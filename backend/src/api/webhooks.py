"""
Jotform Webhook Integration for SleepReach Lead Scoring.

Receives leads from Jotform Sleep Clinic Patient Intake Assessment form,
applies our lead scoring logic (v2), and saves them to PostgreSQL.

V2 UPDATES:
- Uses canonical intake_mapping for consistent field mapping
- Uses lead_scoring_v2 for enhanced multi-condition scoring
- Stores multi-condition data, severity assessments, score breakdown
- Populates all new fields: conditions[], preferred_contact_method, etc.

NOTE: No Google Ads webhook — SleepReach only supports Widget, Jotform, Referral sources.
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Form, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.security import is_in_service_area
from ..models.lead import (
    Lead,
    LeadSource,
    LeadStatus,
    ConditionType,
    DurationType,
    TreatmentType,
    UrgencyType,
    PriorityType,
    ContactOutcome,
)
from ..models.provider import ReferringProvider, ProviderStatus
from ..services.encryption import EncryptionService
from ..services.audit import AuditService
from ..services.lead_number import generate_unique_lead_number
from ..services.cache import get_cache
from ..services.intake_mapping import (
    map_jotform_submission_to_lead_input,
    LeadInput,
    normalize_conditions_list,
    normalize_duration,
    normalize_treatments,
    normalize_urgency,
    normalize_contact_method,
)
from ..services.lead_scoring_v2 import (
    calculate_lead_score,
    ScoreBreakdown,
    is_in_service_area as check_service_area,
)
from sqlalchemy import func


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks", tags=["Webhooks"])


# =============================================================================
# Configuration
# =============================================================================

JOTFORM_FORM_ID = "260953996150062"

# Idempotency window: reject duplicate submissions within this many seconds.
# Jotform may retry on timeout — this prevents duplicate leads.
IDEMPOTENCY_WINDOW_SECONDS = 300  # 5 minutes


# =============================================================================
# Field Mapping Configuration (Sleep Clinic)
# =============================================================================

CONDITION_MAP = {
    "insomnia": ConditionType.INSOMNIA,
    "sleep apnea": ConditionType.SLEEP_APNEA,
    "sleep_apnea": ConditionType.SLEEP_APNEA,
    "restless leg": ConditionType.RESTLESS_LEG,
    "restless_leg": ConditionType.RESTLESS_LEG,
    "restless leg syndrome": ConditionType.RESTLESS_LEG,
    "rls": ConditionType.RESTLESS_LEG,
    "narcolepsy": ConditionType.NARCOLEPSY,
    "other": ConditionType.OTHER,
}

DURATION_MAP = {
    "less than 6 months": DurationType.LESS_THAN_6_MONTHS,
    "6 to 12 months": DurationType.SIX_TO_TWELVE_MONTHS,
    "more than 12 months": DurationType.MORE_THAN_12_MONTHS,
}

TREATMENT_KEYWORDS = {
    "cpap": TreatmentType.CPAP_BIPAP,
    "bipap": TreatmentType.CPAP_BIPAP,
    "bi-pap": TreatmentType.CPAP_BIPAP,
    "medication": TreatmentType.MEDICATION,
    "sleep study": TreatmentType.SLEEP_STUDY,
    "polysomnography": TreatmentType.SLEEP_STUDY,
    "therapy": TreatmentType.THERAPY_CBT,
    "cbt": TreatmentType.THERAPY_CBT,
    "cognitive": TreatmentType.THERAPY_CBT,
    "counseling": TreatmentType.THERAPY_CBT,
}

URGENCY_MAP = {
    "as soon as possible": UrgencyType.ASAP,
    "asap": UrgencyType.ASAP,
    "within a month": UrgencyType.WITHIN_30_DAYS,
    "within 30 days": UrgencyType.WITHIN_30_DAYS,
    "within a few months": UrgencyType.EXPLORING,
    "exploring": UrgencyType.EXPLORING,
    "just exploring options": UrgencyType.EXPLORING,
}

# Scoring Constants (matching widget scoring for sleep conditions)
CONDITION_SCORES = {
    ConditionType.INSOMNIA: 50,
    ConditionType.SLEEP_APNEA: 50,
    ConditionType.RESTLESS_LEG: 50,
    ConditionType.NARCOLEPSY: 50,
    ConditionType.OTHER: 0,
}

DURATION_SCORES = {
    DurationType.MORE_THAN_12_MONTHS: 20,
    DurationType.SIX_TO_TWELVE_MONTHS: 10,
    DurationType.LESS_THAN_6_MONTHS: 0,
}

URGENCY_SCORES = {
    UrgencyType.ASAP: 25,
    UrgencyType.WITHIN_30_DAYS: 10,
    UrgencyType.EXPLORING: 0,
}

INSURANCE_YES_SCORE = 30
INSURANCE_NO_SCORE = -20
IN_SERVICE_AREA_SCORE = 25
OUT_OF_SERVICE_AREA_SCORE = -100
CPAP_SCORE = 20
MEDICATION_SCORE = 15
SLEEP_STUDY_SCORE = 10
THERAPY_SCORE = 15
PROVIDER_REFERRAL_BONUS = 15
HOT_THRESHOLD = 120
MEDIUM_THRESHOLD = 70


# =============================================================================
# Helper Functions
# =============================================================================

def sanitize_input(value: Any) -> str:
    """Sanitize input to prevent injection attacks."""
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return str(value)
    return str(value).strip()


def get_client_ip(request: Request) -> Optional[str]:
    """Extract client IP from request headers."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def parse_jotform_payload(raw_request: str) -> Dict[str, Any]:
    """Parse Jotform rawRequest JSON string."""
    try:
        return json.loads(raw_request)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Jotform payload: {e}")
        raise ValueError(f"Invalid JSON in rawRequest: {e}")


def map_condition(conditions: List[str]) -> ConditionType:
    """Map Jotform condition values to our enum."""
    if not conditions:
        return ConditionType.OTHER
    condition_lower = conditions[0].lower().strip()
    for key, value in CONDITION_MAP.items():
        if key in condition_lower:
            return value
    return ConditionType.OTHER


def map_duration(duration: str) -> DurationType:
    """Map Jotform duration value to our enum."""
    if not duration:
        return DurationType.LESS_THAN_6_MONTHS
    duration_lower = duration.lower().strip()
    for key, value in DURATION_MAP.items():
        if key in duration_lower:
            return value
    return DurationType.LESS_THAN_6_MONTHS


def map_treatments(treatments: List[str]) -> List[TreatmentType]:
    """Map Jotform treatment values to our enum list."""
    if not treatments:
        return [TreatmentType.NONE]
    result = set()
    for treatment in treatments:
        treatment_lower = treatment.lower()
        for keyword, treatment_type in TREATMENT_KEYWORDS.items():
            if keyword in treatment_lower:
                result.add(treatment_type)
    if not result:
        return [TreatmentType.NONE]
    return list(result)


def map_urgency(urgency: str) -> UrgencyType:
    """Map Jotform urgency value to our enum."""
    if not urgency:
        return UrgencyType.EXPLORING
    urgency_lower = urgency.lower().strip()
    for key, value in URGENCY_MAP.items():
        if key in urgency_lower:
            return value
    return UrgencyType.EXPLORING


def parse_yes_no(value: str) -> bool:
    """Parse yes/no string to boolean."""
    if not value:
        return False
    return value.lower().strip() in ["yes", "true", "1", "y"]


def normalize_phone(phone: str) -> str:
    """Normalize phone number."""
    if not phone:
        return ""
    digits = re.sub(r"[^\d+]", "", phone)
    return digits if digits else phone


def normalize_zip(zip_code: str) -> str:
    """Normalize ZIP code to 5 digits."""
    if not zip_code:
        return "00000"
    digits = re.sub(r"[^\d]", "", zip_code)
    return digits[:5] if len(digits) >= 5 else digits.zfill(5)


def get_raw_specialty(specialty_str: str) -> str:
    """
    Return specialty string as-is (raw text).
    RULE: User types X -> Database stores X -> Dashboard shows X
    No mapping, no transformation, no enum.
    """
    if not specialty_str:
        return ""
    return specialty_str.strip()


def find_or_create_provider(
    db: Session,
    provider_name: str,
    practice_name: str,
    provider_email: str,
    provider_specialty: str = "",
) -> Optional[ReferringProvider]:
    """
    Find existing provider or create a new one from Jotform referral data.
    """
    if not provider_name or provider_name.strip() in ["", "N/A", "n/a", "NA"]:
        return None
    
    provider_name = provider_name.strip()
    practice_name = practice_name.strip() if practice_name else None
    provider_email = provider_email.strip().lower() if provider_email else None
    specialty_raw = get_raw_specialty(provider_specialty)
    
    def update_provider_if_needed(provider: ReferringProvider) -> ReferringProvider:
        """Update provider with new email/specialty if they're missing."""
        updated = False
        if not provider.email and provider_email and "@" in provider_email:
            provider.email = provider_email
            updated = True
        if not provider.practice_name and practice_name and practice_name not in ["", "N/A", "n/a", "NA"]:
            provider.practice_name = practice_name
            updated = True
        if not provider.specialty and specialty_raw:
            provider.specialty = specialty_raw
            updated = True
        if updated:
            try:
                db.flush()
            except Exception as e:
                logger.warning(f"Failed to update provider: {e}")
        return provider
    
    # 1. Try exact email match first
    if provider_email and "@" in provider_email:
        existing = db.query(ReferringProvider).filter(
            func.lower(ReferringProvider.email) == provider_email
        ).first()
        if existing:
            return update_provider_if_needed(existing)
    
    # 2. Try exact name match
    name_matches = db.query(ReferringProvider).filter(
        ReferringProvider.name.ilike(f"%{provider_name}%")
    ).all()
    for provider in name_matches:
        if provider.name.lower() == provider_name.lower():
            return update_provider_if_needed(provider)
    
    # 3. Try name + practice combination
    if practice_name and practice_name not in ["", "N/A", "n/a", "NA"]:
        practice_matches = db.query(ReferringProvider).filter(
            ReferringProvider.practice_name.ilike(f"%{practice_name}%")
        ).all()
        for provider in practice_matches:
            if provider_name.lower() in provider.name.lower() or provider.name.lower() in provider_name.lower():
                return update_provider_if_needed(provider)
    
    # 4. Create new provider
    new_provider = ReferringProvider(
        name=provider_name,
        email=provider_email if provider_email and "@" in provider_email else None,
        practice_name=practice_name if practice_name and practice_name not in ["", "N/A"] else None,
        specialty=specialty_raw if specialty_raw else None,
        status=ProviderStatus.PENDING,
    )
    
    try:
        db.add(new_provider)
        db.flush()
        logger.info(f"Created new provider: {new_provider.name} ({new_provider.id})")
        return new_provider
    except Exception as e:
        logger.warning(f"Failed to create provider: {e}")
        db.rollback()
        return None


def extract_patient_name(data: Dict[str, Any]) -> tuple:
    """Extract patient name from Jotform submission."""
    first_name = ""
    last_name = ""

    name_fields = [
        "q30_fullName", "q30_name",
        "q38_contactInformation", "q3_fullName", "q3_name",
        "q4_fullName", "q4_name", "name", "full_name",
        "patient_name", "patientName", "contact_information",
    ]
    
    for field in name_fields:
        if field in data:
            value = data[field]
            if isinstance(value, dict):
                first = sanitize_input(value.get("first", "") or value.get("firstName", ""))
                last = sanitize_input(value.get("last", "") or value.get("lastName", ""))
                if first or last:
                    first_name = first
                    last_name = last
                    break
            elif isinstance(value, str) and value.strip():
                parts = value.strip().split(' ', 1)
                first_name = sanitize_input(parts[0])
                last_name = sanitize_input(parts[1]) if len(parts) > 1 else ""
                break
    
    if not first_name:
        for field in ["first_name", "firstName", "q_first_name"]:
            if field in data and data[field]:
                first_name = sanitize_input(str(data[field]))
                break
        for field in ["last_name", "lastName", "q_last_name"]:
            if field in data and data[field]:
                last_name = sanitize_input(str(data[field]))
                break
    
    return first_name, last_name


def extract_provider_email(data: Dict[str, Any]) -> str:
    """Extract provider email from Jotform."""
    email_fields = [
        "q15_providerEmail", "q15_providersEmail",
        "q46_providersEmail", "q46_providerEmail",
        "q47_providersEmail", "q47_providerEmail",
        "providersEmail", "providerEmail",
        "referring_provider_email", "referrerEmail",
    ]
    for field in email_fields:
        value = data.get(field, "")
        if value and isinstance(value, str) and "@" in value:
            return sanitize_input(value).lower()
    
    for key, value in data.items():
        key_lower = key.lower()
        if "email" in key_lower and ("provider" in key_lower or "referr" in key_lower):
            if value and isinstance(value, str) and "@" in value:
                return sanitize_input(value).lower()
    
    return ""


def extract_provider_specialty(data: Dict[str, Any]) -> str:
    """Extract provider specialty from Jotform."""
    specialty_fields = [
        "q14_specialty", "q14_providerSpecialty",
        "q48_providerSpecialty", "q47_providerSpecialty",
        "providerSpecialty", "providersSpecialty",
        "provider_specialty", "specialty", "Specialty",
    ]
    for field in specialty_fields:
        value = data.get(field, "")
        if value and isinstance(value, str) and value.strip():
            return sanitize_input(value).strip()
    
    for key, value in data.items():
        key_lower = key.lower()
        if "specialty" in key_lower or "speciality" in key_lower:
            if value and isinstance(value, str) and value.strip():
                return sanitize_input(value).strip()
    
    return ""


def extract_jotform_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract and map all fields from Jotform payload.

    NEW Jotform form ID: 260953996150062
    Field mapping (question ID → field):
      q5  → privacy_consent          q6  → sleep_concerns (multi)
      q7  → sleep_concern_other      q8  → treatment_interest
      q9  → symptom_duration         q10 → treatment_history (multi)
      q11 → urgency                  q12 → referred_by_provider (Yes/No)
      q13 → referral_provider_name   q14 → referral_specialty
      q15 → referral_provider_email  q16 → referral_clinic
      q30 → full_name (first/last)   q19 → email
      q20 → phone                    q21 → date_of_birth
      q22 → preferred_contact_method q24 → has_insurance
      q25 → insurance_provider       q26 → zip_code
      q23 → sms_consent
    """
    first_name, last_name = extract_patient_name(data)

    # Email — q19
    email = sanitize_input(
        data.get("q19_email", "") or data.get("q19_emailAddress", "")
        or data.get("q39_email", "") or data.get("email", "")
    )

    # Phone — q20
    phone_data = data.get("q20_phoneNumber", data.get("q20_phone", data.get("q40_phoneNumber", {})))
    if isinstance(phone_data, dict):
        phone = normalize_phone(sanitize_input(phone_data.get("full", "")))
    else:
        phone = normalize_phone(sanitize_input(phone_data))

    # Sleep concerns — q6 (multi-select)
    conditions_raw = data.get("q6_whatSleep", data.get("q6_sleepConcerns", data.get("q12_whatCondition", [])))
    if isinstance(conditions_raw, str):
        conditions_raw = [conditions_raw]
    conditions = map_condition(conditions_raw)

    # Other sleep concern text — q7
    # (stored in other_condition_text via intake_mapping)

    # Symptom duration — q9
    duration = map_duration(sanitize_input(
        data.get("q9_howLong", "") or data.get("q9_symptomDuration", "")
        or data.get("q21_howLong", "")
    ))

    # Treatment history — q10 (multi-select)
    treatments_raw = data.get("q10_whatHave", data.get("q10_treatmentHistory", data.get("q22_whatTreatments", [])))
    if isinstance(treatments_raw, str):
        treatments_raw = [treatments_raw]
    treatments = map_treatments(treatments_raw)

    # Insurance — q24
    has_insurance = parse_yes_no(sanitize_input(
        data.get("q24_doYou", "") or data.get("q24_insurance", "")
    ))
    insurance_provider = sanitize_input(
        data.get("q25_insuranceProvider", "") or data.get("q25_insurance", "")
    )

    # ZIP code — q26
    zip_code = normalize_zip(sanitize_input(
        data.get("q26_zipCode", "") or data.get("q26_whatIs", "")
    ))

    # Urgency — q11
    urgency = map_urgency(sanitize_input(
        data.get("q11_howSoon", "") or data.get("q11_urgency", "")
        or data.get("q27_whenWould", "")
    ))

    # Referral — q12 (Yes/No), q13 (provider name), q16 (clinic)
    referred_by_provider = parse_yes_no(sanitize_input(
        data.get("q12_wereYou", "") or data.get("q12_referral", "")
        or data.get("q43_wereYou", "")
    ))

    referring_provider_email = extract_provider_email(data)
    referring_provider_specialty = extract_provider_specialty(data)

    return {
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone": phone,
        "condition": conditions,
        "symptom_duration": duration,
        "prior_treatments": treatments,
        "has_insurance": has_insurance,
        "insurance_provider": insurance_provider if has_insurance else None,
        "zip_code": zip_code,
        "urgency": urgency,
        "referred_by_provider": referred_by_provider,
        "referring_provider_name": sanitize_input(
            data.get("q13_providerName", "") or data.get("q13_provider", "")
            or data.get("q44_referringProviders", "")
        ),
        "referring_clinic": sanitize_input(
            data.get("q16_clinicOr", "") or data.get("q16_clinic", "")
            or data.get("q45_clinicpracticeName", "")
        ),
        "referring_provider_email": referring_provider_email,
        "referring_provider_specialty": referring_provider_specialty,
    }


# =============================================================================
# Webhook Endpoint
# =============================================================================

@router.post(
    "/jotform",
    status_code=status.HTTP_200_OK,
    summary="Jotform Webhook",
    description="Receives leads from Jotform Sleep Clinic Patient Intake Assessment form.",
)
async def jotform_webhook(
    request: Request,
    rawRequest: str = Form(default=None),
    formID: str = Form(default=None),
    db: Session = Depends(get_db),
):
    """
    Receive and process leads from Jotform.
    
    V2 UPDATE: Uses canonical mapping layer and new scoring engine.
    Populates new fields: conditions[], preferred_contact_method, etc.
    """
    try:
        logger.info(f"Jotform webhook received - Form ID: {formID}")
        form_data = await request.form()
        
        if not formID:
            formID = form_data.get("formID", "")
        
        if formID != JOTFORM_FORM_ID:
            logger.warning(f"Invalid form ID: {formID}")
            raise HTTPException(status_code=400, detail=f"Invalid form ID")
        
        raw_request_data = rawRequest or form_data.get("rawRequest", "")
        if not raw_request_data:
            data = dict(form_data)
        else:
            data = parse_jotform_payload(raw_request_data)
        
        # =====================================================================
        # IDEMPOTENCY CHECK
        # =====================================================================
        from datetime import timedelta

        submission_id: str = (
            str(form_data.get("submissionID", "") or form_data.get("submissionId", "")).strip()
        )

        if submission_id:
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=IDEMPOTENCY_WINDOW_SECONDS)
            dup = db.query(Lead.id, Lead.lead_number).filter(
                Lead.source.in_([LeadSource.jotform, LeadSource.referral]),
                Lead.notes.contains(f"[submissionID:{submission_id}]"),
                Lead.created_at >= cutoff,
            ).first()
            if dup:
                logger.warning(f"Jotform duplicate detected via submissionID={submission_id}")
                return JSONResponse(
                    status_code=200,
                    content={
                        "success": True,
                        "message": "Duplicate submission detected, original lead preserved",
                        "lead_number": dup.lead_number,
                        "duplicate": True,
                    },
                )
        else:
            client_ip_early = get_client_ip(request)
            ip_hash_early = EncryptionService.hash_ip(client_ip_early) if client_ip_early else None
            if ip_hash_early:
                cutoff = datetime.now(timezone.utc) - timedelta(seconds=IDEMPOTENCY_WINDOW_SECONDS)
                duplicate = db.query(Lead.id, Lead.lead_number).filter(
                    Lead.ip_address_hash == ip_hash_early,
                    Lead.source.in_([LeadSource.jotform, LeadSource.referral]),
                    Lead.created_at >= cutoff,
                ).first()
                if duplicate:
                    logger.warning(f"Jotform duplicate detected via IP hash")
                    return JSONResponse(
                        status_code=200,
                        content={
                            "success": True,
                            "message": "Duplicate submission detected, original lead preserved",
                            "lead_number": duplicate.lead_number,
                            "duplicate": True,
                        },
                    )

        # =====================================================================
        # V2: Use canonical mapping layer
        # =====================================================================
        lead_input: LeadInput = map_jotform_submission_to_lead_input(data)
        logger.info(f"Jotform mapped conditions: {lead_input.conditions}, primary: {lead_input.primary_condition}")
        
        # Also extract legacy mapped data for backward compatibility
        mapped_data = extract_jotform_data(data)
        
        # =====================================================================
        # V2: Use new scoring engine with multi-condition support
        # =====================================================================
        score_breakdown: ScoreBreakdown = calculate_lead_score(
            lead_input,
            referred_by_provider=lead_input.referred_by_provider
        )
        
        score = score_breakdown.lead_score
        priority_str = score_breakdown.priority
        in_service_area = score_breakdown.in_service_area
        
        priority_map = {
            "hot": PriorityType.HOT,
            "medium": PriorityType.MEDIUM,
            "low": PriorityType.LOW,
            "disqualified": PriorityType.DISQUALIFIED,
        }
        priority = priority_map.get(priority_str, PriorityType.LOW)
        
        # Encrypt PHI fields
        first_name_encrypted = EncryptionService.encrypt_field(lead_input.first_name)
        last_name_encrypted = EncryptionService.encrypt_field(lead_input.last_name)
        email_encrypted = EncryptionService.encrypt_field(lead_input.email)
        phone_encrypted = EncryptionService.encrypt_field(lead_input.phone)
        
        lead_number = generate_unique_lead_number(db)
        client_ip = get_client_ip(request)
        user_agent = request.headers.get("User-Agent")
        now = datetime.now(timezone.utc)
        
        # Process referral information
        referral_notes = None
        referring_provider = None
        referring_provider_raw = None
        is_referral = lead_input.referred_by_provider
        
        if is_referral:
            referring_provider_raw = {
                "provider_name": lead_input.referring_provider_name,
                "clinic_name": lead_input.referring_clinic,
                "provider_email": lead_input.referring_provider_email,
                "source": "jotform",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            
            parts = []
            if lead_input.referring_provider_name and lead_input.referring_provider_name not in ["N/A", "n/a", "", "NA"]:
                parts.append(f"Provider: {lead_input.referring_provider_name}")
            if lead_input.referring_clinic and lead_input.referring_clinic not in ["N/A", "n/a", "", "NA"]:
                parts.append(f"Clinic: {lead_input.referring_clinic}")
            if parts:
                referral_notes = "[Jotform Referral] " + ", ".join(parts)
            
            referring_provider = find_or_create_provider(
                db=db,
                provider_name=lead_input.referring_provider_name,
                practice_name=lead_input.referring_clinic,
                provider_email=lead_input.referring_provider_email,
                provider_specialty=mapped_data.get("referring_provider_specialty", ""),
            )
        
        # Set source based on referral status
        lead_source = LeadSource.referral if is_referral else LeadSource.jotform
        
        # Map normalized duration to enum
        duration_enum_map = {
            "less_than_6_months": DurationType.LESS_THAN_6_MONTHS,
            "6_to_12_months": DurationType.SIX_TO_TWELVE_MONTHS,
            "more_than_12_months": DurationType.MORE_THAN_12_MONTHS,
        }
        symptom_duration = duration_enum_map.get(
            lead_input.symptom_duration,
            DurationType.LESS_THAN_6_MONTHS
        )
        
        # Map normalized urgency to enum
        urgency_enum_map = {
            "asap": UrgencyType.ASAP,
            "within_30_days": UrgencyType.WITHIN_30_DAYS,
            "exploring": UrgencyType.EXPLORING,
        }
        urgency = urgency_enum_map.get(lead_input.urgency, UrgencyType.EXPLORING)
        
        # Map primary condition to enum (sleep conditions)
        condition_enum_map = {
            "insomnia": ConditionType.INSOMNIA,
            "sleep_apnea": ConditionType.SLEEP_APNEA,
            "restless_leg": ConditionType.RESTLESS_LEG,
            "narcolepsy": ConditionType.NARCOLEPSY,
            "other": ConditionType.OTHER,
        }
        primary_condition = condition_enum_map.get(
            lead_input.primary_condition,
            ConditionType.OTHER
        )
        
        # Map normalized treatments to enum list (sleep treatments)
        treatment_enum_map = {
            "cpap_bipap": TreatmentType.CPAP_BIPAP,
            "medication": TreatmentType.MEDICATION,
            "sleep_study": TreatmentType.SLEEP_STUDY,
            "therapy_cbt": TreatmentType.THERAPY_CBT,
            "none": TreatmentType.NONE,
            "other": TreatmentType.OTHER,
        }
        prior_treatments = [
            treatment_enum_map.get(t, TreatmentType.OTHER)
            for t in lead_input.prior_treatments
        ] or [TreatmentType.NONE]
        
        # Map preferred contact method
        contact_method_map = {
            "phone_call": "phone",
            "text": "sms",
            "email": "email",
            "any": "any",
        }
        preferred_contact = contact_method_map.get(
            lead_input.preferred_contact_method,
            lead_input.preferred_contact_method
        ) if lead_input.preferred_contact_method else None
        
        # =====================================================================
        # Create Lead record
        # =====================================================================
        lead = Lead(
            lead_number=lead_number,
            first_name_encrypted=first_name_encrypted,
            last_name_encrypted=last_name_encrypted,
            email_encrypted=email_encrypted,
            phone_encrypted=phone_encrypted,
            
            # Primary condition
            condition=primary_condition,
            
            # Multi-condition support
            conditions=lead_input.conditions if lead_input.conditions else [],
            other_condition_text=lead_input.other_condition_text,
            
            # Preferred contact method
            preferred_contact_method=preferred_contact,
            
            # Sleep treatment interest
            sleep_treatment_interest=lead_input.sleep_treatment_interest,
            
            # Clinical info
            symptom_duration=symptom_duration,
            prior_treatments=prior_treatments,
            
            # Insurance
            has_insurance=lead_input.has_insurance,
            insurance_provider=lead_input.insurance_provider,
            other_insurance_provider=lead_input.other_insurance_provider,
            
            # Location
            zip_code=lead_input.zip_code,
            in_service_area=in_service_area,
            
            # Urgency & Consent
            urgency=urgency,
            hipaa_consent=True,
            hipaa_consent_timestamp=now,
            privacy_consent_timestamp=now,
            sms_consent=lead_input.sms_consent,
            
            # Enhanced scoring with breakdown
            score=score,
            priority=priority,
            
            # Score breakdown components
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
            contact_outcome=ContactOutcome.NEW,
            source=lead_source,
            notes="\n".join(filter(None, [
                referral_notes,
                f"[submissionID:{submission_id}]" if submission_id else None,
            ])) or None,
            
            # Referral tracking
            is_referral=is_referral,
            referring_provider_id=referring_provider.id if referring_provider else None,
            referring_provider_raw=referring_provider_raw,
            
            # Tracking fields
            ip_address_hash=EncryptionService.hash_ip(client_ip),
            user_agent=user_agent,
            utm_source="referral" if is_referral else "jotform",
            utm_medium="provider_referral" if is_referral else "form",
            utm_campaign=f"referral_{formID}" if is_referral else f"form_{formID}",
        )
        
        db.add(lead)
        db.commit()
        db.refresh(lead)
        
        # Update provider referral count
        if referring_provider:
            actual_count = db.query(func.count(Lead.id)).filter(
                Lead.referring_provider_id == referring_provider.id,
                Lead.deleted_at.is_(None),
            ).scalar() or 0
            referring_provider.total_referrals = actual_count
            referring_provider.last_referral_at = now
            db.commit()
        
        logger.info(
            f"Jotform lead created: {lead.lead_number}, "
            f"conditions={lead_input.conditions}, "
            f"preferred_contact={preferred_contact}, "
            f"score={score}, priority={priority.value}"
        )
        
        try:
            cache = get_cache()
            cache.invalidate_on_lead_change()
        except Exception:
            pass
        
        # Send confirmation email
        try:
            from ..services.sync_notifications import dispatch_lead_receipt_notifications
            decrypted_email = EncryptionService.decrypt_field(lead.email_encrypted)
            decrypted_first = EncryptionService.decrypt_field(lead.first_name_encrypted)
            decrypted_phone = EncryptionService.decrypt_field(lead.phone_encrypted)
            if decrypted_email:
                dispatch_lead_receipt_notifications(
                    lead_id=str(lead.id),
                    email=decrypted_email,
                    phone=decrypted_phone or "",
                    first_name=decrypted_first or "",
                    lead_number=lead.lead_number,
                    conditions=lead_input.conditions or [],
                    other_condition_text=lead_input.other_condition_text or "",
                )
        except Exception as e:
            logger.warning(f"Failed to send confirmation email for Jotform lead {lead.lead_number}: {e}")
        
        try:
            audit_service = AuditService(db)
            audit_service.log_create(
                table_name="leads",
                record_id=lead.id,
                ip_address=client_ip,
                endpoint="/api/webhooks/jotform",
                request_method="POST",
                user_agent=user_agent,
                new_values={
                    "source": "jotform",
                    "priority": priority.value,
                    "conditions": lead_input.conditions,
                    "preferred_contact_method": preferred_contact,
                },
            )
        except Exception:
            pass
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Lead received",
                "lead_number": lead.lead_number,
                "priority": priority.value,
                "score": score,
                "conditions": lead_input.conditions,
                "preferred_contact_method": preferred_contact,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Jotform webhook error: {type(e).__name__}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Error processing lead")


@router.get("/jotform/test", summary="Test Jotform Webhook")
async def test_jotform_webhook():
    """Test endpoint to verify the webhook is accessible."""
    return {
        "status": "ok",
        "message": "Jotform webhook is active",
        "expected_form_id": JOTFORM_FORM_ID,
        "endpoint": "/api/webhooks/jotform",
    }
