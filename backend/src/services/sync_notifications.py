"""
Notification dispatcher — smart Celery-first with synchronous fallback.

This module is the SINGLE entry point for all email/SMS notifications in the
application. It replaces scattered .delay() / sync calls with a unified API
that automatically chooses the best delivery method:

  1. CELERY (async) — When CELERY_ENABLED=true and a Celery worker is reachable.
     Tasks are queued in Redis and processed by the Celery worker container,
     which retries with exponential backoff on failure.

  2. SYNC (in-request) — When Celery is disabled or unreachable (e.g., Redis
     down, no worker running, development environment). The notification is
     sent synchronously within the HTTP request.

The caller never needs to know which path is taken. Both paths use the EXACT
same email templates, Paubox service, and SMS service — no duplication.

Usage in API endpoints:

    from ..services.sync_notifications import (
        dispatch_lead_receipt_notifications,
        dispatch_coordinator_email,
        dispatch_coordinator_sms,
    )

    # This automatically uses Celery or sync depending on availability
    dispatch_lead_receipt_notifications(
        lead_id=str(lead.id),
        email=decrypted["email"],
        phone=decrypted["phone"],
        first_name=decrypted["first_name"],
        lead_number=lead.lead_number,
    )
"""

import logging
from typing import Dict, Any, Optional, List

from ..core.config import settings

logger = logging.getLogger(__name__)


# =============================================================================
# Celery availability check (cached per-process for 30 seconds)
# =============================================================================

_celery_available: Optional[bool] = None
_celery_checked_at: float = 0.0
_CELERY_CHECK_INTERVAL = 30.0  # Re-check every 30 seconds


def _is_celery_available() -> bool:
    """
    Check if Celery is enabled AND the broker (Redis) is reachable.

    The result is cached for 30 seconds per-process to avoid pinging Redis
    on every single notification call. If Redis goes down mid-process, the
    fallback kicks in within 30 seconds.

    Returns:
        True if tasks can be dispatched via Celery, False otherwise.
    """
    global _celery_available, _celery_checked_at

    if not settings.celery_enabled:
        return False

    import time
    now = time.time()

    # Return cached result if still fresh
    if _celery_available is not None and (now - _celery_checked_at) < _CELERY_CHECK_INTERVAL:
        return _celery_available

    # Probe the broker
    try:
        from ..tasks.celery_app import celery_app
        conn = celery_app.connection()
        conn.ensure_connection(max_retries=1, timeout=3)
        conn.close()
        _celery_available = True
        _celery_checked_at = now
        logger.debug("Celery broker probe: REACHABLE")
        return True
    except Exception as e:
        _celery_available = False
        _celery_checked_at = now
        logger.warning("Celery broker probe: UNREACHABLE (%s). Using sync fallback.", e)
        return False


def _reset_celery_check():
    """Reset the cached Celery check (useful for testing)."""
    global _celery_available, _celery_checked_at
    _celery_available = None
    _celery_checked_at = 0.0


# =============================================================================
# Lead Receipt Notifications (email + SMS to new leads)
# =============================================================================

def dispatch_lead_receipt_notifications(
    lead_id: str,
    email: str,
    phone: str,
    first_name: str,
    lead_number: str,
    response_time: str = "24-48 hours",
    conditions: Optional[List[str]] = None,
    other_condition_text: str = "",
) -> Dict[str, Any]:
    """
    Send receipt email and SMS to a new lead.

    Dispatches via Celery if available, otherwise sends synchronously.
    Both paths use the same unified lead confirmation email template
    from email_templates.py and the same SMS template from sms_service.py.

    Args:
        lead_id: UUID of the lead
        email: Lead's email address
        phone: Lead's phone number
        first_name: Lead's first name
        lead_number: Lead reference number
        response_time: Expected response time
        conditions: List of condition strings (optional)
        other_condition_text: Custom condition text (optional)

    Returns:
        Dict with send status
    """
    if _is_celery_available():
        try:
            from ..tasks.lead_tasks import send_lead_receipt_notifications
            result = send_lead_receipt_notifications.delay(
                lead_id=lead_id,
                email=email,
                phone=phone,
                first_name=first_name,
                lead_number=lead_number,
                response_time=response_time,
                conditions=conditions or [],
                other_condition_text=other_condition_text,
            )
            logger.info(
                "Lead receipt notifications queued via Celery for %s (task_id=%s)",
                lead_number, result.id,
            )
            return {"status": "queued", "task_id": result.id, "method": "celery"}
        except Exception as e:
            logger.warning(
                "Celery dispatch failed for lead %s, falling back to sync: %s",
                lead_number, e,
            )
            # Fall through to sync path

    # Synchronous fallback
    return _send_lead_receipt_sync(
        lead_id=lead_id,
        email=email,
        phone=phone,
        first_name=first_name,
        lead_number=lead_number,
        response_time=response_time,
        conditions=conditions,
        other_condition_text=other_condition_text,
    )


def _send_lead_receipt_sync(
    lead_id: str,
    email: str,
    phone: str,
    first_name: str,
    lead_number: str,
    response_time: str = "24-48 hours",
    conditions: Optional[List[str]] = None,
    other_condition_text: str = "",
) -> Dict[str, Any]:
    """
    Send receipt email and SMS to a new lead — synchronously.

    Uses the EXACT same unified lead confirmation email template
    from email_templates.py and the same SMS template from sms_service.py.
    """
    from .email_templates import send_lead_confirmation_email
    from .sms_service import sms_service

    results = {"email": False, "email_provider": "none", "sms": False, "method": "sync"}

    try:
        # ── Email ────────────────────────────────────────────────────────
        if email:
            email_result = send_lead_confirmation_email({
                "first_name": first_name,
                "email": email,
                "lead_number": lead_number,
                "lead_id": lead_id,
                "conditions": conditions or [],
                "other_condition_text": other_condition_text or "",
            })

            results["email"] = email_result.get("success", False)
            results["email_provider"] = email_result.get("provider", "unknown")
            results["email_message_id"] = email_result.get("message_id")

            masked = email[:2] + "***@" + email.split("@")[-1] if "@" in email else "***"
            logger.info(
                "Lead confirmation email sent to %s via %s: %s (sync)",
                masked, results["email_provider"], results["email"],
            )

        # ── SMS ──────────────────────────────────────────────────────────
        if phone:
            context = {
                "first_name": first_name,
                "lead_number": lead_number,
                "response_time": response_time,
                "phone_number": settings.support_phone,
            }
            sms_content = sms_service.render_template("lead_receipt", context)
            sms_result = sms_service.send_sms(to_number=phone, message=sms_content)
            results["sms"] = sms_result

        logger.info(
            "Receipt notifications for lead %s: email=%s (%s), sms=%s (sync)",
            lead_number, results["email"], results["email_provider"], results["sms"],
        )
        return {"status": "success", "results": results}

    except Exception as e:
        logger.error("Failed to send receipt notifications for lead %s: %s", lead_id, e)
        return {"status": "error", "error": str(e), "results": results}


# =============================================================================
# Coordinator Email (dashboard → lead)
# =============================================================================

def dispatch_coordinator_email(
    to_email: str,
    subject: str,
    body: str,
    lead_id: str,
    lead_name: str,
    category: str,
) -> Dict[str, Any]:
    """
    Send an email from coordinator to a lead.

    Dispatches via Celery if available, otherwise sends synchronously.
    Both paths use the same wrap_email_in_template() and send_email_via_paubox().

    Args:
        to_email: Recipient email address
        subject: Email subject
        body: Email body (plain text — wrapped in HTML template)
        lead_id: UUID of the lead
        lead_name: Lead's first name
        category: Email template category

    Returns:
        Dict with send status
    """
    if _is_celery_available():
        try:
            from ..tasks.lead_tasks import send_coordinator_email
            result = send_coordinator_email.delay(
                to_email=to_email,
                subject=subject,
                body=body,
                lead_id=lead_id,
                lead_name=lead_name,
                category=category,
            )
            logger.info(
                "Coordinator email queued via Celery for lead %s (task_id=%s)",
                lead_id, result.id,
            )
            return {"status": "queued", "task_id": result.id, "method": "celery"}
        except Exception as e:
            logger.warning(
                "Celery dispatch failed for coordinator email (lead %s), "
                "falling back to sync: %s", lead_id, e,
            )

    # Synchronous fallback
    return _send_coordinator_email_sync(
        to_email=to_email,
        subject=subject,
        body=body,
        lead_id=lead_id,
        lead_name=lead_name,
        category=category,
    )


def _send_coordinator_email_sync(
    to_email: str,
    subject: str,
    body: str,
    lead_id: str,
    lead_name: str,
    category: str,
) -> Dict[str, Any]:
    """
    Send a coordinator email to a lead — synchronously.

    Uses the EXACT same wrap_email_in_template() from lead_tasks.py
    and send_email_via_paubox() from paubox_email_service.py.
    """
    from ..tasks.lead_tasks import wrap_email_in_template
    from .paubox_email_service import send_email_via_paubox

    try:
        html_content = wrap_email_in_template(body, lead_name, subject)

        result = send_email_via_paubox(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=body,
            lead_id=lead_id,
        )

        provider = result.get("provider", "unknown")
        success = result.get("success", False)

        logger.info(
            "Coordinator email sent for lead %s (%s) via %s: %s (sync)",
            lead_id, category, provider, success,
        )

        return {
            "status": "success" if success else "failed",
            "category": category,
            "lead_id": lead_id,
            "provider": provider,
            "message_id": result.get("message_id"),
            "error": result.get("error") if not success else None,
            "method": "sync",
        }

    except Exception as e:
        logger.error(
            "Failed to send coordinator email for lead %s (%s): %s",
            lead_id, category, e,
        )
        return {
            "status": "failed",
            "category": category,
            "lead_id": lead_id,
            "error": str(e),
            "method": "sync",
        }


# =============================================================================
# Coordinator SMS (dashboard → lead)
# =============================================================================

def dispatch_coordinator_sms(
    to_phone: str,
    message: str,
    lead_id: str,
    lead_name: str,
    category: str,
) -> Dict[str, Any]:
    """
    Send an SMS from coordinator to a lead.

    Dispatches via Celery if available, otherwise sends synchronously.
    Both paths use the same sms_service.send_sms().

    Args:
        to_phone: Recipient phone number
        message: SMS message content
        lead_id: UUID of the lead
        lead_name: Lead's first name
        category: SMS template category

    Returns:
        Dict with send status
    """
    if _is_celery_available():
        try:
            from ..tasks.lead_tasks import send_coordinator_sms
            result = send_coordinator_sms.delay(
                to_phone=to_phone,
                message=message,
                lead_id=lead_id,
                lead_name=lead_name,
                category=category,
            )
            logger.info(
                "Coordinator SMS queued via Celery for lead %s (task_id=%s)",
                lead_id, result.id,
            )
            return {"status": "queued", "task_id": result.id, "method": "celery"}
        except Exception as e:
            logger.warning(
                "Celery dispatch failed for coordinator SMS (lead %s), "
                "falling back to sync: %s", lead_id, e,
            )

    # Synchronous fallback
    return _send_coordinator_sms_sync(
        to_phone=to_phone,
        message=message,
        lead_id=lead_id,
        lead_name=lead_name,
        category=category,
    )


def _send_coordinator_sms_sync(
    to_phone: str,
    message: str,
    lead_id: str,
    lead_name: str,
    category: str,
) -> Dict[str, Any]:
    """
    Send an SMS from coordinator to a lead — synchronously.

    Uses the EXACT same sms_service.send_sms() as the Celery task.
    """
    from .sms_service import sms_service

    try:
        result = sms_service.send_sms(to_number=to_phone, message=message)

        success = result.get("success", False)
        message_sid = result.get("message_sid")

        logger.info(
            "Coordinator SMS sent for lead %s (%s): Success=%s, SID=%s (sync)",
            lead_id, category, success, message_sid,
        )

        return {
            "status": "success" if success else "failed",
            "category": category,
            "lead_id": lead_id,
            "message_sid": message_sid,
            "twilio_status": result.get("status"),
            "error": result.get("error") if not success else None,
            "method": "sync",
        }

    except Exception as e:
        logger.error(
            "Failed to send coordinator SMS for lead %s (%s): %s",
            lead_id, category, e,
        )
        return {
            "status": "failed",
            "category": category,
            "lead_id": lead_id,
            "error": str(e),
            "method": "sync",
        }


# =============================================================================
# Legacy aliases (backward compatibility)
# =============================================================================
# These aliases ensure any remaining imports of the old function names
# continue to work without code changes.

send_lead_receipt_notifications_sync = dispatch_lead_receipt_notifications
send_coordinator_email_sync = dispatch_coordinator_email
send_coordinator_sms_sync = dispatch_coordinator_sms
