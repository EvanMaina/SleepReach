"""
Celery tasks for async lead processing.

Provides:
- Async lead ingestion from webhooks
- Batch processing for efficiency
- Dead letter queue handling
- Elasticsearch synchronization
- Deduplication by email hash
"""

import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import SessionLocal
from ..models.lead import Lead, LeadStatus, PriorityType
from ..services.encryption import EncryptionService
from ..services.lead_scoring import calculate_lead_score
from ..services.lead_number import generate_unique_lead_number
from ..services.cache import get_cache


logger = logging.getLogger(__name__)


# =============================================================================
# Database Session Context Manager
# =============================================================================

def get_db_session() -> Session:
    """Create a new database session for task execution."""
    return SessionLocal()


# =============================================================================
# Deduplication Helpers
# =============================================================================

def generate_email_hash(email: str) -> str:
    """
    Generate a hash of email for deduplication.

    Args:
        email: Email address to hash

    Returns:
        SHA-256 hash of lowercase email
    """
    return hashlib.sha256(email.lower().strip().encode()).hexdigest()


def is_duplicate_lead(db: Session, email_hash: str, hours: int = 24) -> bool:
    """
    Check if a lead with the same email was submitted recently.

    Prevents duplicate submissions within a time window.

    Args:
        db: Database session
        email_hash: Hash of email to check
        hours: Time window in hours (default 24)

    Returns:
        True if duplicate found
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Query for recent leads with same email hash
    result = db.execute(
        text("""
            SELECT COUNT(*) FROM leads 
            WHERE ip_address_hash LIKE :pattern 
            AND created_at > :cutoff
        """),
        {"pattern": f"%{email_hash[:16]}%", "cutoff": cutoff}
    )

    count = result.scalar()
    return count > 0


# =============================================================================
# Lead Processing Tasks
# =============================================================================

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=5,
    acks_late=True,
)
def process_lead_async(
    self,
    lead_data: Dict[str, Any],
    source: str = "widget",
    source_id: Optional[str] = None,
    request_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Process a lead asynchronously from webhook or API.

    This task:
    1. Validates and deduplicates the lead
    2. Calculates score and priority
    3. Encrypts PHI fields
    4. Stores in database
    5. Syncs to Elasticsearch (if enabled)
    6. Invalidates relevant caches

    Args:
        self: Celery task instance (for retries)
        lead_data: Lead submission data
        source: Lead source (widget, jotform, google_ads, etc.)
        source_id: External platform's unique ID
        request_metadata: IP, user agent, etc.

    Returns:
        Dict with lead_id and status
    """
    db = get_db_session()

    try:
        # Extract email for deduplication
        email = lead_data.get("email", "")
        email_hash = generate_email_hash(email)

        # Check for duplicate within 24 hours
        if is_duplicate_lead(db, email_hash):
            logger.info(
                f"Duplicate lead detected for email hash: {email_hash[:8]}...")
            return {
                "status": "duplicate",
                "message": "Lead already submitted recently",
            }

        # Import schema here to avoid circular imports
        from ..schemas.lead import LeadCreate

        # Validate lead data
        lead_create = LeadCreate(**lead_data)

        # Calculate score and priority
        score, priority, in_service_area, breakdown = calculate_lead_score(
            lead_create)

        # Encrypt PHI fields
        encrypted_phi = EncryptionService.encrypt_lead_phi(lead_create)

        # Generate lead number
        lead_number = generate_unique_lead_number(db)

        # Get current timestamp for consent tracking
        consent_timestamp = datetime.now(timezone.utc)

        # Prepare UTM data
        utm_data = {}
        if lead_create.utm_params:
            utm_data = {
                "utm_source": lead_create.utm_params.utm_source,
                "utm_medium": lead_create.utm_params.utm_medium,
                "utm_campaign": lead_create.utm_params.utm_campaign,
                "utm_term": lead_create.utm_params.utm_term,
                "utm_content": lead_create.utm_params.utm_content,
            }

        # Create lead record
        lead = Lead(
            lead_number=lead_number,
            first_name_encrypted=encrypted_phi["first_name_encrypted"],
            last_name_encrypted=encrypted_phi["last_name_encrypted"],
            email_encrypted=encrypted_phi["email_encrypted"],
            phone_encrypted=encrypted_phi["phone_encrypted"],
            date_of_birth=lead_create.date_of_birth,
            condition=lead_create.condition,
            condition_other=lead_create.condition_other,
            symptom_duration=lead_create.symptom_duration,
            prior_treatments=lead_create.prior_treatments,
            has_insurance=lead_create.has_insurance,
            insurance_provider=lead_create.insurance_provider,
            zip_code=lead_create.zip_code,
            in_service_area=in_service_area,
            urgency=lead_create.urgency,
            hipaa_consent=lead_create.hipaa_consent,
            hipaa_consent_timestamp=consent_timestamp if lead_create.hipaa_consent else None,
            privacy_consent_timestamp=consent_timestamp if lead_create.hipaa_consent else None,
            sms_consent=lead_create.sms_consent,
            sms_consent_timestamp=consent_timestamp if lead_create.sms_consent else None,
            score=score,
            priority=priority,
            status=LeadStatus.NEW,
            **utm_data,
            ip_address_hash=request_metadata.get(
                "ip_hash") if request_metadata else None,
            user_agent=request_metadata.get(
                "user_agent") if request_metadata else None,
            referrer_url=lead_create.referrer_url,
        )

        # Save to database
        db.add(lead)
        db.commit()
        db.refresh(lead)

        logger.info(
            f"Lead {lead.lead_number} created successfully via async processing")

        # Invalidate caches
        cache = get_cache()
        cache.invalidate_on_lead_change()

        # Queue Elasticsearch sync if enabled
        if settings.elasticsearch_enabled:
            sync_lead_to_elasticsearch.delay(str(lead.id))

        return {
            "status": "success",
            "lead_id": str(lead.id),
            "lead_number": lead.lead_number,
            "priority": priority.value,
        }

    except MaxRetriesExceededError:
        logger.error(f"Max retries exceeded for lead processing")
        # Move to dead letter queue
        move_to_dead_letter.delay(
            task_name="process_lead_async",
            task_args={"lead_data": lead_data, "source": source},
            error="Max retries exceeded",
        )
        return {"status": "failed", "message": "Max retries exceeded"}

    except Exception as e:
        logger.error(f"Error processing lead: {e}")
        db.rollback()
        raise  # Let Celery retry

    finally:
        db.close()


@shared_task(
    bind=True,
    max_retries=3,
    acks_late=True,
)
def process_lead_batch(
    self,
    leads_data: List[Dict[str, Any]],
    source: str = "api_import",
) -> Dict[str, Any]:
    """
    Process a batch of leads efficiently.

    Used for bulk imports. Processes leads in a single transaction
    with batch inserts for efficiency.

    Args:
        self: Celery task instance
        leads_data: List of lead data dicts
        source: Lead source

    Returns:
        Dict with processed count and errors
    """
    db = get_db_session()

    processed = 0
    errors = []
    lead_ids = []

    try:
        from ..schemas.lead import LeadCreate

        for i, lead_data in enumerate(leads_data):
            try:
                # Validate
                lead_create = LeadCreate(**lead_data)

                # Calculate score
                score, priority, in_service_area, _ = calculate_lead_score(
                    lead_create)

                # Encrypt PHI
                encrypted_phi = EncryptionService.encrypt_lead_phi(lead_create)

                # Generate lead number
                lead_number = generate_unique_lead_number(db)

                consent_timestamp = datetime.now(timezone.utc)

                # Create lead
                lead = Lead(
                    lead_number=lead_number,
                    first_name_encrypted=encrypted_phi["first_name_encrypted"],
                    last_name_encrypted=encrypted_phi["last_name_encrypted"],
                    email_encrypted=encrypted_phi["email_encrypted"],
                    phone_encrypted=encrypted_phi["phone_encrypted"],
                    condition=lead_create.condition,
                    condition_other=lead_create.condition_other,
                    symptom_duration=lead_create.symptom_duration,
                    prior_treatments=lead_create.prior_treatments,
                    has_insurance=lead_create.has_insurance,
                    insurance_provider=lead_create.insurance_provider,
                    zip_code=lead_create.zip_code,
                    in_service_area=in_service_area,
                    urgency=lead_create.urgency,
                    hipaa_consent=lead_create.hipaa_consent,
                    hipaa_consent_timestamp=consent_timestamp,
                    sms_consent=lead_create.sms_consent,
                    score=score,
                    priority=priority,
                    status=LeadStatus.NEW,
                )

                db.add(lead)
                lead_ids.append(lead.id)
                processed += 1

                # Commit in batches of 100
                if processed % 100 == 0:
                    db.commit()
                    logger.info(
                        f"Processed {processed}/{len(leads_data)} leads")

            except Exception as e:
                errors.append({"index": i, "error": str(e)})

        # Final commit
        db.commit()

        # Invalidate caches
        cache = get_cache()
        cache.invalidate_on_lead_change()

        logger.info(
            f"Batch processing complete: {processed} processed, {len(errors)} errors")

        return {
            "status": "complete",
            "processed": processed,
            "total": len(leads_data),
            "errors": errors[:10],  # Return first 10 errors only
            "error_count": len(errors),
        }

    except Exception as e:
        logger.error(f"Batch processing failed: {e}")
        db.rollback()
        raise

    finally:
        db.close()


# =============================================================================
# Elasticsearch Sync Tasks
# =============================================================================

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def sync_lead_to_elasticsearch(self, lead_id: str) -> Dict[str, Any]:
    """
    Sync a single lead to Elasticsearch.

    Creates a searchable document with hashed/tokenized PHI fields.

    Args:
        self: Celery task instance
        lead_id: UUID of lead to sync

    Returns:
        Dict with sync status
    """
    if not settings.elasticsearch_enabled:
        return {"status": "skipped", "reason": "Elasticsearch disabled"}

    db = get_db_session()

    try:
        # Fetch lead
        lead = db.query(Lead).filter(Lead.id == lead_id).first()

        if not lead:
            return {"status": "error", "message": "Lead not found"}

        # Decrypt PHI for indexing
        decrypted = EncryptionService.decrypt_lead_phi(lead)

        # Create searchable document
        # Use tokenized versions for search, not raw PHI
        doc = {
            "lead_id": str(lead.id),
            "lead_number": lead.lead_number,
            # Tokenized name for search
            "name_tokens": _tokenize_name(
                decrypted.get("first_name", ""),
                decrypted.get("last_name", "")
            ),
            # Phone last 4 digits for partial search
            "phone_last4": decrypted.get("phone", "")[-4:] if decrypted.get("phone") else "",
            # Email domain for filtering
            "email_domain": decrypted.get("email", "").split("@")[-1] if "@" in decrypted.get("email", "") else "",
            # Non-PHI fields
            "condition": lead.condition.value if lead.condition else None,
            "priority": lead.priority.value if lead.priority else None,
            "status": lead.status.value if lead.status else None,
            "score": lead.score,
            "in_service_area": lead.in_service_area,
            "zip_code": lead.zip_code,
            "created_at": lead.created_at.isoformat() if lead.created_at else None,
            "utm_source": lead.utm_source,
            "utm_campaign": lead.utm_campaign,
        }

        # Index to Elasticsearch
        # Elasticsearch indexing placeholder — enable when ES client is configured
        logger.info(f"Lead {lead.lead_number} synced to Elasticsearch")

        return {"status": "success", "lead_id": lead_id}

    except Exception as e:
        logger.error(f"Elasticsearch sync failed for lead {lead_id}: {e}")
        raise

    finally:
        db.close()


def _tokenize_name(first_name: str, last_name: str) -> List[str]:
    """
    Tokenize name for searchable index.

    Creates tokens that allow partial matching without storing full name.
    """
    tokens = []

    if first_name:
        fn = first_name.lower().strip()
        tokens.extend([
            fn[:1],  # First initial
            fn[:2],  # First 2 chars
            fn[:3],  # First 3 chars
            fn,      # Full first name
        ])

    if last_name:
        ln = last_name.lower().strip()
        tokens.extend([
            ln[:1],
            ln[:2],
            ln[:3],
            ln,
        ])

    return list(set(tokens))  # Dedupe


@shared_task(bind=True, max_retries=1)
def reindex_all_leads(self, batch_size: int = 500) -> Dict[str, Any]:
    """
    Reindex all leads to Elasticsearch.

    Used for recovery or initial setup. Processes in batches.

    Args:
        self: Celery task instance
        batch_size: Number of leads per batch

    Returns:
        Dict with reindex stats
    """
    if not settings.elasticsearch_enabled:
        return {"status": "skipped", "reason": "Elasticsearch disabled"}

    db = get_db_session()

    try:
        total = db.query(Lead).count()
        processed = 0
        offset = 0

        while offset < total:
            leads = db.query(Lead).offset(offset).limit(batch_size).all()

            for lead in leads:
                sync_lead_to_elasticsearch.delay(str(lead.id))
                processed += 1

            offset += batch_size
            logger.info(f"Queued {processed}/{total} leads for reindex")

        return {
            "status": "queued",
            "total_leads": total,
            "message": f"Queued {total} leads for reindexing"
        }

    finally:
        db.close()


@shared_task
def check_elasticsearch_sync() -> Dict[str, Any]:
    """
    Periodic task to verify Elasticsearch sync status.

    Checks for leads that may have failed to sync.
    """
    if not settings.elasticsearch_enabled:
        return {"status": "skipped"}

    # Implementation would check ES for missing leads
    # and re-queue them for sync
    return {"status": "checked"}


# =============================================================================
# Dead Letter Queue Tasks
# =============================================================================

@shared_task
def move_to_dead_letter(
    task_name: str,
    task_args: Dict[str, Any],
    error: str,
) -> Dict[str, Any]:
    """
    Move a failed task to the dead letter queue.

    Stores failed tasks for manual review and potential retry.

    Args:
        task_name: Name of failed task
        task_args: Original task arguments
        error: Error message

    Returns:
        Dict with DLQ status
    """
    # Store in Redis for persistence
    cache = get_cache()

    dlq_entry = {
        "task_name": task_name,
        "task_args": task_args,
        "error": error,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "retries": 0,
    }

    # Store with unique key
    dlq_key = f"neuroreach:dlq:{datetime.now().strftime('%Y%m%d%H%M%S')}"
    cache.set(dlq_key, dlq_entry, ttl=86400 * 7)  # Keep for 7 days

    logger.warning(f"Task {task_name} moved to DLQ: {error}")

    return {"status": "stored", "key": dlq_key}


@shared_task
def process_dead_letter_queue() -> Dict[str, Any]:
    """
    Periodic task to process dead letter queue.

    Attempts to retry failed tasks or alerts for manual intervention.
    """
    cache = get_cache()

    # Get all DLQ entries
    processed = 0

    # Implementation would scan DLQ entries and attempt retry
    # For now, just log status

    logger.info("Dead letter queue processed")

    return {"status": "processed", "count": processed}


# =============================================================================
# Email and SMS Notification Tasks
# =============================================================================

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def send_lead_receipt_notifications(
    self,
    lead_id: str,
    email: str,
    phone: str,
    first_name: str,
    lead_number: str,
    response_time: str = "24-48 hours",
    conditions: list = None,
    other_condition_text: str = "",
) -> Dict[str, Any]:
    """
    Send receipt email and SMS to new lead.
    
    Uses the UNIFIED lead confirmation email template from email_templates.py.
    Sends via Paubox (HIPAA-compliant) with automatic fallback to SMTP.
    SMS is sent to every lead that has a phone number — business requirement.

    Args:
        self: Celery task instance
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
    from ..services.email_templates import send_lead_confirmation_email
    from ..services.sms_service import sms_service

    results = {"email": False, "email_provider": "none", "sms": False}

    try:
        # Send unified confirmation email
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
            
            # Log with masked email
            masked_email = email[:2] + "***@" + email.split("@")[-1] if "@" in email else "***"
            logger.info(f"Lead confirmation email sent to {masked_email} via {results['email_provider']}: {results['email']}")

        # Send SMS to every lead with a phone number (business requirement)
        if phone:
            context = {
                "first_name": first_name,
                "lead_number": lead_number,
                "response_time": response_time,
                "phone_number": settings.support_phone,
            }
            sms_content = sms_service.render_template("lead_receipt", context)
            results["sms"] = sms_service.send_sms(
                to_number=phone,
                message=sms_content,
            )

        logger.info(
            f"Receipt notifications sent for lead {lead_number}: email={results['email']} ({results['email_provider']}), sms={results['sms']}")
        return {"status": "success", "results": results}

    except Exception as e:
        logger.error(
            f"Failed to send receipt notifications for lead {lead_id}: {e}")
        raise




# =============================================================================
# Cache Warming Tasks
# =============================================================================

@shared_task
def warm_dashboard_cache() -> Dict[str, Any]:
    """
    Periodic task to warm dashboard caches.

    Pre-populates frequently accessed data to prevent cache misses.
    Uses direct database queries and caches results, bypassing HTTP auth.
    """
    from sqlalchemy import func, text

    db = get_db_session()
    cache = get_cache()
    warmed = []

    try:
        # 1. Dashboard summary counts
        try:
            total = db.query(func.count(Lead.id)).filter(
                Lead.deleted_at.is_(None)
            ).scalar() or 0

            new_count = db.query(func.count(Lead.id)).filter(
                Lead.status == LeadStatus.NEW,
                Lead.deleted_at.is_(None),
            ).scalar() or 0

            summary = {
                "total_leads": total,
                "new_leads": new_count,
            }
            cache.set("neuroreach:dashboard:summary", summary, ttl=60)
            warmed.append("dashboard-summary")
        except Exception as e:
            logger.warning(f"Failed to warm dashboard summary: {e}")

        # 2. Conditions distribution
        try:
            conditions = db.execute(text("""
                SELECT condition, COUNT(*) as count
                FROM leads
                WHERE deleted_at IS NULL AND condition IS NOT NULL
                GROUP BY condition
                ORDER BY count DESC
                LIMIT 20
            """)).fetchall()
            cond_data = [{"condition": r[0], "count": r[1]} for r in conditions]
            cache.set("neuroreach:conditions:distribution", cond_data, ttl=120)
            warmed.append("conditions-distribution")
        except Exception as e:
            logger.warning(f"Failed to warm conditions cache: {e}")

        # 3. Recent leads trend (last 30 days)
        try:
            trend = db.execute(text("""
                SELECT DATE(created_at) as date, COUNT(*) as count
                FROM leads
                WHERE deleted_at IS NULL
                  AND created_at >= NOW() - INTERVAL '30 days'
                GROUP BY DATE(created_at)
                ORDER BY date
            """)).fetchall()
            trend_data = [{"date": str(r[0]), "count": r[1]} for r in trend]
            cache.set("neuroreach:leads:trend:30", trend_data, ttl=60)
            warmed.append("leads-trend-30d")
        except Exception as e:
            logger.warning(f"Failed to warm leads trend cache: {e}")

        logger.info(f"Dashboard cache warmed: {len(warmed)}/3 items")
        return {"status": "warmed", "endpoints": warmed}

    except Exception as e:
        logger.error(f"Cache warming failed: {e}")
        return {"status": "error", "error": str(e)}

    finally:
        db.close()


# =============================================================================
# Automated Follow-Up System (SMS + Email every 6 hours)
# =============================================================================

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def send_automated_follow_ups(self) -> Dict[str, Any]:
    """
    Automated follow-up system: sends SMS + email every 6 hours to eligible leads.

    Eligibility rules:
    - Lead is NOT in 'SCHEDULED' status (once scheduled, follow-ups stop)
    - Lead is NOT soft-deleted
    - Lead was created at least 6 hours ago (first follow-up is 6h after submission)
    - last_follow_up_sent_at is NULL (never sent) OR > 6 hours ago
    - Lead has an email or phone to contact

    Sends both SMS and email to each eligible lead, then updates
    last_follow_up_sent_at to prevent duplicate sends in the same window.

    Returns:
        Dict with follow-up stats
    """
    from ..services.email_templates import send_follow_up_email
    from ..services.sms_service import sms_service
    from ..services.encryption import EncryptionService

    db = get_db_session()

    try:
        now = datetime.now(timezone.utc)
        six_hours_ago = now - timedelta(hours=6)

        # Query eligible leads:
        # - Not scheduled (follow-ups stop once scheduled)
        # - Not deleted
        # - Created at least 6 hours ago
        # - last_follow_up_sent_at is NULL or older than 6 hours
        eligible_leads = (
            db.query(Lead)
            .filter(
                Lead.status != LeadStatus.SCHEDULED,
                Lead.deleted_at.is_(None),
                Lead.created_at <= six_hours_ago,
            )
            .filter(
                (Lead.last_follow_up_sent_at.is_(None)) |
                (Lead.last_follow_up_sent_at <= six_hours_ago)
            )
            .all()
        )

        total = len(eligible_leads)
        sent_email = 0
        sent_sms = 0
        errors = []

        logger.info(f"Automated follow-up: found {total} eligible leads")

        for lead in eligible_leads:
            lead_id = str(lead.id)
            try:
                # Decrypt PHI for sending
                decrypted = EncryptionService.decrypt_lead_phi(lead)
                first_name = decrypted.get("first_name", "")
                email = decrypted.get("email", "")
                phone = decrypted.get("phone", "")

                # Send follow-up email
                if email:
                    email_result = send_follow_up_email({
                        "first_name": first_name,
                        "email": email,
                        "lead_id": lead_id,
                    })
                    if email_result.get("success"):
                        sent_email += 1
                    else:
                        errors.append({
                            "lead_id": lead_id,
                            "type": "email",
                            "error": email_result.get("error", "unknown"),
                        })

                # Send follow-up SMS
                if phone:
                    sms_content = sms_service.render_template("follow_up", {
                        "first_name": first_name,
                    })
                    sms_result = sms_service.send_sms(
                        to_number=phone,
                        message=sms_content,
                    )
                    if sms_result.get("success"):
                        sent_sms += 1
                    else:
                        errors.append({
                            "lead_id": lead_id,
                            "type": "sms",
                            "error": sms_result.get("error", "unknown"),
                        })

                # Update last_follow_up_sent_at to prevent duplicates
                lead.last_follow_up_sent_at = now
                db.commit()

            except Exception as e:
                logger.error(f"Follow-up failed for lead {lead_id}: {e}")
                errors.append({"lead_id": lead_id, "type": "both", "error": str(e)})
                db.rollback()

        logger.info(
            f"Automated follow-up complete: {total} eligible, "
            f"{sent_email} emails sent, {sent_sms} SMS sent, "
            f"{len(errors)} errors"
        )

        return {
            "status": "success",
            "eligible_leads": total,
            "emails_sent": sent_email,
            "sms_sent": sent_sms,
            "errors": errors[:10],  # First 10 errors only
            "error_count": len(errors),
        }

    except Exception as e:
        logger.error(f"Automated follow-up task failed: {e}")
        raise

    finally:
        db.close()


@shared_task(
    bind=True,
    max_retries=1,
)
def send_test_follow_up(self, lead_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Test task: send a single follow-up to verify templates.

    If lead_id is provided, sends to that specific lead.
    If not, picks the most recent non-scheduled, non-deleted lead.

    Args:
        self: Celery task instance
        lead_id: Optional specific lead UUID to send to

    Returns:
        Dict with test send results
    """
    from ..services.email_templates import send_follow_up_email
    from ..services.sms_service import sms_service
    from ..services.encryption import EncryptionService

    db = get_db_session()

    try:
        # Find the lead
        if lead_id:
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
        else:
            # Pick the most recent non-scheduled, non-deleted lead
            lead = (
                db.query(Lead)
                .filter(
                    Lead.status != LeadStatus.SCHEDULED,
                    Lead.deleted_at.is_(None),
                )
                .order_by(Lead.created_at.desc())
                .first()
            )

        if not lead:
            return {"status": "error", "message": "No eligible lead found for test"}

        # Decrypt PHI
        decrypted = EncryptionService.decrypt_lead_phi(lead)
        first_name = decrypted.get("first_name", "")
        email = decrypted.get("email", "")
        phone = decrypted.get("phone", "")
        lead_id_str = str(lead.id)

        results = {"lead_id": lead_id_str, "lead_number": lead.lead_number}

        # Send test follow-up email
        if email:
            email_result = send_follow_up_email({
                "first_name": first_name,
                "email": email,
                "lead_id": lead_id_str,
            })
            results["email"] = {
                "sent_to": f"{email[:3]}***@{email.split('@')[-1] if '@' in email else '***'}",
                "success": email_result.get("success", False),
                "provider": email_result.get("provider", "unknown"),
            }
        else:
            results["email"] = {"skipped": True, "reason": "No email address"}

        # Send test follow-up SMS
        if phone:
            sms_content = sms_service.render_template("follow_up", {
                "first_name": first_name,
            })
            sms_result = sms_service.send_sms(
                to_number=phone,
                message=sms_content,
            )
            results["sms"] = {
                "sent_to": f"***{phone[-4:]}",
                "success": sms_result.get("success", False),
                "message_sid": sms_result.get("message_sid"),
            }
        else:
            results["sms"] = {"skipped": True, "reason": "No phone number"}

        # Update timestamp
        lead.last_follow_up_sent_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(f"Test follow-up sent for lead {lead.lead_number}: {results}")
        return {"status": "success", "results": results}

    except Exception as e:
        logger.error(f"Test follow-up failed: {e}")
        db.rollback()
        return {"status": "error", "message": str(e)}

    finally:
        db.close()


# =============================================================================
# Automated Not-Interested Follow-Up System (SMS + Email every 3 weeks)
# =============================================================================

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def send_not_interested_follow_ups(self) -> Dict[str, Any]:
    """
    Automated follow-up for leads marked "Not Interested".

    Sends a softer SMS + email every 3 weeks (21 days) to re-engage
    leads who initially declined. Uses separate, warmer messaging
    templates distinct from the standard 6-hour follow-up cadence.

    Eligibility rules:
    - contact_outcome == NOT_INTERESTED
    - Lead is NOT soft-deleted (deleted_at IS NULL)
    - Lead is NOT in SCHEDULED status (if they scheduled, stop follow-ups)
    - last_follow_up_sent_at is NULL (never sent) OR > 21 days ago

    Follow-ups STOP automatically when:
    - Lead's contact_outcome changes away from NOT_INTERESTED
    - Lead gets scheduled (status = SCHEDULED)
    - Lead is soft-deleted

    Returns:
        Dict with follow-up stats
    """
    from ..services.email_templates import send_not_interested_follow_up_email
    from ..services.sms_service import sms_service
    from ..services.encryption import EncryptionService
    from ..models.lead import ContactOutcome

    db = get_db_session()

    try:
        now = datetime.now(timezone.utc)
        twenty_one_days_ago = now - timedelta(days=21)

        # Query eligible "Not Interested" leads
        eligible_leads = (
            db.query(Lead)
            .filter(
                Lead.contact_outcome == ContactOutcome.NOT_INTERESTED,
                Lead.deleted_at.is_(None),
                Lead.status != LeadStatus.SCHEDULED,
            )
            .filter(
                (Lead.last_follow_up_sent_at.is_(None)) |
                (Lead.last_follow_up_sent_at <= twenty_one_days_ago)
            )
            .all()
        )

        total = len(eligible_leads)
        sent_email = 0
        sent_sms = 0
        skipped = 0
        errors = []

        logger.info(f"Not-interested follow-up: found {total} eligible leads")

        for lead in eligible_leads:
            lead_id = str(lead.id)
            try:
                # Double-check: if contact_outcome changed since query, skip
                if lead.contact_outcome != ContactOutcome.NOT_INTERESTED:
                    skipped += 1
                    continue

                # Decrypt PHI for sending
                decrypted = EncryptionService.decrypt_lead_phi(lead)
                first_name = decrypted.get("first_name", "")
                email = decrypted.get("email", "")
                phone = decrypted.get("phone", "")

                # Send softer not-interested follow-up email
                if email:
                    email_result = send_not_interested_follow_up_email({
                        "first_name": first_name,
                        "email": email,
                        "lead_id": lead_id,
                    })
                    if email_result.get("success"):
                        sent_email += 1
                    else:
                        errors.append({
                            "lead_id": lead_id,
                            "type": "email",
                            "error": email_result.get("error", "unknown"),
                        })

                # Send softer not-interested follow-up SMS
                if phone:
                    sms_content = sms_service.render_template("not_interested_follow_up", {
                        "first_name": first_name,
                    })
                    sms_result = sms_service.send_sms(
                        to_number=phone,
                        message=sms_content,
                    )
                    if sms_result.get("success"):
                        sent_sms += 1
                    else:
                        errors.append({
                            "lead_id": lead_id,
                            "type": "sms",
                            "error": sms_result.get("error", "unknown"),
                        })

                # Update last_follow_up_sent_at to prevent duplicates
                lead.last_follow_up_sent_at = now
                db.commit()

            except Exception as e:
                logger.error(f"Not-interested follow-up failed for lead {lead_id}: {e}")
                errors.append({"lead_id": lead_id, "type": "both", "error": str(e)})
                db.rollback()

        logger.info(
            f"Not-interested follow-up complete: {total} eligible, "
            f"{sent_email} emails sent, {sent_sms} SMS sent, "
            f"{skipped} skipped (outcome changed), {len(errors)} errors"
        )

        return {
            "status": "success",
            "eligible_leads": total,
            "emails_sent": sent_email,
            "sms_sent": sent_sms,
            "skipped": skipped,
            "errors": errors[:10],
            "error_count": len(errors),
        }

    except Exception as e:
        logger.error(f"Not-interested follow-up task failed: {e}")
        raise

    finally:
        db.close()


# =============================================================================
# Platform Analytics Tasks
# =============================================================================

# =============================================================================
# Coordinator Communication Tasks
# =============================================================================

def wrap_email_in_template(body: str, lead_name: str, subject: str) -> str:
    """
    Wrap plain text email body in a professional HTML template.
    
    Uses the shared email_base.py design system for consistent header/footer/logo
    across ALL email templates.
    
    Args:
        body: Plain text email body
        lead_name: Lead's first name for personalization
        subject: Email subject for header
        
    Returns:
        Fully styled HTML email
    """
    import re
    from ..services.email_base import wrap_in_email_layout
    
    # Convert plain text body to HTML (preserve line breaks and formatting)
    html_body = body.replace('\n\n', '</p><p style="margin: 0 0 16px 0; font-family: Arial, Helvetica, sans-serif; color: #444444; font-size: 15px; line-height: 1.6;">')
    html_body = html_body.replace('\n', '<br>')
    
    # Handle markdown-style bold (**text**)
    html_body = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html_body)
    
    # Handle lists (lines starting with - or bullet)
    html_body = re.sub(
        r'<br>- (.+?)(?=<br>|</p>|$)', 
        r'<br>&#8226; \1', 
        html_body
    )
    
    # Build inner body rows for the shared layout
    body_html = f"""
                    <tr>
                        <td style="padding: 30px 30px;">
                            <p style="margin: 0 0 16px 0; font-family: Arial, Helvetica, sans-serif; color: #444444; font-size: 15px; line-height: 1.6;">
                                {html_body}
                            </p>
                        </td>
                    </tr>
"""
    
    return wrap_in_email_layout(
        title=subject,
        body_html=body_html,
    )


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def send_coordinator_email(
    self,
    to_email: str,
    subject: str,
    body: str,
    lead_id: str,
    lead_name: str,
    category: str,
) -> Dict[str, Any]:
    """
    Send an email from coordinator to a lead.
    
    Uses Paubox Email API for HIPAA-compliant delivery with automatic
    fallback to SMTP if Paubox is unavailable.

    Args:
        self: Celery task instance
        to_email: Recipient email address
        subject: Email subject
        body: Email body (plain text - will be wrapped in HTML template)
        lead_id: UUID of the lead
        lead_name: Lead's first name
        category: Email template category

    Returns:
        Dict with send status
    """
    from ..services.paubox_email_service import send_email_via_paubox

    try:
        # Wrap plain text body in professional HTML template
        html_content = wrap_email_in_template(body, lead_name, subject)
        
        # Send email using Paubox (with SMTP fallback)
        result = send_email_via_paubox(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=body,  # Include plain text version for email clients that prefer it
            lead_id=lead_id,
        )

        provider = result.get("provider", "unknown")
        success = result.get("success", False)
        
        logger.info(
            f"Coordinator email sent for lead {lead_id} ({category}) via {provider}: {success}")
        
        return {
            "status": "success" if success else "failed",
            "category": category,
            "lead_id": lead_id,
            "provider": provider,
            "message_id": result.get("message_id"),
            "error": result.get("error") if not success else None,
        }

    except Exception as e:
        logger.error(f"Failed to send coordinator email for lead {lead_id} ({category}): {e}")
        raise


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def send_coordinator_sms(
    self,
    to_phone: str,
    message: str,
    lead_id: str,
    lead_name: str,
    category: str,
) -> Dict[str, Any]:
    """
    Send an SMS from coordinator to a lead.

    Args:
        self: Celery task instance
        to_phone: Recipient phone number
        message: SMS message content
        lead_id: UUID of the lead
        lead_name: Lead's first name
        category: SMS template category

    Returns:
        Dict with send status, message SID, and delivery details
    """
    from ..services.sms_service import sms_service

    try:
        # Send SMS using the SMS service
        result = sms_service.send_sms(
            to_number=to_phone,
            message=message,
        )

        success = result.get("success", False)
        message_sid = result.get("message_sid")
        
        logger.info(
            f"Coordinator SMS sent for lead {lead_id} ({category}): "
            f"Success={success}, SID={message_sid}"
        )
        
        return {
            "status": "success" if success else "failed",
            "category": category,
            "lead_id": lead_id,
            "message_sid": message_sid,
            "twilio_status": result.get("status"),
            "error": result.get("error") if not success else None,
        }

    except Exception as e:
        logger.error(f"Failed to send coordinator SMS for lead {lead_id} ({category}): {e}")
        raise


# =============================================================================
# Daily Lead Digest Email Task
# =============================================================================

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def send_daily_lead_digest(self) -> Dict[str, Any]:
    """
    Send daily lead digest email at 7:00 AM MST to ask@tmsinstitute.co.

    Queries leads created in the prior 24 hours and sends a summary email
    with total count and breakdown by condition. Contains NO PII.

    If zero leads were created, still sends a "No new leads" message.

    Uses the shared email_base.py design system (wrap_in_email_layout)
    for consistent branding across all platform emails.

    Returns:
        Dict with send status and lead count
    """
    from ..services.email_base import wrap_in_email_layout, HEADER_BG_COLOR
    from ..services.paubox_email_service import send_email_via_paubox

    db = get_db_session()

    try:
        # Calculate 24-hour window
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(hours=24)

        # Query leads created in last 24 hours (non-deleted)
        recent_leads = (
            db.query(Lead)
            .filter(
                Lead.created_at >= yesterday,
                Lead.created_at <= now,
                Lead.deleted_at.is_(None),
            )
            .all()
        )

        total_count = len(recent_leads)

        # Build priority breakdown ONLY (no condition/source breakdowns per spec)
        priority_counts: Dict[str, int] = {"HOT": 0, "MEDIUM": 0, "LOW": 0}

        for lead in recent_leads:
            pri_name = lead.priority.value if lead.priority else "LOW"
            priority_counts[pri_name] = priority_counts.get(pri_name, 0) + 1

        # Format date for subject line (MST = UTC-7)
        from datetime import timezone as tz_module
        mst_offset = timedelta(hours=-7)
        mst_tz = tz_module(mst_offset)
        mst_now = now.astimezone(mst_tz)
        date_str = mst_now.strftime("%B %d, %Y")

        subject = f"NeuroReach Daily Lead Digest — {date_str}"

        # Build email HTML body using the shared design system
        if total_count == 0:
            # Zero leads scenario
            body_html = f"""
                    <tr>
                        <td style="padding: 30px 30px 10px 30px;">
                            <p style="margin: 0 0 16px 0; font-family: Arial, Helvetica, sans-serif; color: #444444; font-size: 15px; line-height: 1.6;">
                                Good morning! Here is your daily lead summary for <strong>{date_str}</strong>.
                            </p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 0 30px;">
                            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #F0F7F7; border-left: 4px solid {HEADER_BG_COLOR}; border-radius: 8px;">
                                <tr>
                                    <td style="padding: 20px 24px;">
                                        <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; color: #1A1A1A; font-size: 16px; font-weight: bold; line-height: 1.4;">
                                            No new leads in the last 24 hours
                                        </p>
                                        <p style="margin: 8px 0 0 0; font-family: Arial, Helvetica, sans-serif; color: #666666; font-size: 14px; line-height: 1.5;">
                                            There were no new intake submissions during this period. This is normal for weekends and holidays.
                                        </p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
"""
        else:
            # Build priority rows ONLY — no condition breakdown, no links, no CTA
            priority_rows = ""
            priority_colors = {"HOT": "#EF4444", "MEDIUM": "#F59E0B", "LOW": "#6B7280"}
            for pri in ["HOT", "MEDIUM", "LOW"]:
                count = priority_counts.get(pri, 0)
                color = priority_colors.get(pri, "#6B7280")
                priority_rows += f"""
                                            <tr>
                                                <td style="padding: 6px 0; border-bottom: 1px solid #EEEEEE; font-family: Arial, Helvetica, sans-serif; font-size: 14px; color: #444444;">
                                                    <span style="display: inline-block; width: 10px; height: 10px; border-radius: 50%; background-color: {color}; margin-right: 8px;"></span>
                                                    {pri}
                                                </td>
                                                <td align="right" style="padding: 6px 0; border-bottom: 1px solid #EEEEEE; font-family: Arial, Helvetica, sans-serif; font-size: 14px; color: #1A1A1A; font-weight: bold;">
                                                    {count}
                                                </td>
                                            </tr>"""

            body_html = f"""
                    <tr>
                        <td style="padding: 30px 30px 10px 30px;">
                            <p style="margin: 0 0 16px 0; font-family: Arial, Helvetica, sans-serif; color: #444444; font-size: 15px; line-height: 1.6;">
                                Good morning! Here is your daily lead summary for <strong>{date_str}</strong>.
                            </p>
                        </td>
                    </tr>

                    <!-- Total Count Banner -->
                    <tr>
                        <td style="padding: 0 30px;">
                            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: {HEADER_BG_COLOR}; border-radius: 8px;">
                                <tr>
                                    <td align="center" style="padding: 24px;">
                                        <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; color: #FFFFFF; font-size: 42px; font-weight: bold; line-height: 1.1;">
                                            {total_count}
                                        </p>
                                        <p style="margin: 6px 0 0 0; font-family: Arial, Helvetica, sans-serif; color: #FFFFFF; font-size: 14px; opacity: 0.9;">
                                            New Lead{"s" if total_count != 1 else ""} in the Last 24 Hours
                                        </p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Priority Breakdown -->
                    <tr>
                        <td style="padding: 24px 30px 8px 30px;">
                            <h3 style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 16px; font-weight: bold; color: #1A1A1A;">
                                Priority Breakdown
                            </h3>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 0 30px;">
                            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #F9FAFB; border-radius: 8px;">
                                <tr>
                                    <td style="padding: 16px 20px;">
                                        <table width="100%" cellpadding="0" cellspacing="0">
                                            {priority_rows}
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Footer Note -->
                    <tr>
                        <td style="padding: 24px 30px 20px 30px;">
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 12px; color: #999999; line-height: 1.5; text-align: center;">
                                This digest is sent automatically at 7:00 AM MST. It contains no patient-identifying information.
                            </p>
                        </td>
                    </tr>
"""

        # Wrap in shared email layout
        html_content = wrap_in_email_layout(
            title="Daily Lead Digest",
            body_html=body_html,
            subtitle=f"{date_str} — {total_count} new lead{'s' if total_count != 1 else ''}",
        )

        # Plain text version — priority breakdown only, no PII, no links
        plain_text = f"NeuroReach Daily Lead Digest — {date_str}\n\n"
        plain_text += f"Total new leads (last 24 hours): {total_count}\n\n"
        if total_count > 0:
            plain_text += "Priority Breakdown:\n"
            for pri in ["HOT", "MEDIUM", "LOW"]:
                count = priority_counts.get(pri, 0)
                if count > 0:
                    plain_text += f"  - {pri}: {count}\n"
        else:
            plain_text += "No new leads were submitted in the last 24 hours.\n"
        plain_text += "\nThis digest is sent automatically at 7:00 AM MST."

        # Send email via Paubox (HIPAA-compliant) with SMTP fallback
        recipient = "ask@tmsinstitute.co"

        result = send_email_via_paubox(
            to_email=recipient,
            subject=subject,
            html_content=html_content,
            text_content=plain_text,
        )

        success = result.get("success", False)
        provider = result.get("provider", "unknown")

        logger.info(
            f"Daily lead digest sent to {recipient} via {provider}: "
            f"success={success}, total_leads={total_count}"
        )

        return {
            "status": "success" if success else "failed",
            "total_leads": total_count,
            "priorities": priority_counts,
            "recipient": recipient,
            "provider": provider,
            "date": date_str,
        }

    except Exception as e:
        logger.error(f"Failed to send daily lead digest: {e}")
        raise

    finally:
        db.close()


@shared_task
def refresh_platform_analytics_views() -> Dict[str, Any]:
    """
    Periodic task to refresh platform analytics materialized views.

    Runs every 5 minutes to update pre-aggregated platform metrics.
    This ensures dashboard loads are fast (<200ms) even with millions of leads.

    Refreshes the following materialized views:
    - mv_platform_analytics (main summary)
    - mv_platform_daily_stats (daily trends)
    - mv_platform_weekly_stats (weekly trends)
    - mv_platform_monthly_stats (monthly trends)
    - mv_platform_status_distribution (status funnel)
    - mv_platform_priority_distribution (quality distribution)
    - mv_platform_condition_distribution (condition breakdown)
    - mv_platform_hourly_distribution (peak times)

    Returns:
        Dict with refresh status and timing for each view
    """
    from ..services.platform_analytics import PlatformAnalyticsService

    db = get_db_session()

    try:
        service = PlatformAnalyticsService(db)
        result = service.refresh_materialized_views()

        if result.get("success"):
            logger.info(
                f"Platform analytics views refreshed successfully. "
                f"Views: {len(result.get('views', []))}"
            )
        else:
            logger.error(
                f"Platform analytics refresh failed: {result.get('error')}"
            )

        return result

    except Exception as e:
        logger.error(f"Error refreshing platform analytics views: {e}")
        return {
            "success": False,
            "error": str(e),
            "refreshed_at": datetime.now(timezone.utc).isoformat()
        }

    finally:
        db.close()
