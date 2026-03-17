"""
Lead submission and management endpoints.

Handles patient intake form submissions from the widget
and lead retrieval for the dashboard.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, func, or_

from ..core.config import settings
from ..core.database import get_db
from ..models.lead import Lead, PriorityType, LeadStatus, ContactOutcome, LeadSource, ConditionType, DurationType, UrgencyType
from ..models.provider import ReferringProvider
from ..schemas.lead import (
    LeadCreate,
    LeadUpdate,
    LeadResponse,
    LeadListResponse,
    LeadSubmitResponse,
    ScheduleCallbackRequest,
    LogContactAttemptRequest,
    ScheduledLeadResponse,
    UpdateContactOutcomeRequest,
    ManualLeadCreate,
)
from ..schemas.common import PaginatedResponse, ErrorResponse
from ..services.lead_scoring import (
    calculate_lead_score as calculate_lead_score_legacy,
    get_estimated_response_time as get_estimated_response_time_legacy,
    get_confirmation_message as get_confirmation_message_legacy,
)
# NEW: Use v2 scoring and canonical mapping for widget submissions
from ..services.lead_scoring_v2 import (
    calculate_lead_score as calculate_lead_score_v2,
    calculate_score_from_lead_data,
    get_estimated_response_time,
    get_confirmation_message,
    ScoreBreakdown,
)
from ..services.intake_mapping import map_widget_submission_to_lead_input, LeadInput
from ..services.encryption import EncryptionService
from ..services.audit import AuditService
from ..services.lead_number import generate_unique_lead_number
from ..services.cache import get_cache
from ..core.auth import get_current_user, require_role
from ..services.lead_scoring_v2 import is_in_service_area as _check_service_area


router = APIRouter(prefix="/api/leads", tags=["Leads"])


# =============================================================================
# Helper Functions
# =============================================================================

def mark_lead_activity(lead: Lead) -> None:
    """
    Mark lead as having recent activity.
    
    Call this whenever ANY modification is made to a lead to update
    the last_updated_at timestamp for coordinator workflow sorting.
    
    Args:
        lead: Lead model instance to mark
    """
    lead.last_updated_at = datetime.now(timezone.utc)


def clear_lead_transition_fields(lead: Lead) -> None:
    """
    Clear all stale transition fields BEFORE setting new status/tags.
    
    CRITICAL: Call this at the START of every queue transition to prevent
    old tags from carrying over. For example, a lead marked "Cancelled Appointment"
    that gets a callback scheduled should NOT still show "Cancelled Appointment".
    
    This clears:
    - contact_outcome (reset to NEW baseline — NOT None, column is NOT NULL)
    - follow_up_reason (e.g., "No Answer", "Callback Requested", "No Show")
    - follow_up_date (follow-up schedule)
    - scheduled_callback_at (callback/consultation datetime)
    - next_follow_up_at (next follow-up datetime)
    - scheduled_notes (callback/consultation notes)
    
    This does NOT clear:
    - notes (permanent coordinator notes)
    - priority, score (permanent lead data)
    - contact_attempts, last_contact_attempt (historical tracking)
    - source, UTM data, referral data (attribution)
    - status (caller sets this after clearing)
    
    NOTE: Callers MUST set contact_outcome to the appropriate value after
    calling this function. The baseline is ContactOutcome.NEW but most
    callers will immediately override it with the new outcome.
    
    Args:
        lead: Lead model instance to clear transition fields on
    """
    # CRITICAL: Set to NEW (not None) — contact_outcome column is NOT NULL
    lead.contact_outcome = ContactOutcome.NEW
    lead.follow_up_reason = None
    lead.follow_up_date = None
    lead.scheduled_callback_at = None
    lead.next_follow_up_at = None
    lead.scheduled_notes = None


def get_client_ip(request: Request) -> Optional[str]:
    """
    Extract client IP from request headers.

    Handles X-Forwarded-For for proxied requests.

    Args:
        request: FastAPI request object

    Returns:
        Client IP address or None
    """
    # Check for forwarded IP (when behind proxy/load balancer)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Take the first IP in the chain
        return forwarded.split(",")[0].strip()

    # Fall back to direct client IP
    if request.client:
        return request.client.host

    return None


def get_user_agent(request: Request) -> Optional[str]:
    """
    Extract user agent from request headers.

    Args:
        request: FastAPI request object

    Returns:
        User agent string or None
    """
    return request.headers.get("User-Agent")


# =============================================================================
# Queue Filter Helper — mirrors frontend filterLeadsByQueue() in QueueSidebar.tsx
# =============================================================================

def apply_queue_filter(query, queue_type: Optional[str]):
    """
    Apply queue-type-specific SQL filters to a Lead query.

    Exactly mirrors the frontend filterLeadsByQueue() in QueueSidebar.tsx so
    the server returns only the leads that belong in each coordinator queue.

    Args:
        query: SQLAlchemy query already filtered for deleted_at IS NULL
        queue_type: One of 'all','new','contacted','follow_up','callback',
                    'scheduled','completed','unreachable','hot','medium','low'

    Returns:
        Modified query with the appropriate WHERE clauses applied
    """
    # Terminal statuses excluded from all "active" queues
    TERMINAL = [
        LeadStatus.CONSULTATION_COMPLETE,
        LeadStatus.TREATMENT_STARTED,
        LeadStatus.LOST,
        LeadStatus.DISQUALIFIED,
    ]

    if not queue_type or queue_type == "all":
        # All active leads — exclude terminal statuses
        return query.filter(Lead.status.notin_(TERMINAL))

    if queue_type == "new":
        return query.filter(
            Lead.status == LeadStatus.NEW,
            or_(
                Lead.contact_outcome == ContactOutcome.NEW,
                Lead.contact_outcome.is_(None),
            ),
        )

    if queue_type == "contacted":
        CONTACTED_OUTCOMES = [
            ContactOutcome.ANSWERED,
            ContactOutcome.NO_ANSWER,
            ContactOutcome.UNREACHABLE,
            ContactOutcome.CALLBACK_REQUESTED,
            ContactOutcome.NOT_INTERESTED,
            ContactOutcome.SCHEDULED,
            ContactOutcome.COMPLETED,
        ]
        return query.filter(
            Lead.status != LeadStatus.SCHEDULED,
            Lead.status.notin_(TERMINAL),
            or_(
                Lead.contact_outcome.in_(CONTACTED_OUTCOMES),
                Lead.status == LeadStatus.CONTACTED,
            ),
        )

    if queue_type == "follow_up":
        FOLLOWUP_OUTCOMES = [
            ContactOutcome.NO_ANSWER,
            ContactOutcome.UNREACHABLE,
            ContactOutcome.CALLBACK_REQUESTED,
        ]
        FOLLOWUP_REASONS = [
            "No Answer",
            "Not Interested",
            "No Show",
            "Cancelled Appointment",
        ]
        return query.filter(
            Lead.status != LeadStatus.SCHEDULED,
            Lead.status.notin_(TERMINAL),
            or_(
                Lead.contact_outcome.in_(FOLLOWUP_OUTCOMES),
                Lead.follow_up_reason.in_(FOLLOWUP_REASONS),
            ),
        )

    if queue_type == "callback":
        return query.filter(
            Lead.status != LeadStatus.SCHEDULED,
            Lead.status.notin_(TERMINAL),
            or_(
                Lead.contact_outcome == ContactOutcome.CALLBACK_REQUESTED,
                Lead.follow_up_reason == "Callback Requested",
            ),
        )

    if queue_type == "scheduled":
        return query.filter(Lead.status == LeadStatus.SCHEDULED)

    if queue_type == "completed":
        return query.filter(
            Lead.status.in_([
                LeadStatus.CONSULTATION_COMPLETE,
                LeadStatus.TREATMENT_STARTED,
            ])
        )

    if queue_type == "unreachable":
        return query.filter(
            Lead.status != LeadStatus.SCHEDULED,
            Lead.status.notin_(TERMINAL),
            or_(
                Lead.contact_outcome == ContactOutcome.UNREACHABLE,
                Lead.follow_up_reason == "Unreachable",
            ),
        )

    if queue_type == "not_interested":
        return query.filter(
            Lead.status != LeadStatus.SCHEDULED,
            Lead.status.notin_(TERMINAL),
            or_(
                Lead.contact_outcome == ContactOutcome.NOT_INTERESTED,
                Lead.follow_up_reason == "Not Interested",
            ),
        )

    if queue_type == "hot":
        return query.filter(
            Lead.priority == PriorityType.HOT,
            Lead.status.notin_([LeadStatus.SCHEDULED] + TERMINAL),
        )

    if queue_type == "medium":
        return query.filter(
            Lead.priority == PriorityType.MEDIUM,
            Lead.status.notin_([LeadStatus.SCHEDULED] + TERMINAL),
        )

    if queue_type == "low":
        return query.filter(
            Lead.priority == PriorityType.LOW,
            Lead.status.notin_([LeadStatus.SCHEDULED] + TERMINAL),
        )

    # Unknown queue_type — return query unmodified
    return query


# =============================================================================
# Lightweight New-Lead Check Endpoint (for frontend polling)
# =============================================================================

@router.get(
    "/latest-check",
    summary="Check for new leads",
    description="Lightweight endpoint for frontend polling. Returns latest lead count and timestamp.",
    dependencies=[Depends(get_current_user)],
)
async def latest_check(
    db: Session = Depends(get_db),
) -> dict:
    """
    Ultra-lightweight endpoint for the NewLeadWatcher frontend component.
    
    Returns the total count of active (non-deleted) leads and the
    created_at timestamp of the newest lead. The frontend compares
    the count to its previous value to detect new arrivals.
    
    Redis-cached for 5 seconds to ensure <50ms response under load.
    """
    import logging
    _logger = logging.getLogger(__name__)

    try:
        # Try Redis cache first (5-second TTL)
        try:
            cache = get_cache()
            cached = cache.get("leads:latest_check")
            if cached:
                return cached
        except Exception:
            pass  # Redis down — fall through to DB

        # Single lightweight query: COUNT + MAX(created_at) in one pass
        result = db.execute(
            __import__("sqlalchemy").text(
                "SELECT COUNT(*), MAX(created_at) FROM leads WHERE deleted_at IS NULL"
            )
        ).first()

        total = result[0] or 0 if result else 0
        latest_at = result[1].isoformat() if result and result[1] else None

        # Fetch source values for leads created in the last 30 seconds.
        # This allows the frontend NewLeadWatcher to determine whether new
        # leads are organic (widget/jotform) or manual (coordinator-created)
        # and suppress notifications for manual leads — purely data-driven,
        # no in-memory counters, works across page refreshes and multiple
        # coordinators on different browsers.
        recent_sources_result = db.execute(
            __import__("sqlalchemy").text(
                "SELECT COALESCE(source, 'widget') FROM leads "
                "WHERE deleted_at IS NULL AND created_at >= NOW() - INTERVAL '30 seconds'"
            )
        ).fetchall()
        recent_sources = [row[0] for row in recent_sources_result] if recent_sources_result else []

        payload = {"total": total, "latest_at": latest_at, "recent_sources": recent_sources}

        # Cache for 5 seconds
        try:
            cache = get_cache()
            cache.set("leads:latest_check", payload, ttl=5)
        except Exception:
            pass

        return payload

    except Exception as e:
        _logger.error(f"latest-check error: {e}")
        return {"total": 0, "latest_at": None}


# =============================================================================
# Widget Submission Endpoint
# =============================================================================

@router.post(
    "/submit",
    response_model=LeadSubmitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit Lead from Widget",
    description="Accepts patient intake form submission from the widget.",
    responses={
        201: {"description": "Lead created successfully"},
        400: {"description": "Validation error", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
)
async def submit_lead(
    lead_data: LeadCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> LeadSubmitResponse:
    """
    Submit a new lead from the patient intake widget.

    This endpoint:
    1. Validates input data
    2. Maps to canonical LeadInput format
    3. Calculates lead score with v2 scoring engine
    4. Encrypts PHI before storage
    5. Creates audit log entry
    6. Returns confirmation message

    Args:
        lead_data: LeadCreate schema with form data
        request: FastAPI request for metadata extraction
        db: Database session

    Returns:
        LeadSubmitResponse with confirmation

    Raises:
        HTTPException: If validation or storage fails
    """
    try:
        # =====================================================================
        # Step 0: Duplicate submission check (idempotency + content hash)
        # =====================================================================
        import hashlib
        import logging as _logging
        _dedup_logger = _logging.getLogger(__name__)

        # --- Primary check: client-provided submission_id (UUID, 24h TTL) ---
        sub_id = (lead_data.submission_id or "").strip()
        if sub_id:
            _redis_key = f"widget:dedup:{sub_id}"
            try:
                _cache = get_cache()
                _cached_resp = _cache.get(_redis_key)
                if _cached_resp:
                    _dedup_logger.info("Duplicate widget submission blocked (submission_id=%s)", sub_id)
                    return LeadSubmitResponse(**_cached_resp)
            except Exception:
                pass  # Redis down — proceed normally (fail open)

        # --- Fallback check: content hash of email+phone within 5-minute window ---
        _email_raw = (lead_data.email or "").lower().strip()
        _phone_raw = (lead_data.phone or "").strip()
        _content_hash = hashlib.sha256(
            f"{_email_raw}:{_phone_raw}".encode()
        ).hexdigest()[:32]
        _content_key = f"widget:dedup:content:{_content_hash}"
        try:
            _cache = get_cache()
            _cached_content = _cache.get(_content_key)
            if _cached_content:
                _dedup_logger.info(
                    "Duplicate widget submission blocked (content hash=%s)", _content_hash
                )
                return LeadSubmitResponse(**_cached_content)
        except Exception:
            pass  # Redis down — proceed normally

        # =====================================================================
        # Step 1: Map widget submission to canonical LeadInput format
        # =====================================================================
        widget_payload = {
            "first_name": lead_data.first_name,
            "last_name": lead_data.last_name,
            "email": lead_data.email,
            "phone": lead_data.phone,
            "date_of_birth": lead_data.date_of_birth.isoformat() if lead_data.date_of_birth else None,
            # Use single condition as conditions array
            "condition": lead_data.condition.value if lead_data.condition else "",
            "condition_other": lead_data.condition_other,
            # Multi-condition support (NEW)
            "conditions": [c.value for c in lead_data.conditions] if lead_data.conditions else [],
            "other_condition_text": lead_data.other_condition_text,
            # Severity assessments (NEW)
            "phq2_interest": lead_data.phq2_interest,
            "phq2_mood": lead_data.phq2_mood,
            "gad2_nervous": lead_data.gad2_nervous,
            "gad2_worry": lead_data.gad2_worry,
            "ocd_time_occupied": lead_data.ocd_time_occupied,
            "ptsd_intrusion": lead_data.ptsd_intrusion,
            # TMS therapy interest (NEW)
            "tms_therapy_interest": lead_data.tms_therapy_interest,
            # Preferred contact method (NEW)
            "preferred_contact_method": lead_data.preferred_contact_method,
            # Other fields
            "symptom_duration": lead_data.symptom_duration.value if lead_data.symptom_duration else "",
            "prior_treatments": [t.value for t in lead_data.prior_treatments] if lead_data.prior_treatments else [],
            "has_insurance": lead_data.has_insurance,
            "insurance_provider": lead_data.insurance_provider,
            "other_insurance_provider": lead_data.other_insurance_provider,
            "zip_code": lead_data.zip_code,
            "urgency": lead_data.urgency.value if lead_data.urgency else "",
            "hipaa_consent": lead_data.hipaa_consent,
            "sms_consent": lead_data.sms_consent,
            "utm_params": {
                "utm_source": lead_data.utm_params.utm_source if lead_data.utm_params else None,
                "utm_medium": lead_data.utm_params.utm_medium if lead_data.utm_params else None,
                "utm_campaign": lead_data.utm_params.utm_campaign if lead_data.utm_params else None,
                "utm_term": lead_data.utm_params.utm_term if lead_data.utm_params else None,
                "utm_content": lead_data.utm_params.utm_content if lead_data.utm_params else None,
            } if lead_data.utm_params else {},
            "referrer_url": lead_data.referrer_url,
            # Referral fields (NEW - Widget now supports referrals like Jotform)
            "is_referral": lead_data.is_referral,
            "referring_provider_name": lead_data.referring_provider_name,
            "referring_clinic": lead_data.referring_clinic,
            "referring_provider_email": lead_data.referring_provider_email,
            "referring_provider_specialty": lead_data.referring_provider_specialty,
        }
        
        # Map to canonical LeadInput
        lead_input = map_widget_submission_to_lead_input(widget_payload)
        
        # =====================================================================
        # Step 2: Calculate lead score using v2 scoring engine
        # =====================================================================
        score_breakdown: ScoreBreakdown = calculate_lead_score_v2(lead_input)
        
        # Map priority string to enum
        priority_map = {
            "hot": PriorityType.HOT,
            "medium": PriorityType.MEDIUM,
            "low": PriorityType.LOW,
            "disqualified": PriorityType.DISQUALIFIED,
        }
        priority = priority_map.get(score_breakdown.priority.lower(), PriorityType.LOW)
        in_service_area = score_breakdown.in_service_area

        # Encrypt PHI fields
        encrypted_phi = EncryptionService.encrypt_lead_phi(lead_data)

        # Get request metadata
        client_ip = get_client_ip(request)
        user_agent = get_user_agent(request)

        # Prepare UTM data
        utm_data = {}
        if lead_data.utm_params:
            utm_data = {
                "utm_source": lead_data.utm_params.utm_source,
                "utm_medium": lead_data.utm_params.utm_medium,
                "utm_campaign": lead_data.utm_params.utm_campaign,
                "utm_term": lead_data.utm_params.utm_term,
                "utm_content": lead_data.utm_params.utm_content,
            }

        # Generate unique lead number (TMS-YYYY-XXX format) with retry logic
        lead_number = generate_unique_lead_number(db)

        # Get current timestamp for consent tracking
        consent_timestamp = datetime.now(timezone.utc)

        # =====================================================================
        # Step 2.5: Handle Referral (if is_referral=True from widget)
        # =====================================================================
        referring_provider_id = None
        is_referral = lead_input.referred_by_provider
        
        if is_referral and lead_input.referring_provider_name:
            # Look up or create referring provider
            # IMPORTANT: Ensure empty/whitespace emails become None, not empty string
            email_raw = (lead_input.referring_provider_email or "").lower().strip()
            provider_email_lookup = email_raw if email_raw and "@" in email_raw else None
            provider_name_lookup = lead_input.referring_provider_name.strip()
            
            # Get specialty from lead_data (widget submission)
            provider_specialty_raw = lead_data.referring_provider_specialty or ""
            
            existing_provider = None
            
            # First try to find by email if provided
            if provider_email_lookup:
                existing_provider = db.query(ReferringProvider).filter(
                    ReferringProvider.email == provider_email_lookup
                ).first()
            
            # If not found by email, try by name (case-insensitive)
            if not existing_provider and provider_name_lookup:
                existing_provider = db.query(ReferringProvider).filter(
                    ReferringProvider.name.ilike(provider_name_lookup)
                ).first()
            
            if existing_provider:
                # Update existing provider's missing fields (don't touch total_referrals here)
                if lead_input.referring_clinic and not existing_provider.practice_name:
                    existing_provider.practice_name = lead_input.referring_clinic
                if provider_email_lookup and not existing_provider.email:
                    existing_provider.email = provider_email_lookup
                # Update specialty if not set and we have one from widget
                # RULE: Store exact user input - no mapping, no transformation
                if provider_specialty_raw and not existing_provider.specialty:
                    existing_provider.specialty = provider_specialty_raw.strip()
                referring_provider_id = existing_provider.id
                db.flush()
            else:
                # Create new referring provider with specialty
                # RULE: Store exact user input - no mapping, no transformation
                # NOTE: total_referrals=0 here; will be set via COUNT after lead commit
                new_provider = ReferringProvider(
                    name=provider_name_lookup,
                    email=provider_email_lookup,
                    practice_name=lead_input.referring_clinic if lead_input.referring_clinic else None,
                    specialty=provider_specialty_raw.strip() if provider_specialty_raw else None,
                    total_referrals=0,
                    converted_referrals=0,
                )
                db.add(new_provider)
                db.flush()  # Get the ID without committing
                referring_provider_id = new_provider.id

        # =====================================================================
        # Step 3: Create lead record with ALL fields populated
        # =====================================================================
        lead = Lead(
            # Lead identifier
            lead_number=lead_number,
            # Encrypted PHI
            first_name_encrypted=encrypted_phi["first_name_encrypted"],
            last_name_encrypted=encrypted_phi["last_name_encrypted"],
            email_encrypted=encrypted_phi["email_encrypted"],
            phone_encrypted=encrypted_phi["phone_encrypted"],
            # Date of Birth (optional)
            date_of_birth=lead_data.date_of_birth,
            # Clinical info (legacy single condition)
            condition=lead_data.condition,
            condition_other=lead_data.condition_other,
            # Multi-condition support (NEW)
            conditions=lead_input.conditions if lead_input.conditions else [],
            other_condition_text=lead_input.other_condition_text,
            # TMS therapy interest
            tms_therapy_interest=lead_input.tms_therapy_interest,
            # Preferred contact method (NEW)
            preferred_contact_method=lead_input.preferred_contact_method,
            # Depression PHQ-2 Assessment
            phq2_interest=lead_input.phq2_interest,
            phq2_mood=lead_input.phq2_mood,
            depression_severity_score=score_breakdown.depression_severity_score,
            depression_severity_level=score_breakdown.depression_severity_level,
            # Anxiety GAD-2 Assessment
            gad2_nervous=lead_input.gad2_nervous,
            gad2_worry=lead_input.gad2_worry,
            anxiety_severity_score=score_breakdown.anxiety_severity_score,
            anxiety_severity_level=score_breakdown.anxiety_severity_level,
            # OCD Assessment
            ocd_time_occupied=lead_input.ocd_time_occupied,
            ocd_severity_level=score_breakdown.ocd_severity_level,
            # PTSD Assessment
            ptsd_intrusion=lead_input.ptsd_intrusion,
            ptsd_severity_level=score_breakdown.ptsd_severity_level,
            # Symptom duration
            symptom_duration=lead_data.symptom_duration,
            prior_treatments=lead_data.prior_treatments,
            # Insurance
            has_insurance=lead_data.has_insurance,
            insurance_provider=lead_data.insurance_provider,
            other_insurance_provider=lead_input.other_insurance_provider,
            # Location
            zip_code=lead_data.zip_code,
            in_service_area=in_service_area,
            # Urgency & consent
            urgency=lead_data.urgency,
            hipaa_consent=lead_data.hipaa_consent,
            hipaa_consent_timestamp=consent_timestamp if lead_data.hipaa_consent else None,
            # Privacy consent implied by HIPAA consent
            privacy_consent_timestamp=consent_timestamp if lead_data.hipaa_consent else None,
            sms_consent=lead_data.sms_consent,
            sms_consent_timestamp=consent_timestamp if lead_data.sms_consent else None,
            # Scoring - main score
            score=score_breakdown.lead_score,
            lead_score=score_breakdown.lead_score,
            priority=priority,
            # Score breakdown fields (NEW)
            condition_score=score_breakdown.condition_score,
            therapy_interest_score=score_breakdown.therapy_interest_score,
            severity_score=score_breakdown.severity_score,
            insurance_score=score_breakdown.insurance_score,
            duration_score=score_breakdown.duration_score,
            treatment_score=score_breakdown.treatment_score,
            location_score=score_breakdown.location_score,
            urgency_score=score_breakdown.urgency_score,
            # Status
            status=LeadStatus.NEW,
            # Referral tracking (NEW - Widget now supports referrals like Jotform)
            is_referral=is_referral,
            referring_provider_id=referring_provider_id,
            # UTM tracking
            **utm_data,
            # Metadata
            ip_address_hash=EncryptionService.hash_ip(client_ip),
            user_agent=user_agent,
            referrer_url=lead_data.referrer_url,
        )

        # Save to database
        db.add(lead)
        db.commit()
        db.refresh(lead)

        # IDEMPOTENT FIX: Recalculate provider total_referrals from actual lead COUNT
        # This runs AFTER lead commit so the new lead is included in the count.
        # Using COUNT instead of increment ensures correctness even with retries/races.
        if is_referral and referring_provider_id:
            actual_count = db.query(func.count(Lead.id)).filter(
                Lead.referring_provider_id == referring_provider_id,
                Lead.deleted_at.is_(None),
            ).scalar() or 0
            provider = db.query(ReferringProvider).filter(
                ReferringProvider.id == referring_provider_id
            ).first()
            if provider:
                provider.total_referrals = actual_count
                provider.last_referral_at = datetime.now(timezone.utc)
                db.commit()

        # Invalidate cache to ensure dashboard metrics include new lead
        try:
            cache = get_cache()
            cache.invalidate_on_lead_change()
        except Exception:
            pass  # Don't fail the request if cache invalidation fails

        # Generate confirmation message and estimated time BEFORE notifications
        # Note: v2 functions expect string priority (hot, medium, low, disqualified)
        message = get_confirmation_message(score_breakdown.priority, in_service_area)
        estimated_time = get_estimated_response_time(score_breakdown.priority)

        # Send receipt notifications (email + SMS) via dispatcher (Celery async with sync fallback)
        try:
            from ..services.sync_notifications import dispatch_lead_receipt_notifications

            # Decrypt PHI for notifications
            decrypted = EncryptionService.decrypt_lead_phi(lead)

            # Send email + SMS with conditions for unified template
            dispatch_lead_receipt_notifications(
                lead_id=str(lead.id),
                email=decrypted["email"],
                phone=decrypted["phone"],
                first_name=decrypted["first_name"],
                lead_number=lead.lead_number,
                response_time=estimated_time,
                conditions=lead_input.conditions if lead_input.conditions else [],
                other_condition_text=lead_input.other_condition_text or "",
            )
        except Exception as e:
            # Log error but don't fail the request
            # Notifications are nice-to-have, not critical
            import logging
            logging.error(f"Failed to send notification: {e}")
            pass

        # Create audit log entry (without PHI)
        audit_service = AuditService(db)
        audit_service.log_create(
            table_name="leads",
            record_id=lead.id,
            ip_address=client_ip,
            endpoint="/api/leads/submit",
            request_method="POST",
            user_agent=user_agent,
            new_values={
                "condition": lead_data.condition.value,
                "priority": priority.value,
                "in_service_area": in_service_area,
                "phi_fields": "[REDACTED]",  # Never log PHI
            },
        )

        _submit_response = LeadSubmitResponse(
            success=True,
            message=message,
            lead_id=lead.id,
            priority=priority,
            estimated_response_time=estimated_time,
        )

        # =====================================================================
        # Store dedup keys in Redis AFTER successful creation
        # submission_id key: 24h TTL (covers re-sends on flaky connections)
        # content hash key: 5-minute TTL (covers rapid-fire duplicate forms)
        # =====================================================================
        _response_payload = _submit_response.model_dump(mode="json")
        try:
            _cache = get_cache()
            if sub_id:
                _cache.set(_redis_key, _response_payload, ttl=86400)  # 24 hours
            _cache.set(_content_key, _response_payload, ttl=300)  # 5 minutes
        except Exception:
            pass  # Non-fatal — worst case we get a duplicate, which is handled at DB level

        return _submit_response

    except ValueError as e:
        # Validation error
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        # Log error without PHI
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your submission. Please try again.",
        )


# =============================================================================
# Dashboard Endpoints (for future authentication)
# =============================================================================

@router.get(
    "",
    response_model=PaginatedResponse,
    summary="List Leads",
    description="Get paginated list of leads for dashboard.",
    dependencies=[Depends(get_current_user)],
)
async def list_leads(
    request: Request,
    db: Session = Depends(get_db),
    page: int = 1,
    page_size: int = 20,
    priority: Optional[PriorityType] = None,
    status_filter: Optional[LeadStatus] = None,
    contact_outcome_filter: Optional[ContactOutcome] = None,
    in_service_area: Optional[bool] = None,
    is_referral: Optional[bool] = None,
    search: Optional[str] = None,
    queue_type: Optional[str] = None,
) -> PaginatedResponse:
    """
    List leads with pagination, filtering, and search.

    PERFORMANCE OPTIMIZED:
    - Server-side pagination BEFORE decryption
    - Only decrypt leads in the current page
    - Count queries use indexes efficiently
    - Robust error handling for enum mismatches

    Args:
        request: FastAPI request
        db: Database session
        page: Page number (1-indexed)
        page_size: Items per page (max 100)
        priority: Optional priority filter
        status_filter: Optional status filter
        contact_outcome_filter: Optional contact outcome filter (NEW, ANSWERED, NO_ANSWER, etc.)
        in_service_area: Optional service area filter
        is_referral: Optional filter for referral leads only
        search: Optional search query (searches lead_number only for performance)

    Returns:
        Paginated list of leads
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Validate and cap page_size
        # NOTE: Raised to 1000 so the coordinator dashboard can fetch all leads in
        # one request (currently 188 leads). The previous cap of 100 caused the
        # coordinator to see only the first 100/188 leads, making scheduled-queue
        # and completed-queue counts (13, 3) diverge from analytics (23, 7).
        # Analytics queries the full DB and was correct; the coordinator was wrong.
        page_size = min(page_size, 1000)
        
        # Validate pagination params
        if page < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Page number must be at least 1"
            )
        if page_size < 1 or page_size > 1000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Page size must be between 1 and 1000"
            )

        # Build base query - exclude soft-deleted leads
        query = db.query(Lead).filter(Lead.deleted_at.is_(None))

        # Apply filters (all use indexed columns)
        if priority:
            query = query.filter(Lead.priority == priority)
        if status_filter:
            query = query.filter(Lead.status == status_filter)
        if contact_outcome_filter:
            query = query.filter(Lead.contact_outcome == contact_outcome_filter)
        if in_service_area is not None:
            query = query.filter(Lead.in_service_area == in_service_area)
        if is_referral is not None:
            query = query.filter(Lead.is_referral == is_referral)

        # Search by lead_number (indexed, non-PHI field)
        # For PHI search, use a dedicated search endpoint with rate limiting
        if search:
            search_term = search.strip()
            if search_term:
                query = query.filter(Lead.lead_number.ilike(f"%{search_term}%"))

        # Apply server-side queue filter (coordinator workflow routing).
        # Mirrors filterLeadsByQueue() in QueueSidebar.tsx so each coordinator
        # queue shows exactly the right leads without client-side filtering.
        if queue_type:
            query = apply_queue_filter(query, queue_type)

        # Get total count efficiently (single COUNT query with filters)
        total = query.count()

        # Calculate pagination
        total_pages = (total + page_size - 1) // page_size if total > 0 else 1
        offset = (page - 1) * page_size

        # Get only the leads for current page (LIMIT/OFFSET with index)
        # Use joinedload to eagerly load referring_provider for thread pool processing
        # Sort by last_updated_at DESC NULLS FIRST (new untouched leads first, then recently updated)
        paginated_leads = (
            query
            .options(joinedload(Lead.referring_provider))
            .order_by(desc(Lead.last_updated_at).nulls_first(), desc(Lead.created_at))
            .offset(offset)
            .limit(page_size)
            .all()
        )

        # PERFORMANCE FIX: Batch decrypt using ThreadPoolExecutor
        # This parallelizes decryption across CPU cores for ~5x speedup
        def decrypt_single_lead(lead):
            """Decrypt PHI for a single lead (runs in thread pool)."""
            decrypted = EncryptionService.decrypt_lead_phi(lead)
            return LeadListResponse(
                id=lead.id,
                lead_number=lead.lead_number,
                first_name=decrypted["first_name"],
                last_name=decrypted["last_name"],
                email=decrypted["email"],
                phone=decrypted["phone"],
                condition=lead.condition,
                # Multi-condition support
                conditions=lead.conditions if lead.conditions else [],
                other_condition_text=lead.other_condition_text,
                # Preferred contact method
                preferred_contact_method=lead.preferred_contact_method,
                score=lead.score,
                priority=lead.priority,
                status=lead.status,
                in_service_area=lead.in_service_area,
                created_at=lead.created_at,
                scheduled_callback_at=lead.scheduled_callback_at,
                contact_outcome=lead.contact_outcome or ContactOutcome.NEW,
                contact_attempts=lead.contact_attempts or 0,
                last_contact_attempt=lead.last_contact_attempt,
                # Referral tracking fields
                is_referral=lead.is_referral if lead.is_referral else False,
                referring_provider_id=lead.referring_provider_id,
                referring_provider_name=lead.referring_provider.name if lead.referring_provider else None,
                follow_up_reason=lead.follow_up_reason,
                # Source field — identifies lead origin (widget, jotform, manual, etc.)
                source=lead.source.value if lead.source else None,
                last_updated_at=lead.last_updated_at,
            )

        # Use thread pool for concurrent decryption (max 8 workers)
        with ThreadPoolExecutor(max_workers=8) as executor:
            items = list(executor.map(decrypt_single_lead, paginated_leads))

        # Batch audit logging (single entry for page access)
        if paginated_leads:
            audit_service = AuditService(db)
            audit_service.log_read(
                table_name="leads",
                record_id=paginated_leads[0].id,  # Log first lead ID as reference
                ip_address=get_client_ip(request),
                endpoint="/api/leads",
                request_method="GET",
                user_agent=get_user_agent(request),
            )

        return PaginatedResponse(
            items=[item.model_dump() for item in items],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        )
    
    except LookupError as e:
        # Enum mismatch error - log and return 500 with helpful message
        logger.error(f"Enum mismatch error in list_leads: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database contains invalid enum values. Please contact support."
        )
    except Exception as e:
        # Generic error handler - log without exposing internals
        logger.error(f"Error in list_leads: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while loading leads. Please try again."
        )


# =============================================================================
# PHI Search Endpoint (Rate Limited)
# =============================================================================

@router.get(
    "/search",
    response_model=PaginatedResponse,
    summary="Search Leads by PHI",
    description="Search leads by phone, email, or name (rate limited for security).",
    dependencies=[Depends(get_current_user)],
)
async def search_leads_phi(
    request: Request,
    db: Session = Depends(get_db),
    q: str = "",
    page: int = 1,
    page_size: int = 20,
) -> PaginatedResponse:
    """
    Search leads by PHI fields (phone, email, name).

    This endpoint is separate and rate-limited because it requires
    decrypting all leads to search. Should be used sparingly.

    For large datasets, consider implementing:
    - Elasticsearch with encrypted search
    - Blind index search patterns

    Args:
        request: FastAPI request
        db: Database session
        q: Search query
        page: Page number
        page_size: Items per page

    Returns:
        Matching leads
    """
    if not q or len(q.strip()) < 2:
        return PaginatedResponse(
            items=[],
            total=0,
            page=page,
            page_size=page_size,
            total_pages=0,
            has_next=False,
            has_previous=False,
        )

    search_lower = q.lower().strip()
    page_size = min(page_size, 50)  # Cap at 50 for search

    # For PHI search, we need to scan leads in batches
    # This is slower but more secure than keeping decrypted data
    batch_size = 500
    offset = 0
    matching_leads = []

    # Scan in batches until we have enough results for pagination
    # Get enough for current page + one more
    max_results = (page * page_size) + page_size

    while len(matching_leads) < max_results:
        batch = (
            db.query(Lead)
            .filter(Lead.deleted_at.is_(None))  # GAP 2 FIX: exclude soft-deleted leads from PHI search
            .order_by(desc(Lead.created_at))
            .offset(offset)
            .limit(batch_size)
            .all()
        )

        if not batch:
            break

        for lead in batch:
            decrypted = EncryptionService.decrypt_lead_phi(lead)
            phone = (decrypted.get("phone", "") or "").lower()
            email = (decrypted.get("email", "") or "").lower()
            first_name = (decrypted.get("first_name", "") or "").lower()
            last_name = (decrypted.get("last_name", "") or "").lower()
            full_name = f"{first_name} {last_name}".strip()

            if (
                search_lower in phone or
                search_lower in email or
                search_lower in full_name or
                search_lower in first_name or
                search_lower in last_name
            ):
                matching_leads.append((lead, decrypted))

                if len(matching_leads) >= max_results:
                    break

        offset += batch_size

    # Apply pagination to results
    total = len(matching_leads)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_leads = matching_leads[start_idx:end_idx]

    # Convert to response
    items = []
    for lead, decrypted in paginated_leads:
        items.append(
            LeadListResponse(
                id=lead.id,
                lead_number=lead.lead_number,
                first_name=decrypted["first_name"],
                last_name=decrypted["last_name"],
                email=decrypted["email"],
                phone=decrypted["phone"],
                condition=lead.condition,
                score=lead.score,
                priority=lead.priority,
                status=lead.status,
                in_service_area=lead.in_service_area,
                created_at=lead.created_at,
                scheduled_callback_at=lead.scheduled_callback_at,
                contact_outcome=lead.contact_outcome or ContactOutcome.NEW,
                contact_attempts=lead.contact_attempts or 0,
                last_contact_attempt=lead.last_contact_attempt,
            )
        )

    total_pages = (total + page_size - 1) // page_size if total > 0 else 1

    return PaginatedResponse(
        items=[item.model_dump() for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_previous=page > 1,
    )


# =============================================================================
# Deleted Leads List (Admin Only) — MUST be before /{lead_id} to avoid UUID conflict
# =============================================================================

@router.get(
    "/deleted",
    response_model=PaginatedResponse,
    summary="List Deleted Leads",
    description="Get paginated list of soft-deleted leads for admin recovery view.",
    dependencies=[Depends(require_role("administrator"))],
)
async def list_deleted_leads(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    page: int = 1,
    page_size: int = 50,
) -> PaginatedResponse:
    """
    List soft-deleted leads for the admin Deleted Leads recovery view.

    Redis-cached for 15 s per page so rapid navigation doesn't hammer the
    DB with repeated decryption work.  The HTTP response carries
    Cache-Control: private, no-store so the *browser* never caches PHI,
    while the server-side Redis cache absorbs repeated requests within the
    same 15-second window.

    Cache is automatically invalidated whenever a lead is soft-deleted or
    restored (both callers invoke cache.invalidate_on_lead_change()).
    """
    import logging
    _logger = logging.getLogger(__name__)

    try:
        page_size = min(page_size, 100)

        # ── Server-side Redis cache (15 s TTL) ────────────────────────────
        # Key includes page+size so each page has its own slot.
        _cache_key = f"deleted_leads:page:{page}:size:{page_size}"
        try:
            _cache = get_cache()
            _cached = _cache.get(_cache_key)
            if _cached:
                # PHI must NEVER be stored in a client-visible cache.
                response.headers["Cache-Control"] = "private, no-store"
                return PaginatedResponse(**_cached)
        except Exception:
            pass  # Redis unavailable — fall through to DB

        # ── DB query ──────────────────────────────────────────────────────
        query = db.query(Lead).filter(Lead.deleted_at.isnot(None))
        total = query.count()
        total_pages = (total + page_size - 1) // page_size if total > 0 else 1
        offset = (page - 1) * page_size

        paginated_leads = (
            query
            .options(joinedload(Lead.referring_provider))
            .order_by(desc(Lead.deleted_at))
            .offset(offset)
            .limit(page_size)
            .all()
        )

        def decrypt_deleted_lead(lead):
            decrypted = EncryptionService.decrypt_lead_phi(lead)
            return {
                "id": str(lead.id),
                "lead_number": lead.lead_number,
                "first_name": decrypted["first_name"],
                "last_name": decrypted["last_name"],
                "email": decrypted["email"],
                "phone": decrypted["phone"],
                "condition": lead.condition.value if lead.condition else None,
                "conditions": lead.conditions if lead.conditions else [],
                "priority": lead.priority.value if lead.priority else None,
                "status": lead.status.value if lead.status else None,
                "created_at": lead.created_at.isoformat() if lead.created_at else None,
                "deleted_at": lead.deleted_at.isoformat() if lead.deleted_at else None,
                "is_referral": lead.is_referral if lead.is_referral else False,
                "referring_provider_name": lead.referring_provider.name if lead.referring_provider else None,
            }

        with ThreadPoolExecutor(max_workers=8) as executor:
            items = list(executor.map(decrypt_deleted_lead, paginated_leads))

        _payload = dict(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        )

        # Store in Redis for 15 s — this result contains decrypted PHI
        # which is acceptable in a server-side cache.
        try:
            _cache = get_cache()
            _cache.set(_cache_key, _payload, ttl=15)
        except Exception:
            pass  # Non-fatal — cache miss on next request is fine

        # PHI must NEVER be stored in a client-visible cache.
        response.headers["Cache-Control"] = "private, no-store"
        return PaginatedResponse(**_payload)

    except Exception as e:
        _logger.error(f"Error in list_deleted_leads: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while loading deleted leads.",
        )


# =============================================================================
# Manual Lead Creation Endpoint (Coordinator Entry)
# =============================================================================

@router.post(
    "/manual",
    status_code=status.HTTP_201_CREATED,
    summary="Create Lead Manually",
    description="Allows coordinators to manually add a lead from the dashboard.",
    dependencies=[Depends(require_role("administrator", "coordinator"))],
)
async def create_manual_lead(
    lead_data: ManualLeadCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """
    Create a new lead manually from the coordinator dashboard.

    Only first_name is required. Missing DB-required fields are filled
    with sensible placeholder values so the coordinator can add details later.

    - source = manual
    - priority = HOT (manual leads get immediate attention)
    - status = NEW
    - score = 50 (neutral baseline)

    Args:
        lead_data: ManualLeadCreate schema
        request: FastAPI request
        db: Database session

    Returns:
        Success response with lead_id and lead_number
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        # Generate unique lead number using the same logic as all other leads
        lead_number = generate_unique_lead_number(db)

        # Encrypt PHI fields — use placeholder values for missing required fields
        first_name_enc = EncryptionService.encrypt_field(lead_data.first_name)
        last_name_enc = EncryptionService.encrypt_field(lead_data.last_name) if lead_data.last_name else None
        email_enc = EncryptionService.encrypt_field(lead_data.email) if lead_data.email else EncryptionService.encrypt_field("manual-entry@placeholder.local")
        phone_enc = EncryptionService.encrypt_field(lead_data.phone) if lead_data.phone else EncryptionService.encrypt_field("+10000000000")

        # Determine condition and build conditions array
        # If coordinator selected a condition, use it; otherwise leave empty = "Not Provided"
        condition = lead_data.condition if lead_data.condition else ConditionType.OTHER

        # Determine condition_other text ONLY when coordinator explicitly provided it
        condition_other_text: str | None = None
        if lead_data.condition_other:
            # User provided explicit "Other" description
            condition_other_text = lead_data.condition_other

        # Normalize conditions array to lowercase to match widget-submitted leads
        # Widget leads store: ["depression", "anxiety", "other"]
        # Manual leads must follow the same convention.
        # CRITICAL: When no condition was selected (lead_data.condition is None),
        # store an EMPTY array [] so the frontend can display "Not Provided"
        # instead of a placeholder string. Empty array is the agreed signal.
        if lead_data.condition:
            normalized_conditions = [condition.value.lower()]
        else:
            normalized_conditions = []  # Empty = "Not Provided" in frontend

        # Build lead record with proper defaults for all required NOT NULL columns
        lead = Lead(
            lead_number=lead_number,
            first_name_encrypted=first_name_enc,
            last_name_encrypted=last_name_enc,
            email_encrypted=email_enc,
            phone_encrypted=phone_enc,
            condition=condition,
            condition_other=condition_other_text,
            # Multi-condition support — normalized lowercase to match widget leads
            conditions=normalized_conditions,
            # Store "Other" description in BOTH fields so it displays correctly
            # in every view (pipeline table uses other_condition_text, detail modal uses condition_other)
            other_condition_text=condition_other_text if condition == ConditionType.OTHER else None,
            symptom_duration=lead_data.symptom_duration if lead_data.symptom_duration else DurationType.LESS_THAN_6_MONTHS,
            prior_treatments=lead_data.prior_treatments if lead_data.prior_treatments else [],
            has_insurance=lead_data.has_insurance if lead_data.has_insurance is not None else False,
            insurance_provider=lead_data.insurance_provider,
            zip_code=lead_data.zip_code if lead_data.zip_code else "00000",
            in_service_area=_check_service_area(lead_data.zip_code),
            urgency=lead_data.urgency if lead_data.urgency else UrgencyType.EXPLORING,
            hipaa_consent=True,  # Coordinator-entered leads have implicit consent
            hipaa_consent_timestamp=datetime.now(timezone.utc),
            sms_consent=False,  # Explicit default for NOT NULL column
            # Scoring — neutral baseline for manual leads
            score=50,
            lead_score=50,
            # CRITICAL: All manual leads get HOT priority — enforced at the data layer
            priority=PriorityType.HOT,
            # Status
            status=LeadStatus.NEW,
            # CRITICAL FIX: contact_outcome must NOT be None — column is NOT NULL
            # This was the root cause of "Failed to create lead" error
            contact_outcome=ContactOutcome.NEW,
            # Source tracking
            source=LeadSource.manual,
            # Referral defaults for NOT NULL column
            is_referral=False,
            # Notes from coordinator
            notes=lead_data.notes,
            # Metadata
            ip_address_hash=EncryptionService.hash_ip(get_client_ip(request)),
            user_agent=get_user_agent(request),
        )

        db.add(lead)
        db.commit()
        db.refresh(lead)

        # Invalidate cache
        try:
            cache = get_cache()
            cache.invalidate_on_lead_change()
        except Exception:
            pass

        # Audit log
        try:
            audit_service = AuditService(db)
            audit_service.log_create(
                table_name="leads",
                record_id=lead.id,
                ip_address=get_client_ip(request),
                endpoint="/api/leads/manual",
                request_method="POST",
                user_agent=get_user_agent(request),
                new_values={
                    "lead_number": lead_number,
                    "source": "manual",
                    "priority": "HOT",
                    "phi_fields": "[REDACTED]",
                },
            )
        except Exception as e:
            logger.warning(f"Audit log failed for manual lead: {e}")

        return {
            "success": True,
            "message": f"Lead {lead_number} created successfully.",
            "lead_id": str(lead.id),
            "lead_number": lead_number,
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Manual lead creation error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create lead: {str(e)}",
        )


# =============================================================================
# Daily Digest Manual Trigger Endpoint (Admin Only)
# =============================================================================

@router.post(
    "/digest-trigger",
    summary="Trigger Daily Digest Email",
    description="Manually trigger the daily lead digest email. Admin only.",
    dependencies=[Depends(require_role("administrator"))],
)
async def trigger_daily_digest() -> dict:
    """
    Manually trigger the daily lead digest email via Celery async task.

    Useful for testing or sending an ad-hoc digest outside the 7AM MST schedule.

    Returns:
        Success response with Celery task ID
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        from ..tasks.lead_tasks import send_daily_lead_digest

        result = send_daily_lead_digest.delay()
        logger.info(f"Daily digest triggered manually, task_id={result.id}")

        return {
            "success": True,
            "message": "Daily digest email task queued successfully.",
            "task_id": str(result.id),
        }
    except Exception as e:
        logger.error(f"Failed to trigger daily digest: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger digest: {str(e)}",
        )


# =============================================================================
# Queue Summary Endpoint — MUST be before /{lead_id} to avoid UUID conflict
# =============================================================================

@router.get(
    "/queue-summary",
    summary="Queue Summary Counts",
    description="Returns lead counts for each coordinator queue. Redis-cached for 10s.",
    dependencies=[Depends(get_current_user)],
)
async def get_queue_summary(
    db: Session = Depends(get_db),
) -> dict:
    """
    Return lead count for every coordinator queue in a single response.

    Used by:
    - Coordinator Sidebar badges (shows how many leads are in each queue)
    - CoordinatorDashboard metrics cards (accurate "In Queue" count)

    Redis-cached for 10 seconds to reduce DB load under concurrent usage.
    The cache is automatically invalidated whenever leads are modified via
    cache.invalidate_on_lead_change() which clears 'leads:*' pattern keys.

    Returns:
        Dict mapping queue name → count, e.g.:
        {"all": 165, "new": 45, "contacted": 30, ..., "hot": 35}
    """
    import logging
    _logger = logging.getLogger(__name__)

    _QUEUE_TYPES = [
        "all", "new", "contacted", "follow_up", "callback",
        "scheduled", "completed", "unreachable", "not_interested",
        "hot", "medium", "low",
    ]

    try:
        # Try Redis cache first (10-second TTL)
        try:
            cache = get_cache()
            cached = cache.get("leads:queue_summary")
            if cached:
                return cached
        except Exception:
            pass  # Redis down — fall through to DB

        # One COUNT query per queue type — each uses an indexed WHERE clause
        base = db.query(Lead).filter(Lead.deleted_at.is_(None))
        result = {qt: apply_queue_filter(base, qt).count() for qt in _QUEUE_TYPES}

        # Cache for 10 seconds
        try:
            cache = get_cache()
            cache.set("leads:queue_summary", result, ttl=10)
        except Exception:
            pass  # Non-fatal

        return result

    except Exception as e:
        _logger.error(f"queue-summary error: {e}", exc_info=True)
        # Return zeros rather than 500 so the sidebar still renders
        return {qt: 0 for qt in _QUEUE_TYPES}


@router.get(
    "/{lead_id}",
    response_model=LeadResponse,
    summary="Get Lead Details",
    description="Get detailed information about a specific lead.",
    dependencies=[Depends(get_current_user)],
)
async def get_lead(
    lead_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> LeadResponse:
    """
    Get detailed lead information by ID.

    Args:
        lead_id: UUID of lead to retrieve
        request: FastAPI request
        db: Database session

    Returns:
        Full lead details with decrypted PHI

    Raises:
        HTTPException: If lead not found
    """
    # Fetch lead (exclude soft-deleted)
    lead = db.query(Lead).filter(
        Lead.id == lead_id,
        Lead.deleted_at.is_(None)
    ).first()

    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    # Log audit
    audit_service = AuditService(db)
    audit_service.log_read(
        table_name="leads",
        record_id=lead.id,
        ip_address=get_client_ip(request),
        endpoint=f"/api/leads/{lead_id}",
        request_method="GET",
        user_agent=get_user_agent(request),
    )

    # Decrypt PHI
    decrypted = EncryptionService.decrypt_lead_phi(lead)

    return LeadResponse(
        id=lead.id,
        first_name=decrypted["first_name"],
        last_name=decrypted["last_name"],
        email=decrypted["email"],
        phone=decrypted["phone"],
        condition=lead.condition,
        condition_other=lead.condition_other,
        symptom_duration=lead.symptom_duration,
        prior_treatments=lead.prior_treatments if lead.prior_treatments else [],
        has_insurance=lead.has_insurance,
        insurance_provider=lead.insurance_provider,
        zip_code=lead.zip_code,
        in_service_area=lead.in_service_area,
        urgency=lead.urgency,
        hipaa_consent=lead.hipaa_consent,
        hipaa_consent_timestamp=lead.hipaa_consent_timestamp,
        privacy_consent_timestamp=lead.privacy_consent_timestamp,
        sms_consent=lead.sms_consent,
        sms_consent_timestamp=lead.sms_consent_timestamp,
        score=lead.score,
        priority=lead.priority,
        status=lead.status,
        notes=lead.notes,
        utm_source=lead.utm_source,
        utm_medium=lead.utm_medium,
        utm_campaign=lead.utm_campaign,
        created_at=lead.created_at,
        updated_at=lead.updated_at,
        contacted_at=lead.contacted_at,
        scheduled_callback_at=lead.scheduled_callback_at,
        scheduled_notes=lead.scheduled_notes,
        contact_method=lead.contact_method,
        last_contact_attempt=lead.last_contact_attempt,
        contact_attempts=lead.contact_attempts,
        next_follow_up_at=lead.next_follow_up_at,
        tms_therapy_interest=lead.tms_therapy_interest,
    )


# =============================================================================
# Scheduling Endpoints
# =============================================================================

@router.post(
    "/{lead_id}/schedule",
    response_model=LeadResponse,
    summary="Schedule Callback or Consultation",
    description="Schedule a callback or consultation for a lead. Callbacks stay in Follow-up Queue; Consultations move to Scheduled Queue.",
    dependencies=[Depends(require_role("administrator", "coordinator"))],
)
async def schedule_callback(
    lead_id: UUID,
    schedule_data: ScheduleCallbackRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> LeadResponse:
    """
    Schedule a callback or consultation for a lead.
    
    CRITICAL ROUTING LOGIC:
    - schedule_type='callback': Sets contact_outcome=CALLBACK_REQUESTED, keeps in Follow-up Queue
    - schedule_type='consultation': Sets status=SCHEDULED, contact_outcome=SCHEDULED, moves to Scheduled Queue

    Args:
        lead_id: UUID of lead to schedule
        schedule_data: Scheduling information including schedule_type
        request: FastAPI request
        db: Database session

    Returns:
        Updated lead details

    Raises:
        HTTPException: If lead not found
    """
    # Fetch lead
    lead = db.query(Lead).filter(Lead.id == lead_id).first()

    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    # Store old values for audit
    old_values = {
        "scheduled_callback_at": str(lead.scheduled_callback_at) if lead.scheduled_callback_at else None,
        "scheduled_notes": lead.scheduled_notes,
        "contact_method": lead.contact_method.value if lead.contact_method else None,
        "status": lead.status.value if lead.status else None,
        "contact_outcome": lead.contact_outcome.value if lead.contact_outcome else None,
    }

    # =========================================================================
    # CRITICAL: Clear ALL old transition fields first, then set new ones.
    # This prevents stale tags (e.g., "Cancelled Appointment", "Unreachable")
    # from carrying over when a lead moves to a new queue.
    # =========================================================================
    clear_lead_transition_fields(lead)

    # Now set scheduling fields on the clean slate
    lead.scheduled_callback_at = schedule_data.scheduled_callback_at
    lead.scheduled_notes = schedule_data.scheduled_notes
    lead.contact_method = schedule_data.contact_method

    # =========================================================================
    # CRITICAL: Route based on schedule_type
    # =========================================================================
    schedule_type = (schedule_data.schedule_type or "callback").lower().strip()
    
    if schedule_type == "consultation":
        # CONSULTATION: Move to Scheduled Queue
        lead.status = LeadStatus.SCHEDULED
        lead.contact_outcome = ContactOutcome.SCHEDULED
        lead.contacted_at = datetime.now(timezone.utc)
    else:
        # CALLBACK: Stay in Follow-up/Callback Queue
        if lead.status == LeadStatus.NEW:
            lead.status = LeadStatus.CONTACTED
        lead.contact_outcome = ContactOutcome.CALLBACK_REQUESTED
        lead.follow_up_reason = "Callback Requested"
        lead.contacted_at = datetime.now(timezone.utc)
        lead.next_follow_up_at = schedule_data.scheduled_callback_at

    # Mark activity timestamp
    mark_lead_activity(lead)
    
    db.commit()
    db.refresh(lead)

    # Invalidate cache to ensure dashboard metrics are accurate
    try:
        cache = get_cache()
        cache.invalidate_on_lead_change()
    except Exception:
        pass  # Don't fail the request if cache invalidation fails

    # Log audit
    audit_service = AuditService(db)
    audit_service.log_update(
        table_name="leads",
        record_id=lead.id,
        ip_address=get_client_ip(request),
        endpoint=f"/api/leads/{lead_id}/schedule",
        request_method="POST",
        user_agent=get_user_agent(request),
        old_values=old_values,
        new_values={
            "scheduled_callback_at": str(schedule_data.scheduled_callback_at),
            "scheduled_notes": schedule_data.scheduled_notes,
            "contact_method": schedule_data.contact_method.value,
        },
    )

    # Return updated lead
    decrypted = EncryptionService.decrypt_lead_phi(lead)

    return LeadResponse(
        id=lead.id,
        first_name=decrypted["first_name"],
        last_name=decrypted["last_name"],
        email=decrypted["email"],
        phone=decrypted["phone"],
        condition=lead.condition,
        condition_other=lead.condition_other,
        symptom_duration=lead.symptom_duration,
        prior_treatments=lead.prior_treatments if lead.prior_treatments else [],
        has_insurance=lead.has_insurance,
        insurance_provider=lead.insurance_provider,
        zip_code=lead.zip_code,
        in_service_area=lead.in_service_area,
        urgency=lead.urgency,
        hipaa_consent=lead.hipaa_consent,
        hipaa_consent_timestamp=lead.hipaa_consent_timestamp,
        privacy_consent_timestamp=lead.privacy_consent_timestamp,
        sms_consent=lead.sms_consent,
        sms_consent_timestamp=lead.sms_consent_timestamp,
        score=lead.score,
        priority=lead.priority,
        status=lead.status,
        notes=lead.notes,
        utm_source=lead.utm_source,
        utm_medium=lead.utm_medium,
        utm_campaign=lead.utm_campaign,
        created_at=lead.created_at,
        updated_at=lead.updated_at,
        contacted_at=lead.contacted_at,
        scheduled_callback_at=lead.scheduled_callback_at,
        scheduled_notes=lead.scheduled_notes,
        contact_method=lead.contact_method,
        last_contact_attempt=lead.last_contact_attempt,
        contact_attempts=lead.contact_attempts,
        next_follow_up_at=lead.next_follow_up_at,
    )


@router.post(
    "/{lead_id}/contact-attempt",
    response_model=LeadResponse,
    summary="Log Contact Attempt",
    description="Log a contact attempt for a lead.",
    dependencies=[Depends(require_role("administrator", "coordinator"))],
)
async def log_contact_attempt(
    lead_id: UUID,
    attempt_data: LogContactAttemptRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> LeadResponse:
    """
    Log a contact attempt for a lead.

    Args:
        lead_id: UUID of lead
        attempt_data: Contact attempt information
        request: FastAPI request
        db: Database session

    Returns:
        Updated lead details

    Raises:
        HTTPException: If lead not found
    """
    # Fetch lead
    lead = db.query(Lead).filter(Lead.id == lead_id).first()

    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    # Update contact tracking
    lead.last_contact_attempt = datetime.now(timezone.utc)
    lead.contact_attempts = (lead.contact_attempts or 0) + 1
    lead.contact_method = attempt_data.contact_method

    # Update notes if provided
    if attempt_data.notes:
        existing_notes = lead.notes or ""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        new_note = f"[{timestamp}] Contact attempt ({attempt_data.contact_method.value}): {attempt_data.notes}"
        lead.notes = f"{new_note}\n{existing_notes}" if existing_notes else new_note

    # Set next follow-up if not reached
    if not attempt_data.was_successful and attempt_data.next_follow_up_at:
        lead.next_follow_up_at = attempt_data.next_follow_up_at

    # Update status based on success
    if attempt_data.was_successful:
        if lead.status == LeadStatus.NEW or lead.status == LeadStatus.CONTACTED:
            lead.status = LeadStatus.CONTACTED
        lead.contacted_at = datetime.now(timezone.utc)
        lead.next_follow_up_at = None  # Clear follow-up if successful

    # Mark activity timestamp
    mark_lead_activity(lead)
    
    db.commit()
    db.refresh(lead)

    # Invalidate cache to ensure dashboard metrics are accurate
    try:
        cache = get_cache()
        cache.invalidate_on_lead_change()
    except Exception:
        pass  # Don't fail the request if cache invalidation fails

    # Log audit
    audit_service = AuditService(db)
    audit_service.log_update(
        table_name="leads",
        record_id=lead.id,
        ip_address=get_client_ip(request),
        endpoint=f"/api/leads/{lead_id}/contact-attempt",
        request_method="POST",
        user_agent=get_user_agent(request),
        old_values=None,
        new_values={
            "contact_method": attempt_data.contact_method.value,
            "was_successful": attempt_data.was_successful,
            "contact_attempts": lead.contact_attempts,
        },
    )

    # Return updated lead
    decrypted = EncryptionService.decrypt_lead_phi(lead)

    return LeadResponse(
        id=lead.id,
        first_name=decrypted["first_name"],
        last_name=decrypted["last_name"],
        email=decrypted["email"],
        phone=decrypted["phone"],
        condition=lead.condition,
        condition_other=lead.condition_other,
        symptom_duration=lead.symptom_duration,
        prior_treatments=lead.prior_treatments if lead.prior_treatments else [],
        has_insurance=lead.has_insurance,
        insurance_provider=lead.insurance_provider,
        zip_code=lead.zip_code,
        in_service_area=lead.in_service_area,
        urgency=lead.urgency,
        hipaa_consent=lead.hipaa_consent,
        hipaa_consent_timestamp=lead.hipaa_consent_timestamp,
        privacy_consent_timestamp=lead.privacy_consent_timestamp,
        sms_consent=lead.sms_consent,
        sms_consent_timestamp=lead.sms_consent_timestamp,
        score=lead.score,
        priority=lead.priority,
        status=lead.status,
        notes=lead.notes,
        utm_source=lead.utm_source,
        utm_medium=lead.utm_medium,
        utm_campaign=lead.utm_campaign,
        created_at=lead.created_at,
        updated_at=lead.updated_at,
        contacted_at=lead.contacted_at,
        scheduled_callback_at=lead.scheduled_callback_at,
        scheduled_notes=lead.scheduled_notes,
        contact_method=lead.contact_method,
        last_contact_attempt=lead.last_contact_attempt,
        contact_attempts=lead.contact_attempts,
        next_follow_up_at=lead.next_follow_up_at,
    )


@router.get(
    "/scheduled/calendar",
    response_model=List[ScheduledLeadResponse],
    summary="Get Scheduled Leads",
    description="Get leads with scheduled callbacks for calendar view.",
    dependencies=[Depends(get_current_user)],
)
async def get_scheduled_leads(
    request: Request,
    db: Session = Depends(get_db),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> List[ScheduledLeadResponse]:
    """
    Get leads with scheduled callbacks for calendar view.

    Args:
        request: FastAPI request
        db: Database session
        start_date: Optional start date filter
        end_date: Optional end date filter

    Returns:
        List of scheduled leads
    """
    # Build query for leads with scheduled callbacks, excluding soft-deleted leads.
    # Without the deleted_at filter, soft-deleted leads with a future callback
    # would appear in the calendar view — exposing PHI for deleted records.
    query = db.query(Lead).filter(
        Lead.scheduled_callback_at.isnot(None),
        Lead.deleted_at.is_(None),
    )

    # Apply date filters if provided
    if start_date:
        query = query.filter(Lead.scheduled_callback_at >= start_date)
    if end_date:
        query = query.filter(Lead.scheduled_callback_at <= end_date)

    # Order by scheduled time
    leads = query.order_by(Lead.scheduled_callback_at).all()

    # Convert to response format
    items = []
    for lead in leads:
        decrypted = EncryptionService.decrypt_lead_phi(lead)
        items.append(
            ScheduledLeadResponse(
                id=lead.id,
                lead_number=lead.lead_number,
                first_name=decrypted["first_name"],
                last_name=decrypted["last_name"],
                condition=lead.condition,
                priority=lead.priority,
                status=lead.status,
                scheduled_callback_at=lead.scheduled_callback_at,
                scheduled_notes=lead.scheduled_notes,
                contact_method=lead.contact_method,
                contact_attempts=lead.contact_attempts,
                phone=decrypted["phone"],
            )
        )

    return items


@router.patch(
    "/{lead_id}/status",
    response_model=LeadResponse,
    summary="Update Lead Status",
    description="Update the status of a lead.",
    dependencies=[Depends(require_role("administrator", "coordinator"))],
)
async def update_lead_status(
    lead_id: UUID,
    new_status: LeadStatus,
    request: Request,
    db: Session = Depends(get_db),
) -> LeadResponse:
    """
    Update lead status.

    Protected by role-based authentication via require_role() dependency.

    Args:
        lead_id: UUID of lead to update
        new_status: New status value
        request: FastAPI request
        db: Database session

    Returns:
        Updated lead details

    Raises:
        HTTPException: If lead not found
    """
    # Fetch lead
    lead = db.query(Lead).filter(Lead.id == lead_id).first()

    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    # Store old status for audit
    old_status = lead.status

    # Check if this is a referral lead transitioning to a converted status
    # Converted statuses: SCHEDULED, CONSULTATION_COMPLETE, TREATMENT_STARTED
    converted_statuses = [LeadStatus.SCHEDULED,
                          LeadStatus.CONSULTATION_COMPLETE, LeadStatus.TREATMENT_STARTED]
    was_converted_before = old_status in converted_statuses
    will_be_converted = new_status in converted_statuses

    # =========================================================================
    # CRITICAL: Clear ALL old transition fields when status changes directly.
    # This prevents stale tags from carrying over (e.g., "Cancelled Appointment"
    # still showing after a lead is moved back to NEW status).
    # =========================================================================
    clear_lead_transition_fields(lead)

    # Update status
    lead.status = new_status
    
    # NOTE: clear_lead_transition_fields already sets contact_outcome=ContactOutcome.NEW
    # This explicit re-assignment is harmless but makes the intent crystal clear.
    lead.contact_outcome = ContactOutcome.NEW
    
    # Mark activity timestamp
    mark_lead_activity(lead)
    
    db.commit()
    db.refresh(lead)

    # CRITICAL: Update provider converted_referrals counter if this is a NEW conversion
    if lead.is_referral and lead.referring_provider_id and will_be_converted and not was_converted_before:
        provider = db.query(ReferringProvider).filter(
            ReferringProvider.id == lead.referring_provider_id
        ).first()
        if provider:
            provider.converted_referrals = (
                provider.converted_referrals or 0) + 1
            db.commit()

    # Invalidate cache to ensure dashboard metrics are accurate
    try:
        cache = get_cache()
        cache.invalidate_on_lead_change()
    except Exception:
        pass  # Don't fail the request if cache invalidation fails

    # Log audit
    audit_service = AuditService(db)
    audit_service.log_update(
        table_name="leads",
        record_id=lead.id,
        ip_address=get_client_ip(request),
        endpoint=f"/api/leads/{lead_id}/status",
        request_method="PATCH",
        user_agent=get_user_agent(request),
        old_values={"status": old_status.value},
        new_values={"status": new_status.value},
    )

    # Return updated lead
    decrypted = EncryptionService.decrypt_lead_phi(lead)

    return LeadResponse(
        id=lead.id,
        first_name=decrypted["first_name"],
        last_name=decrypted["last_name"],
        email=decrypted["email"],
        phone=decrypted["phone"],
        condition=lead.condition,
        condition_other=lead.condition_other,
        symptom_duration=lead.symptom_duration,
        prior_treatments=lead.prior_treatments if lead.prior_treatments else [],
        has_insurance=lead.has_insurance,
        insurance_provider=lead.insurance_provider,
        zip_code=lead.zip_code,
        in_service_area=lead.in_service_area,
        urgency=lead.urgency,
        hipaa_consent=lead.hipaa_consent,
        hipaa_consent_timestamp=lead.hipaa_consent_timestamp,
        privacy_consent_timestamp=lead.privacy_consent_timestamp,
        sms_consent=lead.sms_consent,
        sms_consent_timestamp=lead.sms_consent_timestamp,
        score=lead.score,
        priority=lead.priority,
        status=lead.status,
        notes=lead.notes,
        utm_source=lead.utm_source,
        utm_medium=lead.utm_medium,
        utm_campaign=lead.utm_campaign,
        created_at=lead.created_at,
        updated_at=lead.updated_at,
        contacted_at=lead.contacted_at,
    )


# =============================================================================
# Contact Outcome Endpoints
# =============================================================================

@router.patch(
    "/{lead_id}/contact-outcome",
    response_model=LeadResponse,
    summary="Update Contact Outcome",
    description="Update the contact outcome for a lead after outreach attempt.",
    dependencies=[Depends(require_role("administrator", "coordinator"))],
)
async def update_contact_outcome(
    lead_id: UUID,
    outcome_data: UpdateContactOutcomeRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> LeadResponse:
    """
    Update lead contact outcome.

    Used by coordinators to track outreach results:
    - NEW: Not contacted yet
    - ANSWERED: Spoke with lead, can proceed to schedule
    - NO_ANSWER: Called but no pickup, needs follow-up
    - UNREACHABLE: Wrong number, disconnected, etc.
    - CALLBACK_REQUESTED: Lead asked to call back at specific time
    - NOT_INTERESTED: Lead declined, archive

    Args:
        lead_id: UUID of lead to update
        outcome_data: Contact outcome information
        request: FastAPI request
        db: Database session

    Returns:
        Updated lead details

    Raises:
        HTTPException: If lead not found
    """
    # Fetch lead
    lead = db.query(Lead).filter(Lead.id == lead_id).first()

    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    # Store old values for audit
    old_outcome = lead.contact_outcome.value if lead.contact_outcome else "NEW"

    # =========================================================================
    # CRITICAL: Clear ALL old transition fields first, then set new ones.
    # This prevents stale tags (e.g., "Cancelled Appointment", "No Show")
    # from carrying over when a lead moves to a new queue.
    # =========================================================================
    clear_lead_transition_fields(lead)

    # Update contact outcome on clean slate
    lead.contact_outcome = outcome_data.contact_outcome
    lead.last_contact_attempt = datetime.now(timezone.utc)
    lead.contact_attempts = (lead.contact_attempts or 0) + 1

    # =========================================================================
    # WORKFLOW LOGIC: Outcome → Status + Follow-up Reason + Follow-up Date
    #
    # For New/Contacted leads:
    # | Outcome         | Status →   | follow_up_reason      | follow_up_date |
    # |-----------------|------------|-----------------------|----------------|
    # | Answered        | CONTACTED  | —                     | —              |
    # | No Answer       | CONTACTED  | "No Answer"           | —              |
    # | Unreachable     | CONTACTED  | "Unreachable"         | —              |
    # | Callback        | CONTACTED  | "Callback Requested"  | —              |
    # | Not Interested  | CONTACTED  | "Not Interested"      | +14 days       |
    # =========================================================================
    now = datetime.now(timezone.utc)

    if outcome_data.contact_outcome == ContactOutcome.ANSWERED:
        lead.status = LeadStatus.CONTACTED
        lead.contacted_at = now
        lead.follow_up_reason = None
        lead.follow_up_date = None
    elif outcome_data.contact_outcome == ContactOutcome.NO_ANSWER:
        lead.status = LeadStatus.CONTACTED
        lead.contacted_at = now
        lead.follow_up_reason = "No Answer"
        lead.follow_up_date = now + timedelta(days=1)
    elif outcome_data.contact_outcome == ContactOutcome.UNREACHABLE:
        lead.status = LeadStatus.CONTACTED
        lead.contacted_at = now
        lead.follow_up_reason = "Unreachable"
        lead.follow_up_date = None
    elif outcome_data.contact_outcome == ContactOutcome.CALLBACK_REQUESTED:
        lead.status = LeadStatus.CONTACTED
        lead.contacted_at = now
        lead.follow_up_reason = "Callback Requested"
        # follow_up_date set from next_follow_up_at if provided
    elif outcome_data.contact_outcome == ContactOutcome.NOT_INTERESTED:
        lead.status = LeadStatus.CONTACTED
        lead.contacted_at = now
        lead.follow_up_reason = "Not Interested"
        lead.follow_up_date = now + timedelta(days=14)

    # Set next follow-up for certain outcomes (if explicitly provided by frontend)
    if outcome_data.next_follow_up_at:
        lead.next_follow_up_at = outcome_data.next_follow_up_at

    # Create outcome note ONLY if the coordinator typed something.
    # If no note text was provided, the outcome is already tracked in the
    # lead's contact_outcome and status fields — no need to pollute the
    # Notes section with redundant "Outcome recorded: X" entries.
    note_text_raw = (outcome_data.notes or "").strip()
    if note_text_raw:
        try:
            from ..models.lead_note import LeadNote
            
            user_name = "System"
            user_id = None
            try:
                auth_header = request.headers.get("Authorization", "")
                if auth_header.startswith("Bearer "):
                    from ..core.security import decode_token
                    from ..models.user import User
                    token = auth_header.split(" ")[1]
                    payload = decode_token(token)
                    if payload and "sub" in payload:
                        user = db.query(User).filter(User.id == payload["sub"]).first()
                        if user:
                            user_id = user.id
                            user_name = f"{user.first_name} {user.last_name}".strip() or user.email
            except Exception:
                pass

            auto_note = LeadNote(
                lead_id=lead.id,
                note_text=f"Outcome recorded: {outcome_data.contact_outcome.value} — {note_text_raw}",
                created_by=user_id,
                created_by_name=user_name,
                note_type="outcome",
                related_outcome=outcome_data.contact_outcome.value,
            )
            db.add(auto_note)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to create outcome note: {e}")

    # Mark activity timestamp
    mark_lead_activity(lead)
    
    db.commit()
    db.refresh(lead)

    # Invalidate cache to ensure dashboard metrics are accurate
    try:
        cache = get_cache()
        cache.invalidate_on_lead_change()
    except Exception:
        pass  # Don't fail the request if cache invalidation fails

    # Log audit
    audit_service = AuditService(db)
    audit_service.log_update(
        table_name="leads",
        record_id=lead.id,
        ip_address=get_client_ip(request),
        endpoint=f"/api/leads/{lead_id}/contact-outcome",
        request_method="PATCH",
        user_agent=get_user_agent(request),
        old_values={"contact_outcome": old_outcome},
        new_values={
            "contact_outcome": outcome_data.contact_outcome.value,
            "contact_attempts": lead.contact_attempts,
        },
    )

    # Return updated lead
    decrypted = EncryptionService.decrypt_lead_phi(lead)

    return LeadResponse(
        id=lead.id,
        first_name=decrypted["first_name"],
        last_name=decrypted["last_name"],
        email=decrypted["email"],
        phone=decrypted["phone"],
        condition=lead.condition,
        condition_other=lead.condition_other,
        symptom_duration=lead.symptom_duration,
        prior_treatments=lead.prior_treatments if lead.prior_treatments else [],
        has_insurance=lead.has_insurance,
        insurance_provider=lead.insurance_provider,
        zip_code=lead.zip_code,
        in_service_area=lead.in_service_area,
        urgency=lead.urgency,
        hipaa_consent=lead.hipaa_consent,
        hipaa_consent_timestamp=lead.hipaa_consent_timestamp,
        privacy_consent_timestamp=lead.privacy_consent_timestamp,
        sms_consent=lead.sms_consent,
        sms_consent_timestamp=lead.sms_consent_timestamp,
        score=lead.score,
        priority=lead.priority,
        status=lead.status,
        notes=lead.notes,
        utm_source=lead.utm_source,
        utm_medium=lead.utm_medium,
        utm_campaign=lead.utm_campaign,
        created_at=lead.created_at,
        updated_at=lead.updated_at,
        contacted_at=lead.contacted_at,
        scheduled_callback_at=lead.scheduled_callback_at,
        scheduled_notes=lead.scheduled_notes,
        contact_method=lead.contact_method,
        last_contact_attempt=lead.last_contact_attempt,
        contact_attempts=lead.contact_attempts,
        next_follow_up_at=lead.next_follow_up_at,
        contact_outcome=lead.contact_outcome,
    )


# =============================================================================
# Consultation Outcome Endpoint (for Scheduled leads)
# =============================================================================

@router.patch(
    "/{lead_id}/consultation-outcome",
    summary="Record Consultation Outcome",
    description="Record the outcome of a scheduled consultation.",
    dependencies=[Depends(require_role("administrator", "coordinator"))],
)
async def update_consultation_outcome(
    lead_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """
    Record consultation outcome for a scheduled lead.

    Accepts JSON body with:
      - outcome: str (complete|reschedule|followup|no_show|cancelled)
      - notes: Optional[str]
      - scheduled_callback_at: Optional[str] (ISO datetime for reschedule/followup)
      - contact_method: Optional[str] (PHONE|EMAIL|SMS|VIDEO_CALL)

    WORKFLOW RULES:
    | Outcome    | Status →                | follow_up_reason           | follow_up_date |
    |------------|-------------------------|----------------------------|----------------|
    | complete   | CONSULTATION_COMPLETE   | —                          | —              |
    | reschedule | SCHEDULED               | "Rescheduled"              | user-selected  |
    | followup   | CONTACTED (follow-up Q) | "Second Consult Required"  | user-selected  |
    | no_show    | CONTACTED (follow-up Q) | "No Show"                  | +1 day         |
    | cancelled  | CONTACTED (follow-up Q) | "Cancelled Appointment"    | +7 days        |
    """
    import logging
    logger = logging.getLogger(__name__)

    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Parse JSON body
    try:
        body = await request.json()
    except Exception:
        body = {}

    outcome = body.get("outcome", "complete")
    notes = body.get("notes")
    scheduled_callback_at_str = body.get("scheduled_callback_at")
    contact_method_str = body.get("contact_method")

    old_status = lead.status.value if lead.status else None
    now = datetime.now(timezone.utc)
    outcome_lower = outcome.lower().strip()

    # =========================================================================
    # CRITICAL: Clear ALL old transition fields first, then set new ones.
    # This prevents stale tags from carrying over when consultation outcome
    # routes the lead to a different queue.
    # =========================================================================
    clear_lead_transition_fields(lead)

    # Parse optional scheduled date
    scheduled_dt = None
    if scheduled_callback_at_str:
        try:
            scheduled_dt = datetime.fromisoformat(scheduled_callback_at_str.replace("Z", "+00:00"))
        except Exception:
            pass

    # Parse optional contact method
    if contact_method_str:
        try:
            from ..models.lead import ContactMethodType
            lead.contact_method = ContactMethodType(contact_method_str)
        except Exception:
            pass

    if outcome_lower == "complete":
        lead.status = LeadStatus.CONSULTATION_COMPLETE
        lead.contact_outcome = ContactOutcome.COMPLETED
        lead.follow_up_reason = None
        lead.follow_up_date = None
    elif outcome_lower == "reschedule":
        lead.status = LeadStatus.SCHEDULED
        lead.contact_outcome = ContactOutcome.SCHEDULED
        lead.follow_up_reason = "Rescheduled"
        if scheduled_dt:
            lead.scheduled_callback_at = scheduled_dt
            lead.follow_up_date = scheduled_dt
    elif outcome_lower == "followup":
        # Second consult stays in Scheduled queue (NOT Follow-up)
        # The lead still has a consultation — just at a new date
        lead.status = LeadStatus.SCHEDULED
        lead.contact_outcome = ContactOutcome.SCHEDULED
        lead.follow_up_reason = "Second Consult Required"
        if scheduled_dt:
            lead.scheduled_callback_at = scheduled_dt
            lead.follow_up_date = scheduled_dt
            lead.next_follow_up_at = scheduled_dt
    elif outcome_lower == "no_show":
        lead.status = LeadStatus.CONTACTED
        lead.contact_outcome = ContactOutcome.ANSWERED
        lead.follow_up_reason = "No Show"
        lead.follow_up_date = now + timedelta(days=1)
    elif outcome_lower == "cancelled":
        lead.status = LeadStatus.CONTACTED
        lead.contact_outcome = ContactOutcome.ANSWERED
        lead.follow_up_reason = "Cancelled Appointment"
        lead.follow_up_date = now + timedelta(days=7)
    else:
        raise HTTPException(status_code=400, detail=f"Invalid outcome: {outcome}")

    # Get authenticated user info for note attribution
    user_name = "System"
    user_id = None
    try:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            from ..core.security import decode_token
            from ..models.user import User
            token = auth_header.split(" ")[1]
            payload = decode_token(token)
            if payload and "sub" in payload:
                user = db.query(User).filter(User.id == payload["sub"]).first()
                if user:
                    user_id = user.id
                    user_name = f"{user.first_name} {user.last_name}".strip() or user.email
    except Exception:
        pass

    # Create consultation note ONLY if the coordinator typed something.
    # If no note text was provided, the outcome is already tracked in the
    # lead's status and follow_up_reason fields — no redundant note needed.
    consultation_note_text = (notes or "").strip()
    if consultation_note_text:
        try:
            from ..models.lead_note import LeadNote

            note_text = f"Consultation outcome: {outcome_lower} — {consultation_note_text}"
            auto_note = LeadNote(
                lead_id=lead.id,
                note_text=note_text,
                created_by=user_id,
                created_by_name=user_name,
                note_type="outcome",
                related_outcome=outcome_lower,
            )
            db.add(auto_note)
        except Exception as e:
            logger.warning(f"Failed to create consultation note: {e}")

    mark_lead_activity(lead)
    db.commit()
    db.refresh(lead)

    # Invalidate cache
    try:
        cache = get_cache()
        cache.invalidate_on_lead_change()
    except Exception:
        pass

    # Audit
    try:
        audit_service = AuditService(db)
        audit_service.log_update(
            table_name="leads",
            record_id=lead.id,
            ip_address=get_client_ip(request),
            endpoint=f"/api/leads/{lead_id}/consultation-outcome",
            request_method="PATCH",
            user_agent=get_user_agent(request),
            old_values={"status": old_status},
            new_values={
                "status": lead.status.value,
                "follow_up_reason": lead.follow_up_reason,
                "consultation_outcome": outcome_lower,
            },
        )
    except Exception:
        pass

    return {
        "success": True,
        "lead_id": str(lead.id),
        "new_status": lead.status.value,
        "follow_up_reason": lead.follow_up_reason,
    }


# =============================================================================
# Lead Update Endpoint
# =============================================================================

@router.patch(
    "/{lead_id}",
    response_model=LeadResponse,
    summary="Update Lead",
    description="Update lead information. All fields are optional - only provided fields will be updated.",
    dependencies=[Depends(require_role("administrator", "coordinator"))],
)
async def update_lead(
    lead_id: UUID,
    update_data: LeadUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> LeadResponse:
    """
    Update lead fields.

    Allows coordinators to update lead contact info, clinical data, notes, status, etc.
    PHI fields are re-encrypted if modified.

    Args:
        lead_id: UUID of lead to update
        update_data: Fields to update (all optional)
        request: FastAPI request
        db: Database session

    Returns:
        Updated lead details

    Raises:
        HTTPException: If lead not found or soft-deleted
    """
    import logging
    logger = logging.getLogger(__name__)

    # Fetch lead (exclude soft-deleted)
    lead = db.query(Lead).filter(
        Lead.id == lead_id,
        Lead.deleted_at.is_(None)
    ).first()

    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    # =========================================================================
    # OPTIMISTIC LOCKING — detect concurrent edits before writing.
    #
    # The client sends back the `updated_at` value it received when it last
    # fetched the lead.  If another coordinator saved the lead in the
    # meantime, `lead.updated_at` will be newer → we reject with 409 so the
    # client can refresh and show a "this lead was modified" warning instead
    # of silently overwriting the other coordinator's work.
    #
    # Legacy callers that omit `expected_updated_at` (None) bypass the check
    # so backward compatibility is fully preserved.
    # =========================================================================
    if update_data.expected_updated_at is not None:
        # Normalize both timestamps to UTC-aware for comparison.
        # SQLAlchemy returns naive UTC datetimes from PostgreSQL; the client
        # sends an ISO-8601 string that Pydantic parses as timezone-aware.
        db_updated_at = lead.updated_at
        if db_updated_at is not None and db_updated_at.tzinfo is None:
            from datetime import timezone as _tz
            db_updated_at = db_updated_at.replace(tzinfo=_tz.utc)
        client_ts = update_data.expected_updated_at
        if client_ts.tzinfo is None:
            from datetime import timezone as _tz
            client_ts = client_ts.replace(tzinfo=_tz.utc)

        if db_updated_at != client_ts:
            logger.warning(
                "Optimistic locking conflict on lead %s: "
                "client expected updated_at=%s but DB has %s",
                lead_id, client_ts, db_updated_at,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This lead was modified by another user after you opened it. "
                    "Please refresh and reapply your changes."
                ),
            )

    try:
        # Store old values for audit
        old_values = {}
        new_values = {}

        # Update PHI fields if provided (need re-encryption)
        # CRITICAL FIX: Use encrypt_field() (not encrypt() which doesn't exist)
        if update_data.first_name is not None:
            old_values["first_name"] = "[REDACTED]"
            new_values["first_name"] = "[REDACTED]"
            lead.first_name_encrypted = EncryptionService.encrypt_field(
                update_data.first_name)

        if update_data.last_name is not None:
            old_values["last_name"] = "[REDACTED]"
            new_values["last_name"] = "[REDACTED]"
            lead.last_name_encrypted = EncryptionService.encrypt_field(
                update_data.last_name) if update_data.last_name else None

        if update_data.email is not None:
            old_values["email"] = "[REDACTED]"
            new_values["email"] = "[REDACTED]"
            lead.email_encrypted = EncryptionService.encrypt_field(update_data.email)

        if update_data.phone is not None:
            old_values["phone"] = "[REDACTED]"
            new_values["phone"] = "[REDACTED]"
            lead.phone_encrypted = EncryptionService.encrypt_field(update_data.phone)

        # Update non-PHI fields
        if update_data.condition is not None:
            old_values["condition"] = lead.condition.value if lead.condition else None
            lead.condition = update_data.condition
            new_values["condition"] = update_data.condition.value
            # CRITICAL FIX: Also sync the conditions array (multi-condition field)
            # The table renders conditions[] first if it has items, so keeping
            # it in sync ensures the table displays the updated value immediately.
            # The edit modal only supports single condition, so replace the array.
            lead.conditions = [update_data.condition.value]

        if update_data.condition_other is not None:
            old_values["condition_other"] = lead.condition_other
            lead.condition_other = update_data.condition_other
            new_values["condition_other"] = update_data.condition_other

        if update_data.symptom_duration is not None:
            old_values["symptom_duration"] = lead.symptom_duration.value if lead.symptom_duration else None
            lead.symptom_duration = update_data.symptom_duration
            new_values["symptom_duration"] = update_data.symptom_duration.value

        if update_data.prior_treatments is not None:
            old_values["prior_treatments"] = [
                t.value for t in lead.prior_treatments] if lead.prior_treatments else []
            lead.prior_treatments = update_data.prior_treatments
            new_values["prior_treatments"] = [
                t.value for t in update_data.prior_treatments]

        if update_data.has_insurance is not None:
            old_values["has_insurance"] = lead.has_insurance
            lead.has_insurance = update_data.has_insurance
            new_values["has_insurance"] = update_data.has_insurance

        if update_data.insurance_provider is not None:
            old_values["insurance_provider"] = lead.insurance_provider
            lead.insurance_provider = update_data.insurance_provider
            new_values["insurance_provider"] = update_data.insurance_provider

        if update_data.zip_code is not None:
            old_values["zip_code"] = lead.zip_code
            lead.zip_code = update_data.zip_code
            new_values["zip_code"] = update_data.zip_code
            # Recalculate service area using existing utility
            from ..core.security import is_in_service_area
            lead.in_service_area = is_in_service_area(update_data.zip_code)

        if update_data.urgency is not None:
            old_values["urgency"] = lead.urgency.value if lead.urgency else None
            lead.urgency = update_data.urgency
            new_values["urgency"] = update_data.urgency.value

        if update_data.notes is not None:
            old_values["notes"] = lead.notes
            lead.notes = update_data.notes
            new_values["notes"] = update_data.notes

        if update_data.status is not None:
            old_values["status"] = lead.status.value if lead.status else None
            lead.status = update_data.status
            new_values["status"] = update_data.status.value

        if update_data.priority is not None:
            old_values["priority"] = lead.priority.value if lead.priority else None
            lead.priority = update_data.priority
            new_values["priority"] = update_data.priority.value

        if update_data.tms_therapy_interest is not None:
            old_values["tms_therapy_interest"] = lead.tms_therapy_interest
            lead.tms_therapy_interest = update_data.tms_therapy_interest if update_data.tms_therapy_interest != '' else None
            new_values["tms_therapy_interest"] = lead.tms_therapy_interest

        # =====================================================================
        # SCORE RECALCULATION: Re-score when any scoring-relevant field changes.
        # Scoring fields: condition, has_insurance, insurance_provider, zip_code,
        #                 urgency, symptom_duration, prior_treatments, tms_therapy_interest
        #
        # Without this, a lead that changes insurance from "none" (−20) to BlueCross
        # in-network (+30) would still show the old stale priority and score.
        # =====================================================================
        _SCORING_FIELDS = {
            'condition', 'has_insurance', 'insurance_provider', 'zip_code',
            'urgency', 'symptom_duration', 'prior_treatments', 'tms_therapy_interest',
        }
        if set(new_values.keys()) & _SCORING_FIELDS:
            try:
                # Build current lead state from post-update field values
                _conditions = lead.conditions if lead.conditions else (
                    [lead.condition.value] if lead.condition else []
                )
                _treatments = (
                    [t.value for t in lead.prior_treatments]
                    if lead.prior_treatments else []
                )
                # insurance_provider may be an enum or a plain string
                _ins_provider = (
                    lead.insurance_provider.value
                    if hasattr(lead.insurance_provider, 'value')
                    else (lead.insurance_provider or "")
                )
                _new_breakdown = calculate_score_from_lead_data(
                    conditions=_conditions,
                    tms_therapy_interest=lead.tms_therapy_interest or "",
                    phq2_interest=lead.phq2_interest,
                    phq2_mood=lead.phq2_mood,
                    gad2_nervous=lead.gad2_nervous,
                    gad2_worry=lead.gad2_worry,
                    ocd_time_occupied=lead.ocd_time_occupied,
                    ptsd_intrusion=lead.ptsd_intrusion,
                    has_insurance=bool(lead.has_insurance),
                    insurance_provider=_ins_provider,
                    other_insurance_provider=lead.other_insurance_provider or "",
                    symptom_duration=(
                        lead.symptom_duration.value
                        if lead.symptom_duration else ""
                    ),
                    prior_treatments=_treatments,
                    zip_code=lead.zip_code or "",
                    urgency=lead.urgency.value if lead.urgency else "",
                    date_of_birth=lead.date_of_birth,
                    referred_by_provider=bool(lead.is_referral),
                )
                _priority_map = {
                    "hot": PriorityType.HOT,
                    "medium": PriorityType.MEDIUM,
                    "low": PriorityType.LOW,
                    "disqualified": PriorityType.DISQUALIFIED,
                }
                lead.score = _new_breakdown.lead_score
                lead.lead_score = _new_breakdown.lead_score
                lead.priority = _priority_map.get(
                    _new_breakdown.priority.lower(), PriorityType.LOW
                )
                lead.in_service_area = _new_breakdown.in_service_area
                # Persist score breakdown columns
                lead.condition_score = _new_breakdown.condition_score
                lead.therapy_interest_score = _new_breakdown.therapy_interest_score
                lead.severity_score = _new_breakdown.severity_score
                lead.insurance_score = _new_breakdown.insurance_score
                lead.duration_score = _new_breakdown.duration_score
                lead.treatment_score = _new_breakdown.treatment_score
                lead.location_score = _new_breakdown.location_score
                lead.urgency_score = _new_breakdown.urgency_score
                # Reflect updated score/priority in the audit trail
                new_values["score"] = _new_breakdown.lead_score
                new_values["priority"] = lead.priority.value
                logger.info(
                    f"Lead {lead_id} rescored after edit: "
                    f"score={_new_breakdown.lead_score} priority={_new_breakdown.priority}"
                )
            except Exception as _score_err:
                # Non-fatal: continue with the edit even if rescoring fails
                logger.warning(
                    f"Score recalculation failed for lead {lead_id}: {_score_err}"
                )

        # Mark activity timestamp (any update to lead should mark activity)
        mark_lead_activity(lead)

        # Commit changes
        db.commit()
        db.refresh(lead)

        # Invalidate cache
        try:
            cache = get_cache()
            cache.invalidate_on_lead_change()
        except Exception:
            pass

        # Log audit
        if old_values:
            audit_service = AuditService(db)
            audit_service.log_update(
                table_name="leads",
                record_id=lead.id,
                ip_address=get_client_ip(request),
                endpoint=f"/api/leads/{lead_id}",
                request_method="PATCH",
                user_agent=get_user_agent(request),
                old_values=old_values,
                new_values=new_values,
            )

        # Return updated lead
        decrypted = EncryptionService.decrypt_lead_phi(lead)

        return LeadResponse(
            id=lead.id,
            first_name=decrypted["first_name"],
            last_name=decrypted["last_name"],
            email=decrypted["email"],
            phone=decrypted["phone"],
            condition=lead.condition,
            condition_other=lead.condition_other,
            symptom_duration=lead.symptom_duration,
            prior_treatments=lead.prior_treatments if lead.prior_treatments else [],
            has_insurance=lead.has_insurance,
            insurance_provider=lead.insurance_provider,
            zip_code=lead.zip_code,
            in_service_area=lead.in_service_area,
            urgency=lead.urgency,
            hipaa_consent=lead.hipaa_consent,
            hipaa_consent_timestamp=lead.hipaa_consent_timestamp,
            privacy_consent_timestamp=lead.privacy_consent_timestamp,
            sms_consent=lead.sms_consent,
            sms_consent_timestamp=lead.sms_consent_timestamp,
            score=lead.score,
            priority=lead.priority,
            status=lead.status,
            notes=lead.notes,
            utm_source=lead.utm_source,
            utm_medium=lead.utm_medium,
            utm_campaign=lead.utm_campaign,
            created_at=lead.created_at,
            updated_at=lead.updated_at,
            contacted_at=lead.contacted_at,
            scheduled_callback_at=lead.scheduled_callback_at,
            scheduled_notes=lead.scheduled_notes,
            contact_method=lead.contact_method,
            last_contact_attempt=lead.last_contact_attempt,
            contact_attempts=lead.contact_attempts,
            next_follow_up_at=lead.next_follow_up_at,
            contact_outcome=lead.contact_outcome or ContactOutcome.NEW,
            last_updated_at=lead.last_updated_at,
        )

    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        db.rollback()
        logger.error(f"Lead update error for {lead_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update lead: {str(e)}",
        )


# =============================================================================
# Soft Delete Endpoint
# =============================================================================

@router.delete(
    "/{lead_id}",
    status_code=status.HTTP_200_OK,
    summary="Soft Delete Lead",
    description="Soft delete a lead. The lead is not permanently removed but marked as deleted.",
    dependencies=[Depends(require_role("administrator"))],
)
async def delete_lead(
    lead_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """
    Soft delete a lead.

    Sets deleted_at timestamp instead of permanent deletion.
    Lead relationships (referring_provider) are preserved.
    Lead can be restored by clearing deleted_at if needed.

    Returns a JSON confirmation so the frontend gets a clear success signal.

    Args:
        lead_id: UUID of lead to delete
        request: FastAPI request
        db: Database session

    Returns:
        Success confirmation with lead details

    Raises:
        HTTPException: If lead not found or already deleted
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        # Fetch lead (exclude already soft-deleted)
        lead = db.query(Lead).filter(
            Lead.id == lead_id,
            Lead.deleted_at.is_(None)
        ).first()

        if not lead:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found or already deleted",
            )

        # Store info for audit and response before soft delete
        lead_number = lead.lead_number

        # Soft delete - set deleted_at timestamp
        lead.deleted_at = datetime.now(timezone.utc)
        db.commit()

        # Invalidate cache
        try:
            cache = get_cache()
            cache.invalidate_on_lead_change()
        except Exception:
            pass

        # Log audit
        try:
            audit_service = AuditService(db)
            audit_service.log_delete(
                table_name="leads",
                record_id=lead.id,
                ip_address=get_client_ip(request),
                endpoint=f"/api/leads/{lead_id}",
                request_method="DELETE",
                user_agent=get_user_agent(request),
                deleted_data={"lead_number": lead_number, "soft_delete": True},
            )
        except Exception as e:
            logger.warning(f"Audit log failed for delete {lead_id}: {e}")

        return {
            "success": True,
            "message": f"Lead {lead_number} has been deleted. It can be restored by an administrator.",
            "lead_number": lead_number,
            "lead_id": str(lead_id),
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Delete lead error for {lead_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete lead: {str(e)}",
        )


# =============================================================================
# Restore Deleted Lead Endpoint (Admin Only)
# =============================================================================

@router.post(
    "/{lead_id}/restore",
    response_model=LeadResponse,
    summary="Restore Deleted Lead",
    description="Restore a soft-deleted lead back to its previous queue.",
    dependencies=[Depends(require_role("administrator"))],
)
async def restore_lead(
    lead_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> LeadResponse:
    """
    Restore a soft-deleted lead.

    Clears deleted_at timestamp so the lead reappears in its original queue.

    Args:
        lead_id: UUID of lead to restore
        request: FastAPI request
        db: Database session

    Returns:
        Restored lead details

    Raises:
        HTTPException: If lead not found or not deleted
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        # Fetch only soft-deleted leads
        lead = db.query(Lead).filter(
            Lead.id == lead_id,
            Lead.deleted_at.isnot(None)
        ).first()

        if not lead:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Deleted lead not found",
            )

        # Restore - clear deleted_at
        lead.deleted_at = None
        mark_lead_activity(lead)

        db.commit()
        db.refresh(lead)

        # Invalidate cache
        try:
            cache = get_cache()
            cache.invalidate_on_lead_change()
        except Exception:
            pass

        # Log audit
        try:
            audit_service = AuditService(db)
            audit_service.log_update(
                table_name="leads",
                record_id=lead.id,
                ip_address=get_client_ip(request),
                endpoint=f"/api/leads/{lead_id}/restore",
                request_method="POST",
                user_agent=get_user_agent(request),
                old_values={"deleted_at": "was_deleted"},
                new_values={"deleted_at": None, "restored": True},
            )
        except Exception as e:
            logger.warning(f"Audit log failed for restore {lead_id}: {e}")

        # Return restored lead
        decrypted = EncryptionService.decrypt_lead_phi(lead)

        return LeadResponse(
            id=lead.id,
            first_name=decrypted["first_name"],
            last_name=decrypted["last_name"],
            email=decrypted["email"],
            phone=decrypted["phone"],
            condition=lead.condition,
            condition_other=lead.condition_other,
            symptom_duration=lead.symptom_duration,
            prior_treatments=lead.prior_treatments if lead.prior_treatments else [],
            has_insurance=lead.has_insurance,
            insurance_provider=lead.insurance_provider,
            zip_code=lead.zip_code,
            in_service_area=lead.in_service_area,
            urgency=lead.urgency,
            hipaa_consent=lead.hipaa_consent,
            hipaa_consent_timestamp=lead.hipaa_consent_timestamp,
            privacy_consent_timestamp=lead.privacy_consent_timestamp,
            sms_consent=lead.sms_consent,
            sms_consent_timestamp=lead.sms_consent_timestamp,
            score=lead.score,
            priority=lead.priority,
            status=lead.status,
            notes=lead.notes,
            utm_source=lead.utm_source,
            utm_medium=lead.utm_medium,
            utm_campaign=lead.utm_campaign,
            created_at=lead.created_at,
            updated_at=lead.updated_at,
            contacted_at=lead.contacted_at,
            scheduled_callback_at=lead.scheduled_callback_at,
            scheduled_notes=lead.scheduled_notes,
            contact_method=lead.contact_method,
            last_contact_attempt=lead.last_contact_attempt,
            contact_attempts=lead.contact_attempts,
            next_follow_up_at=lead.next_follow_up_at,
            contact_outcome=lead.contact_outcome or ContactOutcome.NEW,
            last_updated_at=lead.last_updated_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Restore lead error for {lead_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to restore lead: {str(e)}",
        )


# =============================================================================
# Permanent Delete Endpoint (Admin Only)
# =============================================================================

@router.delete(
    "/{lead_id}/permanent",
    status_code=status.HTTP_200_OK,
    summary="Permanently Delete Lead",
    description="Permanently remove a soft-deleted lead from the database. This action cannot be undone.",
    dependencies=[Depends(require_role("administrator"))],
)
async def permanent_delete_lead(
    lead_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """
    Permanently delete a lead record.

    WARNING: This action CANNOT be undone. Only works on already soft-deleted leads.

    Args:
        lead_id: UUID of lead to permanently delete
        request: FastAPI request
        db: Database session

    Returns:
        Success confirmation

    Raises:
        HTTPException: If lead not found or not already soft-deleted
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        # Only allow permanent deletion of already soft-deleted leads
        lead = db.query(Lead).filter(
            Lead.id == lead_id,
            Lead.deleted_at.isnot(None)
        ).first()

        if not lead:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Deleted lead not found. Only soft-deleted leads can be permanently removed.",
            )

        lead_number = lead.lead_number

        # Log audit BEFORE deletion
        try:
            audit_service = AuditService(db)
            audit_service.log_delete(
                table_name="leads",
                record_id=lead.id,
                ip_address=get_client_ip(request),
                endpoint=f"/api/leads/{lead_id}/permanent",
                request_method="DELETE",
                user_agent=get_user_agent(request),
                deleted_data={"lead_number": lead_number, "permanent_delete": True},
            )
        except Exception as e:
            logger.warning(f"Audit log failed for permanent delete {lead_id}: {e}")

        # Hard delete
        db.delete(lead)
        db.commit()

        # Invalidate cache
        try:
            cache = get_cache()
            cache.invalidate_on_lead_change()
        except Exception:
            pass

        return {
            "success": True,
            "message": f"Lead {lead_number} has been permanently deleted.",
            "lead_number": lead_number,
            "lead_id": str(lead_id),
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Permanent delete error for {lead_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to permanently delete lead: {str(e)}",
        )
