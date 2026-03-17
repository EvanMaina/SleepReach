"""
Referring Providers API endpoints.

Handles provider management, statistics, and referral tracking.
"""

import logging
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, and_, or_

from ..core.database import get_db
from ..models.provider import ReferringProvider, ProviderStatus, ProviderNotesHistory
from ..models.lead import Lead, LeadStatus
from ..schemas.provider import (
    ProviderCreate,
    ProviderUpdate,
    ProviderResponse,
    ProviderListResponse,
    ProviderDashboardStats,
    ProviderReferralLeadInfo,
)
from ..schemas.common import PaginatedResponse
from ..services.audit import AuditService
from ..services.cache import get_cache
from ..core.auth import get_current_user


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/providers", tags=["Providers"], dependencies=[Depends(get_current_user)])


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


def provider_to_response(provider: ReferringProvider) -> ProviderResponse:
    """Convert provider model to response schema."""
    return ProviderResponse(
        id=provider.id,
        name=provider.name,
        email=provider.email,
        phone=provider.phone,
        fax=provider.fax,
        npi_number=provider.npi_number,
        practice_name=provider.practice_name,
        practice_address=provider.practice_address,
        practice_city=provider.practice_city,
        practice_state=provider.practice_state,
        practice_zip=provider.practice_zip,
        specialty=provider.specialty or "",
        credentials=provider.credentials,
        status=provider.status,
        preferred_contact=provider.preferred_contact,
        send_referral_updates=provider.send_referral_updates,
        total_referrals=provider.total_referrals,
        converted_referrals=provider.converted_referrals,
        conversion_rate=provider.conversion_rate,
        last_referral_at=provider.last_referral_at,
        notes=provider.notes,
        tags=provider.tags,
        created_at=provider.created_at,
        updated_at=provider.updated_at,
        verified_at=provider.verified_at,
    )


def provider_to_list_response(provider: ReferringProvider) -> ProviderListResponse:
    """Convert provider model to list response schema."""
    return ProviderListResponse(
        id=provider.id,
        name=provider.name,
        email=provider.email,  # Added: Include email in list response
        practice_name=provider.practice_name,
        specialty=provider.specialty or "",
        status=provider.status,
        total_referrals=provider.total_referrals,
        converted_referrals=provider.converted_referrals,
        conversion_rate=provider.conversion_rate,
        last_referral_at=provider.last_referral_at,
    )


# =============================================================================
# Provider CRUD Endpoints
# =============================================================================

@router.get(
    "",
    response_model=PaginatedResponse,
    summary="List Providers",
    description="Get paginated list of referring providers.",
)
async def list_providers(
    request: Request,
    db: Session = Depends(get_db),
    page: int = 1,
    page_size: int = 20,
    status_filter: Optional[ProviderStatus] = None,
    status: Optional[ProviderStatus] = None,  # Alias for status_filter (frontend compatibility)
    specialty_filter: Optional[str] = None,  # Free text specialty filter
    specialty: Optional[str] = None,  # Alias for specialty_filter (frontend compatibility)
    search: Optional[str] = None,
    sort_by: str = "total_referrals",
    sort_order: str = "desc",
) -> PaginatedResponse:
    """
    List providers with pagination, filtering, and search.
    
    Args:
        request: FastAPI request
        db: Database session
        page: Page number (1-indexed)
        page_size: Items per page (max 100)
        status_filter: Optional status filter
        specialty_filter: Optional specialty filter
        search: Optional search query (name or practice)
        sort_by: Field to sort by (total_referrals, name, created_at)
        sort_order: Sort order (asc or desc)
    """
    page_size = min(page_size, 100)
    
    # Build base query
    query = db.query(ReferringProvider)
    
    # Apply filters - support both parameter names for compatibility
    effective_status = status_filter or status
    effective_specialty = specialty_filter or specialty
    
    if effective_status:
        query = query.filter(ReferringProvider.status == effective_status)
    if effective_specialty:
        # Free text specialty - use case-insensitive LIKE match
        query = query.filter(ReferringProvider.specialty.ilike(f"%{effective_specialty}%"))
    
    # Search by name or practice
    if search:
        search_term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                ReferringProvider.name.ilike(search_term),
                ReferringProvider.practice_name.ilike(search_term),
                ReferringProvider.email.ilike(search_term),
            )
        )
    
    # Get total count
    total = query.count()
    
    # Apply sorting
    sort_column = {
        "total_referrals": ReferringProvider.total_referrals,
        "name": ReferringProvider.name,
        "created_at": ReferringProvider.created_at,
        "conversion_rate": ReferringProvider.converted_referrals,  # Will sort by converted count
        "last_referral_at": ReferringProvider.last_referral_at,
    }.get(sort_by, ReferringProvider.total_referrals)
    
    if sort_order.lower() == "asc":
        query = query.order_by(sort_column)
    else:
        query = query.order_by(desc(sort_column))
    
    # Pagination
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    offset = (page - 1) * page_size
    
    providers = query.offset(offset).limit(page_size).all()
    
    items = [provider_to_list_response(p).model_dump() for p in providers]
    
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_previous=page > 1,
    )


@router.get(
    "/stats",
    response_model=ProviderDashboardStats,
    summary="Provider Dashboard Stats",
    description="Get summary statistics for the providers dashboard.",
)
async def get_provider_stats(
    request: Request,
    db: Session = Depends(get_db),
) -> ProviderDashboardStats:
    """
    Get dashboard summary statistics for providers.
    """
    # Count providers by status
    total_providers = db.query(ReferringProvider).count()
    active_providers = db.query(ReferringProvider).filter(
        ReferringProvider.status == ProviderStatus.ACTIVE
    ).count()
    pending_providers = db.query(ReferringProvider).filter(
        ReferringProvider.status == ProviderStatus.PENDING
    ).count()
    
    # Count referral leads — exclude soft-deleted leads
    total_referrals = db.query(Lead).filter(
        Lead.is_referral == True,
        Lead.deleted_at.is_(None),
    ).count()

    # Count converted referrals (reached SCHEDULED or beyond) — exclude soft-deleted
    converted_referrals = db.query(Lead).filter(
        and_(
            Lead.is_referral == True,
            Lead.deleted_at.is_(None),
            Lead.status.in_([
                LeadStatus.SCHEDULED,
                LeadStatus.CONSULTATION_COMPLETE,
                LeadStatus.TREATMENT_STARTED,
            ])
        )
    ).count()

    # Calculate conversion rate
    overall_conversion_rate = 0.0
    if total_referrals > 0:
        overall_conversion_rate = round((converted_referrals / total_referrals) * 100, 1)

    # Count referrals this month — exclude soft-deleted
    first_of_month = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    referrals_this_month = db.query(Lead).filter(
        and_(
            Lead.is_referral == True,
            Lead.deleted_at.is_(None),
            Lead.created_at >= first_of_month
        )
    ).count()
    
    # Get top 5 providers by referral count
    top_providers_query = (
        db.query(ReferringProvider)
        .filter(ReferringProvider.status == ProviderStatus.ACTIVE)
        .order_by(desc(ReferringProvider.total_referrals))
        .limit(5)
        .all()
    )
    
    top_providers = [provider_to_list_response(p) for p in top_providers_query]
    
    return ProviderDashboardStats(
        total_providers=total_providers,
        active_providers=active_providers,
        pending_providers=pending_providers,
        total_referrals=total_referrals,
        converted_referrals=converted_referrals,
        overall_conversion_rate=overall_conversion_rate,
        referrals_this_month=referrals_this_month,
        top_providers=top_providers,
    )


@router.get(
    "/{provider_id}",
    response_model=ProviderResponse,
    summary="Get Provider",
    description="Get detailed information about a specific provider.",
)
async def get_provider(
    provider_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> ProviderResponse:
    """Get provider details by ID."""
    provider = db.query(ReferringProvider).filter(
        ReferringProvider.id == provider_id
    ).first()
    
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider not found",
        )
    
    # Log audit
    try:
        audit_service = AuditService(db)
        audit_service.log_read(
            table_name="referring_providers",
            record_id=provider.id,
            ip_address=get_client_ip(request),
            endpoint=f"/api/providers/{provider_id}",
            request_method="GET",
            user_agent=get_user_agent(request),
        )
    except Exception:
        pass
    
    return provider_to_response(provider)


@router.post(
    "",
    response_model=ProviderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Provider",
    description="Create a new referring provider manually.",
)
async def create_provider(
    provider_data: ProviderCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> ProviderResponse:
    """Create a new referring provider."""
    # Check for duplicate email
    if provider_data.email:
        existing = db.query(ReferringProvider).filter(
            func.lower(ReferringProvider.email) == provider_data.email.lower()
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Provider with email {provider_data.email} already exists",
            )
    
    # Check for duplicate NPI
    if provider_data.npi_number:
        existing = db.query(ReferringProvider).filter(
            ReferringProvider.npi_number == provider_data.npi_number
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Provider with NPI {provider_data.npi_number} already exists",
            )
    
    # Create provider
    provider = ReferringProvider(
        name=provider_data.name,
        email=provider_data.email,
        phone=provider_data.phone,
        fax=provider_data.fax,
        npi_number=provider_data.npi_number,
        practice_name=provider_data.practice_name,
        practice_address=provider_data.practice_address,
        practice_city=provider_data.practice_city,
        practice_state=provider_data.practice_state,
        practice_zip=provider_data.practice_zip,
        specialty=provider_data.specialty,
        credentials=provider_data.credentials,
        status=provider_data.status,
        preferred_contact=provider_data.preferred_contact,
        send_referral_updates=provider_data.send_referral_updates,
        notes=provider_data.notes,
        tags=provider_data.tags or [],
    )
    
    # Set verified_at if status is ACTIVE
    if provider_data.status == ProviderStatus.ACTIVE:
        provider.verified_at = datetime.now(timezone.utc)
    
    db.add(provider)
    db.commit()
    db.refresh(provider)
    
    logger.info(f"Created provider: {provider.name} ({provider.id})")
    
    # Invalidate cache
    try:
        cache = get_cache()
        cache.invalidate_pattern("providers:*")
    except Exception:
        pass
    
    # Log audit
    try:
        audit_service = AuditService(db)
        audit_service.log_create(
            table_name="referring_providers",
            record_id=provider.id,
            ip_address=get_client_ip(request),
            endpoint="/api/providers",
            request_method="POST",
            user_agent=get_user_agent(request),
            new_values={"name": provider.name, "status": provider.status.value},
        )
    except Exception:
        pass
    
    return provider_to_response(provider)


@router.patch(
    "/{provider_id}",
    response_model=ProviderResponse,
    summary="Update Provider",
    description="Update a referring provider's information.",
)
async def update_provider(
    provider_id: UUID,
    provider_data: ProviderUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> ProviderResponse:
    """Update provider details."""
    provider = db.query(ReferringProvider).filter(
        ReferringProvider.id == provider_id
    ).first()
    
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider not found",
        )
    
    # Store old values for audit
    old_values = {
        "status": provider.status.value if provider.status else None,
        "name": provider.name,
    }
    
    # Update fields that are provided
    update_data = provider_data.model_dump(exclude_unset=True)
    
    # Check for duplicate email if changing
    if "email" in update_data and update_data["email"]:
        existing = db.query(ReferringProvider).filter(
            and_(
                func.lower(ReferringProvider.email) == update_data["email"].lower(),
                ReferringProvider.id != provider_id
            )
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Provider with email {update_data['email']} already exists",
            )
    
    # Check for duplicate NPI if changing
    if "npi_number" in update_data and update_data["npi_number"]:
        existing = db.query(ReferringProvider).filter(
            and_(
                ReferringProvider.npi_number == update_data["npi_number"],
                ReferringProvider.id != provider_id
            )
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Provider with NPI {update_data['npi_number']} already exists",
            )
    
    # Apply updates
    for field, value in update_data.items():
        setattr(provider, field, value)
    
    # Update verified_at if status changed to ACTIVE
    if "status" in update_data:
        if update_data["status"] == ProviderStatus.ACTIVE and not provider.verified_at:
            provider.verified_at = datetime.now(timezone.utc)
        elif update_data["status"] == ProviderStatus.ARCHIVED:
            provider.archived_at = datetime.now(timezone.utc)
    
    db.commit()
    db.refresh(provider)
    
    logger.info(f"Updated provider: {provider.name} ({provider.id})")
    
    # Invalidate cache
    try:
        cache = get_cache()
        cache.invalidate_pattern("providers:*")
    except Exception:
        pass
    
    # Log audit
    try:
        audit_service = AuditService(db)
        audit_service.log_update(
            table_name="referring_providers",
            record_id=provider.id,
            ip_address=get_client_ip(request),
            endpoint=f"/api/providers/{provider_id}",
            request_method="PATCH",
            user_agent=get_user_agent(request),
            old_values=old_values,
            new_values=update_data,
        )
    except Exception:
        pass
    
    return provider_to_response(provider)


@router.delete(
    "/{provider_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Archive Provider",
    description="Archive a provider (soft delete - sets status to ARCHIVED).",
)
async def archive_provider(
    provider_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    """Archive a provider (soft delete)."""
    provider = db.query(ReferringProvider).filter(
        ReferringProvider.id == provider_id
    ).first()
    
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider not found",
        )
    
    # Soft delete - set status to ARCHIVED
    provider.status = ProviderStatus.ARCHIVED
    provider.archived_at = datetime.now(timezone.utc)
    
    db.commit()
    
    logger.info(f"Archived provider: {provider.name} ({provider.id})")
    
    # Invalidate cache
    try:
        cache = get_cache()
        cache.invalidate_pattern("providers:*")
    except Exception:
        pass
    
    # Log audit
    try:
        audit_service = AuditService(db)
        audit_service.log_update(
            table_name="referring_providers",
            record_id=provider.id,
            ip_address=get_client_ip(request),
            endpoint=f"/api/providers/{provider_id}",
            request_method="DELETE",
            user_agent=get_user_agent(request),
            old_values={"status": provider.status.value},
            new_values={"status": ProviderStatus.ARCHIVED.value},
        )
    except Exception:
        pass


# =============================================================================
# Provider Referrals Endpoint
# =============================================================================

@router.get(
    "/{provider_id}/referrals",
    response_model=List[ProviderReferralLeadInfo],
    summary="Get Provider Referrals",
    description="Get list of referral leads for a specific provider.",
)
async def get_provider_referrals(
    provider_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    limit: int = 50,
) -> List[ProviderReferralLeadInfo]:
    """
    Get referral leads for a provider.
    
    Returns minimal lead info (no PHI) for the provider's referral list.
    """
    provider = db.query(ReferringProvider).filter(
        ReferringProvider.id == provider_id
    ).first()
    
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider not found",
        )
    
    # Get referral leads — exclude soft-deleted leads
    leads = (
        db.query(Lead)
        .filter(
            Lead.referring_provider_id == provider_id,
            Lead.deleted_at.is_(None),
        )
        .order_by(desc(Lead.created_at))
        .limit(limit)
        .all()
    )
    
    result = []
    for lead in leads:
        is_converted = lead.status in [
            LeadStatus.SCHEDULED,
            LeadStatus.CONSULTATION_COMPLETE,
            LeadStatus.TREATMENT_STARTED,
        ]
        result.append(
            ProviderReferralLeadInfo(
                id=lead.id,
                lead_number=lead.lead_number,
                condition=lead.condition.value if lead.condition else "Unknown",
                priority=lead.priority.value if lead.priority else "Unknown",
                status=lead.status.value if lead.status else "Unknown",
                created_at=lead.created_at,
                is_converted=is_converted,
            )
        )
    
    return result


# =============================================================================
# Provider Search/Lookup (for Jotform integration)
# =============================================================================

@router.get(
    "/search/match",
    summary="Search for Matching Provider",
    description="Search for a provider by email or name (for Jotform auto-matching).",
)
async def search_provider_match(
    request: Request,
    db: Session = Depends(get_db),
    email: Optional[str] = None,
    name: Optional[str] = None,
    practice_name: Optional[str] = None,
) -> dict:
    """
    Search for a matching provider.
    
    Used by the Jotform webhook to find or suggest providers.
    Returns the best match if found.
    """
    if not email and not name:
        return {"found": False, "providers": []}
    
    # Try exact email match first
    if email:
        provider = db.query(ReferringProvider).filter(
            func.lower(ReferringProvider.email) == email.lower()
        ).first()
        
        if provider:
            return {
                "found": True,
                "match_type": "email",
                "confidence": 1.0,
                "provider": provider_to_list_response(provider).model_dump(),
            }
    
    # Try name/practice fuzzy search
    candidates = []
    if name:
        name_matches = (
            db.query(ReferringProvider)
            .filter(ReferringProvider.name.ilike(f"%{name}%"))
            .limit(5)
            .all()
        )
        candidates.extend(name_matches)
    
    if practice_name:
        practice_matches = (
            db.query(ReferringProvider)
            .filter(ReferringProvider.practice_name.ilike(f"%{practice_name}%"))
            .limit(5)
            .all()
        )
        # Add unique matches
        existing_ids = {c.id for c in candidates}
        for p in practice_matches:
            if p.id not in existing_ids:
                candidates.append(p)
    
    if candidates:
        return {
            "found": True,
            "match_type": "fuzzy",
            "confidence": 0.7,
            "providers": [provider_to_list_response(p).model_dump() for p in candidates[:5]],
        }
    
    return {"found": False, "providers": []}


# =============================================================================
# Provider Notes History Endpoints
# =============================================================================

@router.get(
    "/{provider_id}/notes",
    summary="Get Provider Notes History",
    description="Get the history of all notes for a specific provider.",
)
async def get_provider_notes_history(
    provider_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    limit: int = 50,
) -> dict:
    """
    Get all notes history for a provider.
    
    Returns chronologically ordered list of all notes and interactions.
    """
    # Verify provider exists
    provider = db.query(ReferringProvider).filter(
        ReferringProvider.id == provider_id
    ).first()
    
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider not found",
        )
    
    # Get notes history
    notes = (
        db.query(ProviderNotesHistory)
        .filter(ProviderNotesHistory.provider_id == provider_id)
        .order_by(desc(ProviderNotesHistory.created_at))
        .limit(limit)
        .all()
    )
    
    return {
        "provider_id": str(provider_id),
        "provider_name": provider.name,
        "current_notes": provider.notes,
        "notes_history": [note.to_dict() for note in notes],
        "total_notes": len(notes),
    }


@router.post(
    "/{provider_id}/notes",
    status_code=status.HTTP_201_CREATED,
    summary="Add Provider Note",
    description="Add a new note to a provider's history.",
)
async def add_provider_note(
    provider_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    note_text: str = "",
    note_type: str = "general",
    created_by: str = None,
) -> dict:
    """
    Add a new note to a provider.
    
    This creates a note in the history AND updates the provider's current notes field.
    """
    # Verify provider exists
    provider = db.query(ReferringProvider).filter(
        ReferringProvider.id == provider_id
    ).first()
    
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider not found",
        )
    
    # Parse request body if note_text wasn't provided as query param
    if not note_text:
        try:
            body = await request.json()
            note_text = body.get("note_text", "")
            note_type = body.get("note_type", "general")
            created_by = body.get("created_by")
        except (ValueError, KeyError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="note_text is required",
            )
    
    if not note_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="note_text cannot be empty",
        )
    
    # Create the note in history
    note = ProviderNotesHistory(
        provider_id=provider_id,
        note_text=note_text.strip(),
        note_type=note_type,
        created_by=created_by or "Coordinator",
    )
    
    db.add(note)
    
    # Also update the provider's current notes field
    provider.notes = note_text.strip()
    
    db.commit()
    db.refresh(note)
    
    logger.info(f"Added note for provider {provider.name}: {note_type}")
    
    return {
        "success": True,
        "note": note.to_dict(),
        "message": "Note added successfully",
    }


# =============================================================================
# Provider Email Endpoint
# =============================================================================

class ProviderEmailRequest(BaseModel):
    subject: str
    message: str


@router.post(
    "/{provider_id}/email",
    summary="Send Email to Provider",
    description="Send a direct email to a referring provider via the platform email service.",
)
async def send_provider_email(
    provider_id: UUID,
    email_request: ProviderEmailRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """
    Send an email to a referring provider.

    Uses the platform SMTP email service. Returns 400 if provider has no email.
    """
    provider = db.query(ReferringProvider).filter(
        ReferringProvider.id == provider_id
    ).first()

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider not found",
        )

    if not provider.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider has no email address on file",
        )

    from ..services.email_service import email_service
    from ..services.email_base import wrap_in_email_layout

    # Build the message body using the branded layout (teal header + clinic footer).
    # wrap_in_email_layout() injects body_html into a <table> structure, so the
    # content MUST be wrapped in <tr><td> tags — raw <p>/<div> tags inside a
    # <table> render incorrectly in most email clients (Outlook, Gmail, etc.).
    body_html = f"""
                    <tr>
                        <td style="padding: 20px 30px 0 30px;">
                            <p style="margin: 0 0 20px 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; color: #444444; line-height: 1.7;">
                                Dear {provider.name},
                            </p>
                            <div style="font-family: Arial, Helvetica, sans-serif; font-size: 15px; color: #333333; line-height: 1.8; white-space: pre-wrap;">{email_request.message}</div>
                        </td>
                    </tr>
"""
    html_content = wrap_in_email_layout(
        title=email_request.subject,
        body_html=body_html,
    )

    try:
        success = email_service.send_email(
            to_email=provider.email,
            subject=email_request.subject,
            html_content=html_content,
            text_content=email_request.message,
        )
    except Exception as exc:
        logger.error(f"Email send failed for provider {provider.id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send email. Please check the email service configuration.",
        )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Email delivery failed. Please try again later.",
        )

    logger.info(f"Email sent to provider {provider.name} <{provider.email}>")

    # Log audit
    try:
        audit_service = AuditService(db)
        audit_service.log_update(
            table_name="referring_providers",
            record_id=provider.id,
            ip_address=get_client_ip(request),
            endpoint=f"/api/providers/{provider_id}/email",
            request_method="POST",
            user_agent=get_user_agent(request),
            old_values={},
            new_values={"action": "email_sent", "subject": email_request.subject},
        )
    except Exception:
        pass

    return {
        "success": True,
        "message": f"Email sent successfully to {provider.name} at {provider.email}",
    }
