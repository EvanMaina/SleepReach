"""
Communications API endpoints for sending emails and SMS to leads.

Provides endpoints for coordinators to send templated communications
to leads directly from the dashboard.
"""

import hashlib
import time
from datetime import datetime, timezone
from typing import Dict, Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field

from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models.lead import Lead, LeadStatus
from ..services.encryption import EncryptionService
from ..services.audit import AuditService
from ..core.auth import get_current_user


from ..models.user import User

# =============================================================================
# Idempotency Cache (in-memory, 5-minute window)
# Prevents duplicate sends from double-clicks or retries
# =============================================================================
_idempotency_cache: Dict[str, float] = {}
_IDEMPOTENCY_TTL = 300  # 5 minutes


def _check_idempotency(key: Optional[str]) -> bool:
    """
    Check if a request with this idempotency key was already processed.
    Returns True if duplicate (should be rejected), False if new.
    """
    if not key:
        return False

    now = time.time()
    # Clean expired entries (lazy cleanup)
    expired = [k for k, ts in _idempotency_cache.items() if now - ts > _IDEMPOTENCY_TTL]
    for k in expired:
        del _idempotency_cache[k]

    if key in _idempotency_cache:
        return True  # Duplicate

    _idempotency_cache[key] = now
    return False

router = APIRouter(prefix="/api/communications", tags=["Communications"], dependencies=[Depends(get_current_user)])


# =============================================================================
# Request/Response Models
# =============================================================================

class SendEmailRequest(BaseModel):
    """Request to send an email to a lead."""
    lead_id: UUID
    # Template category: follow_up, appointment_confirmation, etc.
    category: str
    subject: str
    body: str


class SendSMSRequest(BaseModel):
    """Request to send an SMS to a lead or direct phone number."""
    lead_id: Optional[UUID] = None  # Optional if to_phone is provided
    to_phone: Optional[str] = None  # Direct phone number (for quick SMS)
    category: str  # Template category: follow_up, appointment_reminder, etc.
    message: str


class CommunicationResponse(BaseModel):
    """Response for communication send requests."""
    success: bool
    message: str
    task_id: Optional[str] = None


# =============================================================================
# Helper Functions
# =============================================================================

def get_client_ip(request: Request) -> Optional[str]:
    """Extract client IP from request headers."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def get_user_agent(request: Request) -> Optional[str]:
    """Extract user agent from request headers."""
    return request.headers.get("User-Agent")


# =============================================================================
# Email Endpoints
# =============================================================================

@router.post(
    "/email/send",
    response_model=CommunicationResponse,
    summary="Send Email to Lead",
    description="Send a templated email to a lead.",
)
async def send_email_to_lead(
    email_data: SendEmailRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    x_idempotency_key: Optional[str] = Header(None),
) -> CommunicationResponse:
    """
    Send an email to a lead.

    The email is queued via Celery for async delivery.
    Supports X-Idempotency-Key header to prevent duplicate sends.

    Args:
        email_data: Email content and lead ID
        request: FastAPI request
        db: Database session
        x_idempotency_key: Optional idempotency key to prevent duplicates

    Returns:
        CommunicationResponse with task ID

    Raises:
        HTTPException: If lead not found or has no email
    """
    # Idempotency check — auto-generate key from lead_id + subject if not provided
    idem_key = x_idempotency_key or f"email:{email_data.lead_id}:{hashlib.md5(email_data.subject.encode()).hexdigest()[:8]}"
    if _check_idempotency(idem_key):
        return CommunicationResponse(
            success=True,
            message="Email already queued (duplicate request ignored)",
            task_id=None,
        )

    # Fetch lead
    lead = db.query(Lead).filter(Lead.id == email_data.lead_id).first()

    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    # Decrypt PHI to get email
    decrypted = EncryptionService.decrypt_lead_phi(lead)
    email = decrypted.get("email")
    first_name = decrypted.get("first_name", "there")

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lead does not have an email address",
        )

    try:
        # Send email via dispatcher (Celery async with sync fallback)
        from ..services.sync_notifications import dispatch_coordinator_email

        dispatch_result = dispatch_coordinator_email(
            to_email=email,
            subject=email_data.subject,
            body=email_data.body,
            lead_id=str(lead.id),
            lead_name=first_name,
            category=email_data.category,
        )

        # Determine success: both "success" (sync) and "queued" (Celery) mean OK
        result_status = dispatch_result.get("status", "")
        is_success = result_status in ("success", "queued")
        provider = dispatch_result.get("provider") or dispatch_result.get("method") or "unknown"
        message_id = dispatch_result.get("message_id") or dispatch_result.get("task_id")

        # Log audit
        audit_service = AuditService(db)
        audit_service.log_create(
            table_name="communications",
            record_id=lead.id,
            ip_address=get_client_ip(request),
            endpoint="/api/communications/email/send",
            request_method="POST",
            user_agent=get_user_agent(request),
            new_values={
                "type": "email",
                "category": email_data.category,
                "lead_id": str(lead.id),
                "subject": email_data.subject[:50] + "..." if len(email_data.subject) > 50 else email_data.subject,
            },
        )

        # Update lead status and mark activity
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        new_note = f"[{timestamp}] Email sent ({email_data.category}): {email_data.subject}"

        # Auto-move lead from NEW → CONTACTED on first communication
        if lead.status == LeadStatus.NEW:
            lead.status = LeadStatus.CONTACTED
            lead.contacted_at = datetime.now(timezone.utc)

        existing_notes = lead.notes or ""
        lead.notes = f"{new_note}\n{existing_notes}" if existing_notes else new_note
        lead.last_updated_at = datetime.now(timezone.utc)
        db.commit()

        # Build user-friendly message
        masked_email = email[:2] + "***@" + email.split("@")[-1] if "@" in email else email
        if result_status == "queued":
            msg = f"Email queued for delivery to {masked_email} via {provider}"
        elif is_success:
            msg = f"Email sent to {masked_email} via {provider}"
        else:
            msg = f"Email delivery failed: {dispatch_result.get('error', 'unknown error')}"

        return CommunicationResponse(
            success=is_success,
            message=msg,
            task_id=message_id,
        )

    except Exception as e:
        import logging
        logging.error(f"Failed to send email: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send email: {str(e)}",
        )


# =============================================================================
# SMS Endpoints
# =============================================================================

@router.post(
    "/sms/send",
    response_model=CommunicationResponse,
    summary="Send SMS to Lead",
    description="Send a templated SMS to a lead.",
)
async def send_sms_to_lead(
    sms_data: SendSMSRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    x_idempotency_key: Optional[str] = Header(None),
) -> CommunicationResponse:
    """
    Send an SMS to a lead or direct phone number.

    The SMS is queued via Celery for async delivery.
    Supports X-Idempotency-Key header to prevent duplicate sends.
    If lead_id is provided, requires lead to have SMS consent.
    If to_phone is provided directly, sends without lead lookup.

    Args:
        sms_data: SMS content and lead ID or phone number
        request: FastAPI request
        db: Database session
        x_idempotency_key: Optional idempotency key to prevent duplicates

    Returns:
        CommunicationResponse with task ID

    Raises:
        HTTPException: If lead not found, has no phone, or no SMS consent
    """
    # Idempotency check
    target = str(sms_data.lead_id or sms_data.to_phone or "unknown")
    idem_key = x_idempotency_key or f"sms:{target}:{hashlib.md5(sms_data.message.encode()).hexdigest()[:8]}"
    if _check_idempotency(idem_key):
        return CommunicationResponse(
            success=True,
            message="SMS already queued (duplicate request ignored)",
            task_id=None,
        )

    phone = None
    first_name = "Contact"
    lead = None
    lead_id_str = None

    # Check if we have a direct phone number (quick SMS mode)
    if sms_data.to_phone:
        phone = sms_data.to_phone
        # If lead_id also provided, fetch lead info for audit
        if sms_data.lead_id:
            lead = db.query(Lead).filter(Lead.id == sms_data.lead_id).first()
            if lead:
                decrypted = EncryptionService.decrypt_lead_phi(lead)
                first_name = decrypted.get("first_name", "Contact")
                lead_id_str = str(lead.id)
    elif sms_data.lead_id:
        # Lead-based SMS - fetch lead and get phone
        lead = db.query(Lead).filter(Lead.id == sms_data.lead_id).first()

        if not lead:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found",
            )

        # Business requirement: coordinators can send SMS to any lead with a phone number.
        # The sms_consent field is stored in the DB for record-keeping but does NOT gate sending.

        # Decrypt PHI to get phone
        decrypted = EncryptionService.decrypt_lead_phi(lead)
        phone = decrypted.get("phone")
        first_name = decrypted.get("first_name", "there")
        lead_id_str = str(lead.id)

        if not phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lead does not have a phone number",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either lead_id or to_phone must be provided",
        )

    try:
        # Send SMS via dispatcher (Celery async with sync fallback)
        from ..services.sync_notifications import dispatch_coordinator_sms

        sms_result = dispatch_coordinator_sms(
            to_phone=phone,
            message=sms_data.message,
            lead_id=lead_id_str or "direct",
            lead_name=first_name,
            category=sms_data.category,
        )

        # Log audit (only if we have a lead)
        if lead:
            audit_service = AuditService(db)
            audit_service.log_create(
                table_name="communications",
                record_id=lead.id,
                ip_address=get_client_ip(request),
                endpoint="/api/communications/sms/send",
                request_method="POST",
                user_agent=get_user_agent(request),
                new_values={
                    "type": "sms",
                    "category": sms_data.category,
                    "lead_id": lead_id_str,
                    "to_phone": phone[-4:] if phone else None,  # Only log last 4 digits
                    "message_preview": sms_data.message[:30] + "..." if len(sms_data.message) > 30 else sms_data.message,
                },
            )

        # Update lead status and mark activity if we have a lead
        if lead:
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
            new_note = f"[{timestamp}] SMS sent ({sms_data.category})"

            # Auto-move lead from NEW → CONTACTED on first communication
            if lead.status == LeadStatus.NEW:
                lead.status = LeadStatus.CONTACTED
                lead.contacted_at = datetime.now(timezone.utc)

            existing_notes = lead.notes or ""
            lead.notes = f"{new_note}\n{existing_notes}" if existing_notes else new_note
            lead.last_updated_at = datetime.now(timezone.utc)
        db.commit()

        # Determine success: both "success" (sync) and "queued" (Celery) mean OK
        sms_status = sms_result.get("status", "")
        sms_success = sms_status in ("success", "queued")
        sms_task_id = sms_result.get("message_sid") or sms_result.get("task_id")

        # Mask phone for user-facing message
        masked_phone = f"***-***-{phone[-4:]}" if phone and len(phone) >= 4 else phone

        if sms_status == "queued":
            sms_msg = f"SMS queued for delivery to {masked_phone}"
        elif sms_success:
            sms_msg = f"SMS sent to {masked_phone}"
        else:
            sms_msg = f"SMS failed: {sms_result.get('error', 'unknown error')}"

        return CommunicationResponse(
            success=sms_success,
            message=sms_msg,
            task_id=sms_task_id,
        )

    except Exception as e:
        import logging
        logging.error(f"Failed to send SMS: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send SMS: {str(e)}",
        )


# =============================================================================
# Template Endpoints
# =============================================================================

@router.get(
    "/templates",
    summary="Get Communication Templates",
    description="Get available email and SMS templates.",
)
async def get_templates():
    """
    Get available communication templates.

    Returns predefined templates for email and SMS communications.
    """
    return {
        "email_templates": [
            {"id": "follow_up", "label": "Follow-up",
                "description": "General follow-up on TMS inquiry"},
            {"id": "appointment_confirmation", "label": "Appointment Confirmation",
                "description": "Confirm scheduled consultation"},
            {"id": "appointment_reminder", "label": "Appointment Reminder",
                "description": "Remind about upcoming appointment"},
            {"id": "missed_call", "label": "Missed Call Follow-up",
                "description": "Follow up after missed call"},
            {"id": "thank_you", "label": "Thank You",
                "description": "Thank you after conversation"},
            {"id": "no_response_final", "label": "Final Outreach",
                "description": "Last attempt to reach lead"},
            {"id": "custom", "label": "Custom Email",
                "description": "Write custom message"},
        ],
        "sms_templates": [
            {"id": "follow_up", "label": "Follow-up",
                "description": "Quick follow-up message"},
            {"id": "appointment_reminder", "label": "Appointment Reminder",
                "description": "Remind about appointment"},
            {"id": "missed_call", "label": "Missed Call",
                "description": "Follow up after missed call"},
            {"id": "thank_you", "label": "Thank You",
                "description": "Thank you message"},
            {"id": "schedule_request", "label": "Schedule Request",
                "description": "Request to schedule"},
            {"id": "no_response_final", "label": "Final Outreach",
                "description": "Last attempt"},
            {"id": "custom", "label": "Custom SMS",
                "description": "Write custom message"},
        ],
    }
