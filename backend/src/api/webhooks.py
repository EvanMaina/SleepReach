"""
Jotform Webhook Integration for TMS Lead Scoring.

Receives leads from Jotform TMS Therapy Patient Intake Assessment form,
applies our lead scoring logic (v2), and saves them to PostgreSQL.

V2 UPDATES:
- Uses canonical intake_mapping for consistent field mapping
- Uses lead_scoring_v2 for enhanced multi-condition scoring
- Stores multi-condition data, severity assessments, score breakdown
- Populates all new fields: conditions[], preferred_contact_method, etc.
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
from ..models.provider import ReferringProvider, ProviderStatus, ProviderSpecialty
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

JOTFORM_FORM_ID = "260267308720050"

# Idempotency window: reject duplicate submissions within this many seconds.
# Jotform / Google Ads may retry on timeout — this prevents duplicate leads.
IDEMPOTENCY_WINDOW_SECONDS = 300  # 5 minutes


# =============================================================================
# Field Mapping Configuration
# =============================================================================

CONDITION_MAP = {
    "depression": ConditionType.DEPRESSION,
    "anxiety": ConditionType.ANXIETY,
    "ocd": ConditionType.OCD,
    "obsessive compulsive disorder": ConditionType.OCD,
    "ptsd": ConditionType.PTSD,
    "post-traumatic stress disorder": ConditionType.PTSD,
    "other": ConditionType.OTHER,
}

DURATION_MAP = {
    "less than 6 months": DurationType.LESS_THAN_6_MONTHS,
    "6 to 12 months": DurationType.SIX_TO_TWELVE_MONTHS,
    "more than 12 months": DurationType.MORE_THAN_12_MONTHS,
}

TREATMENT_KEYWORDS = {
    "antidepressant": TreatmentType.ANTIDEPRESSANTS,
    "zoloft": TreatmentType.ANTIDEPRESSANTS,
    "lexapro": TreatmentType.ANTIDEPRESSANTS,
    "prozac": TreatmentType.ANTIDEPRESSANTS,
    "anti-anxiety": TreatmentType.ANTIDEPRESSANTS,
    "xanax": TreatmentType.ANTIDEPRESSANTS,
    "ativan": TreatmentType.ANTIDEPRESSANTS,
    "buspar": TreatmentType.ANTIDEPRESSANTS,
    "therapy": TreatmentType.THERAPY_CBT,
    "cbt": TreatmentType.THERAPY_CBT,
    "cognitive": TreatmentType.THERAPY_CBT,
    "counseling": TreatmentType.THERAPY_CBT,
    "psychotherapy": TreatmentType.THERAPY_CBT,
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

# Scoring Constants (matching widget scoring)
CONDITION_SCORES = {
    ConditionType.DEPRESSION: 50,
    ConditionType.ANXIETY: 50,
    ConditionType.OCD: 50,
    ConditionType.PTSD: 50,
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
ANTIDEPRESSANT_SCORE = 20
THERAPY_SCORE = 15
BOTH_TREATMENTS_BONUS = 10
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


def calculate_jotform_lead_score(
    condition: ConditionType,
    duration: DurationType,
    treatments: List[TreatmentType],
    has_insurance: bool,
    insurance_provider: Optional[str],
    zip_code: str,
    urgency: UrgencyType,
    referred_by_provider: bool = False,
) -> tuple:
    """Calculate lead score using same logic as widget scoring."""
    score = 0
    score += CONDITION_SCORES.get(condition, 0)
    score += DURATION_SCORES.get(duration, 0)
    
    has_meds = TreatmentType.ANTIDEPRESSANTS in treatments
    has_therapy = TreatmentType.THERAPY_CBT in treatments
    if has_meds:
        score += ANTIDEPRESSANT_SCORE
    if has_therapy:
        score += THERAPY_SCORE
    if has_meds and has_therapy:
        score += BOTH_TREATMENTS_BONUS
    
    if has_insurance:
        score += INSURANCE_YES_SCORE
    else:
        score += INSURANCE_NO_SCORE
    
    in_service_area = is_in_service_area(zip_code)
    if in_service_area:
        score += IN_SERVICE_AREA_SCORE
    else:
        score += OUT_OF_SERVICE_AREA_SCORE
    
    score += URGENCY_SCORES.get(urgency, 0)
    
    if referred_by_provider:
        score += PROVIDER_REFERRAL_BONUS
    
    if score >= HOT_THRESHOLD:
        priority = PriorityType.HOT
    elif score >= MEDIUM_THRESHOLD:
        priority = PriorityType.MEDIUM
    elif score >= 0:
        priority = PriorityType.LOW
    else:
        priority = PriorityType.DISQUALIFIED
    
    return score, priority, in_service_area


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
    
    Matching strategy:
    1. Exact email match (highest confidence)
    2. Fuzzy name + practice match
    3. Create new provider if no match found
    
    IMPORTANT: Also updates existing provider's email/specialty if missing.
    
    Args:
        db: Database session
        provider_name: Referring provider's name from Jotform
        practice_name: Practice/clinic name from Jotform
        provider_email: Provider's email from Jotform
        provider_specialty: Provider's specialty from Jotform
        
    Returns:
        ReferringProvider instance (existing or newly created)
    """
    # Skip if no meaningful data provided
    if not provider_name or provider_name.strip() in ["", "N/A", "n/a", "NA"]:
        return None
    
    provider_name = provider_name.strip()
    practice_name = practice_name.strip() if practice_name else None
    provider_email = provider_email.strip().lower() if provider_email else None
    # RULE: Store exact user input - no mapping, no transformation
    specialty_raw = get_raw_specialty(provider_specialty)
    
    # Flag to track if we need to update an existing provider
    def update_provider_if_needed(provider: ReferringProvider) -> ReferringProvider:
        """Update provider with new email/specialty if they're missing."""
        updated = False
        
        # Update email if provider doesn't have one and we have a valid email
        if not provider.email and provider_email and "@" in provider_email:
            provider.email = provider_email
            updated = True
            logger.info(f"Updated provider {provider.name} with email: {provider_email}")
        
        # Update practice name if missing
        if not provider.practice_name and practice_name and practice_name not in ["", "N/A", "n/a", "NA"]:
            provider.practice_name = practice_name
            updated = True
            logger.info(f"Updated provider {provider.name} with practice: {practice_name}")
        
        # Update specialty if not set and we have one
        # RULE: Store exact user input - no mapping, no transformation
        if not provider.specialty and specialty_raw:
            provider.specialty = specialty_raw
            updated = True
            logger.info(f"Updated provider {provider.name} with specialty: {specialty_raw}")
        
        if updated:
            try:
                db.flush()
            except Exception as e:
                logger.warning(f"Failed to update provider: {e}")
        
        return provider
    
    # 1. Try exact email match first (highest confidence)
    if provider_email and "@" in provider_email:
        existing = db.query(ReferringProvider).filter(
            func.lower(ReferringProvider.email) == provider_email
        ).first()
        if existing:
            logger.info(f"Provider matched by email: {existing.name} ({existing.id})")
            return update_provider_if_needed(existing)
    
    # 2. Try fuzzy name match
    # Look for providers with similar names
    name_matches = db.query(ReferringProvider).filter(
        ReferringProvider.name.ilike(f"%{provider_name}%")
    ).all()
    
    # Check for exact name match
    for provider in name_matches:
        if provider.name.lower() == provider_name.lower():
            logger.info(f"Provider matched by exact name: {provider.name} ({provider.id})")
            return update_provider_if_needed(provider)
    
    # 3. If practice name provided, try to match with practice
    if practice_name and practice_name not in ["", "N/A", "n/a", "NA"]:
        practice_matches = db.query(ReferringProvider).filter(
            ReferringProvider.practice_name.ilike(f"%{practice_name}%")
        ).all()
        
        # Look for name + practice combination
        for provider in practice_matches:
            if provider_name.lower() in provider.name.lower() or provider.name.lower() in provider_name.lower():
                logger.info(f"Provider matched by name+practice: {provider.name} ({provider.id})")
                return update_provider_if_needed(provider)
    
    # 4. No match found - create new provider with PENDING status
    # RULE: Store exact user input - no mapping, no transformation
    logger.info(f"Creating new provider: {provider_name} at {practice_name}, email={provider_email}, specialty={specialty_raw}")
    
    new_provider = ReferringProvider(
        name=provider_name,
        email=provider_email if provider_email and "@" in provider_email else None,
        practice_name=practice_name if practice_name and practice_name not in ["", "N/A"] else None,
        specialty=specialty_raw if specialty_raw else None,  # Store raw text as-is
        status=ProviderStatus.PENDING,  # Requires staff verification
    )
    
    try:
        db.add(new_provider)
        db.flush()  # Flush to get the ID but don't commit yet (will be committed with lead)
        logger.info(f"Created new provider: {new_provider.name} ({new_provider.id})")
        return new_provider
    except Exception as e:
        logger.warning(f"Failed to create provider: {e}")
        db.rollback()
        return None


def extract_patient_name(data: Dict[str, Any]) -> tuple:
    """
    Extract patient name from Jotform submission with robust field detection.
    Returns (first_name, last_name) - never returns "Unknown".
    """
    first_name = ""
    last_name = ""
    
    # Try multiple field patterns for contact/name info
    name_fields = [
        "q38_contactInformation",
        "q3_fullName",
        "q3_name",
        "q4_fullName",
        "q4_name",
        "name",
        "full_name",
        "patient_name",
        "patientName",
        "contact_information",
        "contactInformation",
    ]
    
    for field in name_fields:
        if field in data:
            value = data[field]
            
            # Handle nested name object (Jotform format: {first: "John", last: "Doe"})
            if isinstance(value, dict):
                first = sanitize_input(value.get("first", "") or value.get("firstName", ""))
                last = sanitize_input(value.get("last", "") or value.get("lastName", ""))
                if first or last:
                    first_name = first
                    last_name = last
                    break
            
            # Handle string name
            elif isinstance(value, str) and value.strip():
                parts = value.strip().split(' ', 1)
                first_name = sanitize_input(parts[0])
                last_name = sanitize_input(parts[1]) if len(parts) > 1 else ""
                break
    
    # Try separate first/last name fields if not found
    if not first_name:
        separate_first_fields = ["first_name", "firstName", "q_first_name"]
        separate_last_fields = ["last_name", "lastName", "q_last_name"]
        
        for field in separate_first_fields:
            if field in data and data[field]:
                first_name = sanitize_input(str(data[field]))
                break
        
        for field in separate_last_fields:
            if field in data and data[field]:
                last_name = sanitize_input(str(data[field]))
                break
    
    return first_name, last_name


def extract_provider_email(data: Dict[str, Any]) -> str:
    """
    Extract provider email from Jotform with multiple field name fallbacks.
    Jotform field names can vary, so we try multiple patterns.
    
    CRITICAL: This function must find the provider email for referrals.
    Logs all attempts for debugging.
    """
    # List of possible field names for provider email (ordered by likelihood)
    email_fields = [
        # Jotform question ID patterns (qXX_)
        "q46_providersEmail",
        "q46_providerEmail", 
        "q47_providersEmail",
        "q47_providerEmail",
        "q45_providersEmail",
        "q45_providerEmail",
        "q48_providersEmail",
        "q48_providerEmail",
        # Camel case patterns
        "providersEmail",
        "providerEmail",
        "referringProviderEmail",
        "referrerEmail",
        # Snake case patterns
        "providers_email",
        "provider_email",
        "referring_provider_email",
        "referrer_email",
    ]
    
    # Try direct field name matches first
    for field in email_fields:
        value = data.get(field, "")
        if value and isinstance(value, str) and "@" in value:
            email = sanitize_input(value).lower()
            logger.info(f"Provider email found in field '{field}': {email}")
            return email
    
    # Try pattern matching on all field names containing "email" + "provider"
    for key, value in data.items():
        key_lower = key.lower()
        if "email" in key_lower and ("provider" in key_lower or "referr" in key_lower):
            if value and isinstance(value, str) and "@" in value:
                email = sanitize_input(value).lower()
                logger.info(f"Provider email found via pattern match in '{key}': {email}")
                return email
    
    # Try pattern matching for any field with "email" in name that's not patient/contact email
    for key, value in data.items():
        key_lower = key.lower()
        # Skip patient email fields
        if "email" in key_lower and not any(skip in key_lower for skip in ["patient", "contact", "q39", "q38", "q40"]):
            if value and isinstance(value, str) and "@" in value:
                email = sanitize_input(value).lower()
                logger.info(f"Provider email found in fallback field '{key}': {email}")
                return email
    
    # Last resort: Check for any field with an email value that looks like a provider
    # (not the same as patient email field)
    patient_email = data.get("q39_email", "").lower() if data.get("q39_email") else ""
    for key, value in data.items():
        if isinstance(value, str) and "@" in value:
            email = sanitize_input(value).lower()
            # Skip if it's the patient email
            if email != patient_email and email:
                logger.info(f"Provider email found in last-resort scan '{key}': {email}")
                return email
    
    # Log failure with available fields for debugging
    logger.warning(f"Provider email NOT FOUND in Jotform data. Available fields: {list(data.keys())}")
    # Log any fields that contain 'email' for debugging
    email_fields_found = [k for k in data.keys() if 'email' in k.lower()]
    if email_fields_found:
        logger.warning(f"Fields containing 'email': {email_fields_found}")
        for f in email_fields_found:
            logger.warning(f"  Field: {f} (has_value={'yes' if data.get(f) else 'no'})")
    
    return ""


def extract_provider_specialty(data: Dict[str, Any]) -> str:
    """
    Extract provider specialty from Jotform if available.
    
    CRITICAL: This function must find the provider specialty for referrals.
    Logs all attempts for debugging.
    
    Returns the specialty value or empty string if not found.
    """
    # List of possible field names for provider specialty (ordered by likelihood)
    specialty_fields = [
        # Jotform question ID patterns (qXX_)
        "q48_providerSpecialty",
        "q47_providerSpecialty",
        "q46_providerSpecialty",
        "q49_providerSpecialty",
        "q48_providersSpecialty",
        "q47_providersSpecialty",
        "q46_providersSpecialty",
        # Camel case patterns
        "providerSpecialty",
        "providersSpecialty",
        "referringProviderSpecialty",
        # Snake case patterns
        "provider_specialty",
        "providers_specialty",
        "referring_provider_specialty",
        # Simple patterns
        "specialty",
        "Specialty",
    ]
    
    # Try direct field name matches first
    for field in specialty_fields:
        value = data.get(field, "")
        if value and isinstance(value, str) and value.strip():
            specialty = sanitize_input(value).strip()
            logger.info(f"Provider specialty found in field '{field}': {specialty}")
            return specialty
    
    # Try pattern matching on all field names containing "specialty"
    for key, value in data.items():
        key_lower = key.lower()
        if "specialty" in key_lower or "speciality" in key_lower:  # Handle common misspelling
            if value and isinstance(value, str) and value.strip():
                specialty = sanitize_input(value).strip()
                logger.info(f"Provider specialty found via pattern match in '{key}': {specialty}")
                return specialty
    
    # Try pattern matching for provider-related fields that might contain specialty
    for key, value in data.items():
        key_lower = key.lower()
        if "provider" in key_lower and "type" in key_lower:
            if value and isinstance(value, str) and value.strip():
                specialty = sanitize_input(value).strip()
                logger.info(f"Provider specialty found in provider type field '{key}': {specialty}")
                return specialty
    
    # Log failure with available fields for debugging
    logger.warning(f"Provider specialty NOT FOUND in Jotform data.")
    # Log any fields that contain 'special' or 'type' for debugging
    specialty_fields_found = [k for k in data.keys() if 'special' in k.lower() or ('provider' in k.lower() and 'type' in k.lower())]
    if specialty_fields_found:
        logger.warning(f"Potential specialty fields found: {specialty_fields_found}")
        for f in specialty_fields_found:
            logger.warning(f"  {f} = {data.get(f)}")
    
    return ""


def extract_jotform_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and map all fields from Jotform payload."""
    # Use robust name extraction
    first_name, last_name = extract_patient_name(data)
    
    # Log if name couldn't be extracted for debugging
    if not first_name and not last_name:
        logger.warning(f"Could not extract patient name from Jotform. Available fields: {list(data.keys())}")
    
    email = sanitize_input(data.get("q39_email", ""))
    
    phone_data = data.get("q40_phoneNumber", {})
    if isinstance(phone_data, dict):
        phone = normalize_phone(sanitize_input(phone_data.get("full", "")))
    else:
        phone = normalize_phone(sanitize_input(phone_data))
    
    conditions_raw = data.get("q12_whatCondition", [])
    if isinstance(conditions_raw, str):
        conditions_raw = [conditions_raw]
    conditions = map_condition(conditions_raw)
    
    duration = map_duration(sanitize_input(data.get("q21_howLong", "")))
    
    treatments_raw = data.get("q22_whatTreatments", [])
    if isinstance(treatments_raw, str):
        treatments_raw = [treatments_raw]
    treatments = map_treatments(treatments_raw)
    
    has_insurance = parse_yes_no(sanitize_input(data.get("q24_doYou", "")))
    insurance_provider = sanitize_input(data.get("q25_insuranceProvider", ""))
    zip_code = normalize_zip(sanitize_input(data.get("q26_whatIs", "")))
    urgency = map_urgency(sanitize_input(data.get("q27_whenWould", "")))
    referred_by_provider = parse_yes_no(sanitize_input(data.get("q43_wereYou", "")))
    
    # Extract provider details with robust field detection
    referring_provider_email = extract_provider_email(data)
    referring_provider_specialty = extract_provider_specialty(data)
    
    # Log provider data for debugging
    if referred_by_provider:
        logger.info(f"Referral detected - Provider email: {referring_provider_email or 'not found'}, Specialty: {referring_provider_specialty or 'not found'}")
    
    return {
        "first_name": first_name,  # Never default to "Unknown" - let frontend handle display
        "last_name": last_name,
        "email": email,  # May be empty
        "phone": phone,  # May be empty
        "condition": conditions,
        "symptom_duration": duration,
        "prior_treatments": treatments,
        "has_insurance": has_insurance,
        "insurance_provider": insurance_provider if has_insurance else None,
        "zip_code": zip_code,
        "urgency": urgency,
        "referred_by_provider": referred_by_provider,
        "referring_provider_name": sanitize_input(data.get("q44_referringProviders", "")),
        "referring_clinic": sanitize_input(data.get("q45_clinicpracticeName", "")),
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
    description="Receives leads from Jotform TMS Therapy Patient Intake Assessment form.",
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
        # CRITICAL DEBUGGING: Log ALL incoming Jotform fields
        # This helps identify the actual field names being sent
        # =====================================================================
        logger.info("=" * 60)
        logger.info("JOTFORM WEBHOOK - FULL PAYLOAD DUMP FOR DEBUGGING")
        logger.info("=" * 60)
        logger.info(f"Total fields received: {len(data)}")
        
        # Log field names (NOT values) for debugging — values may contain PHI
        # Only log provider-related field VALUES (provider info is not patient PHI)
        PATIENT_PHI_FIELDS = {'q38', 'q39', 'q40', 'name', 'email', 'phone', 'contact'}
        provider_related_fields = []
        for key, value in sorted(data.items()):
            key_lower = key.lower()
            # Log provider-related fields in detail (provider info is NOT patient PHI)
            if any(term in key_lower for term in ['provider', 'referr', 'specialty', 'clinic', 'practice']):
                provider_related_fields.append((key, value))
                logger.info(f"[PROVIDER FIELD] {key} = {repr(value)}")
            else:
                # Log field NAMES only (not values) to avoid PHI in logs
                logger.debug(f"[FIELD] {key} (value_present={'yes' if value else 'no'})")
        
        if provider_related_fields:
            logger.info(f"Found {len(provider_related_fields)} provider-related fields")
        else:
            logger.warning("NO provider-related fields found in Jotform payload!")
            logger.info(f"All available field names: {sorted(data.keys())}")
        logger.info("=" * 60)
        
        # =====================================================================
        # IDEMPOTENCY CHECK: Detect duplicate Jotform retries.
        # Jotform retries the webhook with exponential back-off if the first
        # request times out or returns non-2xx.
        #
        # Two-layer defence:
        #   1. submissionID check (PRIMARY) — Jotform posts a globally-unique
        #      submissionID per submission as a top-level form field (separate
        #      from rawRequest JSON).  Matching on this is exact and handles
        #      retries regardless of IP (NAT rotation, proxy changes, etc.).
        #   2. IP-hash fallback — for edge-cases where submissionID is absent,
        #      keep the original IP-based window check.
        # =====================================================================
        from datetime import timedelta

        # Extract Jotform's own unique submission identifier.
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
                logger.warning(
                    f"Jotform duplicate detected via submissionID={submission_id} — "
                    f"lead {dup.lead_number} already created. Skipping."
                )
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
            # Fallback: IP-based check (less reliable — multiple patients can share
            # a clinic Wi-Fi IP — but retained for payloads missing submissionID).
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
                    logger.warning(
                        f"Jotform duplicate detected via IP hash — lead {duplicate.lead_number} "
                        f"was created within {IDEMPOTENCY_WINDOW_SECONDS}s from the same IP. Skipping."
                    )
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
        # V2: Use canonical mapping layer for consistent field handling
        # =====================================================================
        lead_input: LeadInput = map_jotform_submission_to_lead_input(data)
        
        # Log the extracted conditions for debugging
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
        
        # Extract score values
        score = score_breakdown.lead_score
        priority_str = score_breakdown.priority
        in_service_area = score_breakdown.in_service_area
        
        # Map priority string to enum
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
            # Store raw referral data for audit trail
            referring_provider_raw = {
                "provider_name": lead_input.referring_provider_name,
                "clinic_name": lead_input.referring_clinic,
                "provider_email": lead_input.referring_provider_email,
                "source": "jotform",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            
            # Build referral notes
            parts = []
            if lead_input.referring_provider_name and lead_input.referring_provider_name not in ["N/A", "n/a", "", "NA"]:
                parts.append(f"Provider: {lead_input.referring_provider_name}")
            if lead_input.referring_clinic and lead_input.referring_clinic not in ["N/A", "n/a", "", "NA"]:
                parts.append(f"Clinic: {lead_input.referring_clinic}")
            if parts:
                referral_notes = "[Jotform Referral] " + ", ".join(parts)
            
            # Find or create the referring provider
            referring_provider = find_or_create_provider(
                db=db,
                provider_name=lead_input.referring_provider_name,
                practice_name=lead_input.referring_clinic,
                provider_email=lead_input.referring_provider_email,
                provider_specialty=mapped_data.get("referring_provider_specialty", ""),
            )
            
            if referring_provider:
                logger.info(f"Lead linked to provider: {referring_provider.name} ({referring_provider.id})")
        
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
        
        # Map primary condition to enum for backward compatibility
        condition_enum_map = {
            "depression": ConditionType.DEPRESSION,
            "anxiety": ConditionType.ANXIETY,
            "ocd": ConditionType.OCD,
            "ptsd": ConditionType.PTSD,
            "other": ConditionType.OTHER,
        }
        primary_condition = condition_enum_map.get(
            lead_input.primary_condition,
            ConditionType.OTHER
        )
        
        # Map normalized treatments to enum list
        treatment_enum_map = {
            "antidepressants": TreatmentType.ANTIDEPRESSANTS,
            "therapy_cbt": TreatmentType.THERAPY_CBT,
            "both": TreatmentType.BOTH,
            "none": TreatmentType.NONE,
            "other": TreatmentType.OTHER,
        }
        prior_treatments = [
            treatment_enum_map.get(t, TreatmentType.OTHER)
            for t in lead_input.prior_treatments
        ] or [TreatmentType.NONE]
        
        # Map preferred contact method - NO defaults, keep actual value
        contact_method_map = {
            "phone_call": "phone",
            "text": "sms",
            "email": "email",
            "any": "any",  # Keep "any" as is, don't default to phone
        }
        preferred_contact = contact_method_map.get(
            lead_input.preferred_contact_method,
            lead_input.preferred_contact_method  # Keep original value if not in map
        ) if lead_input.preferred_contact_method else None
        
        # Log preferred contact for debugging
        logger.info(f"Jotform preferred_contact_method: raw='{lead_input.preferred_contact_method}', mapped='{preferred_contact}'")
        
        # =====================================================================
        lead = Lead(
            lead_number=lead_number,
            first_name_encrypted=first_name_encrypted,
            last_name_encrypted=last_name_encrypted,
            email_encrypted=email_encrypted,
            phone_encrypted=phone_encrypted,
            
            # Primary condition (backward compatibility)
            condition=primary_condition,
            
            # V2: Multi-condition support - store conditions array
            conditions=lead_input.conditions if lead_input.conditions else [],
            other_condition_text=lead_input.other_condition_text,
            
            # V2: Preferred contact method
            preferred_contact_method=preferred_contact,
            
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
            
            # V2: Enhanced scoring with breakdown
            score=score,
            priority=priority,
            
            # V2: Store individual score breakdown components for transparency
            condition_score=score_breakdown.condition_score,
            therapy_interest_score=score_breakdown.therapy_interest_score,
            severity_score=score_breakdown.severity_score,
            insurance_score=score_breakdown.insurance_score,
            duration_score=score_breakdown.duration_score,
            treatment_score=score_breakdown.treatment_score,
            location_score=score_breakdown.location_score,
            urgency_score=score_breakdown.urgency_score,
            
            # V2: TMS therapy interest
            tms_therapy_interest=lead_input.tms_therapy_interest,
            
            # V2: Severity assessment values - use correct model field names
            phq2_interest=lead_input.phq2_interest,
            phq2_mood=lead_input.phq2_mood,
            depression_severity_score=score_breakdown.depression_severity_score,
            depression_severity_level=score_breakdown.depression_severity_level,
            gad2_nervous=lead_input.gad2_nervous,
            gad2_worry=lead_input.gad2_worry,
            anxiety_severity_score=score_breakdown.anxiety_severity_score,
            anxiety_severity_level=score_breakdown.anxiety_severity_level,
            ocd_time_occupied=lead_input.ocd_time_occupied,
            ocd_severity_level=score_breakdown.ocd_severity_level,
            ptsd_intrusion=lead_input.ptsd_intrusion,
            ptsd_severity_level=score_breakdown.ptsd_severity_level,
            
            # Status
            status=LeadStatus.NEW,
            contact_outcome=ContactOutcome.NEW,
            source=lead_source,
            # Combine referral notes with Jotform submissionID tag so the
            # idempotency check above can find this lead on webhook retries.
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
        
        # IDEMPOTENT FIX: Recalculate provider total_referrals from actual lead COUNT.
        # This prevents double-counting from Jotform webhook retries.
        # COUNT is always accurate regardless of how many times this code runs.
        if referring_provider:
            actual_count = db.query(func.count(Lead.id)).filter(
                Lead.referring_provider_id == referring_provider.id,
                Lead.deleted_at.is_(None),
            ).scalar() or 0
            referring_provider.total_referrals = actual_count
            referring_provider.last_referral_at = now
            db.commit()
            logger.info(f"Provider {referring_provider.name} total_referrals set to {actual_count} (COUNT-based)")
        
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
        
        # Send unified confirmation email via dispatcher (Celery async with sync fallback)
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
                logger.info(f"Sent confirmation email for Jotform lead {lead.lead_number}")
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


# =============================================================================
# Google Ads Lead Form Webhook
# =============================================================================

# Priority mapping based on the custom "Your Text/Wording" question answers
GOOGLE_ADS_URGENCY_PRIORITY_MAP = {
    "seeking to start treatment immediately": PriorityType.HOT,
    "looking to start within the next 30 days": PriorityType.MEDIUM,
    "just gathering information for now": PriorityType.LOW,
    "just gathering information": PriorityType.LOW,
}

# Urgency mapping for the lead model
GOOGLE_ADS_URGENCY_MAP = {
    "seeking to start treatment immediately": UrgencyType.ASAP,
    "looking to start within the next 30 days": UrgencyType.WITHIN_30_DAYS,
    "just gathering information for now": UrgencyType.EXPLORING,
    "just gathering information": UrgencyType.EXPLORING,
}

# Score values matching the urgency/priority
GOOGLE_ADS_PRIORITY_SCORES = {
    PriorityType.HOT: 150,
    PriorityType.MEDIUM: 90,
    PriorityType.LOW: 40,
}


def _parse_google_ads_user_columns(user_column_data: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Parse the Google Ads user_column_data array into a flat dict.

    Google Ads sends form field data as:
        [
            {"column_id": "FULL_NAME", "column_value": "Jane Doe"},
            {"column_id": "EMAIL", "column_value": "jane@example.com"},
            {"column_id": "PHONE_NUMBER", "column_value": "+14805551234"},
            {"column_id": "Your Text/Wording", "column_value": "Seeking to start treatment immediately"},
        ]

    Returns:
        Dict mapping column_id -> column_value
    """
    result: Dict[str, str] = {}
    if not user_column_data:
        return result
    for item in user_column_data:
        col_id = str(item.get("column_id", "")).strip()
        col_val = str(item.get("column_value", "")).strip()
        if col_id:
            result[col_id] = col_val
    return result


def _split_full_name(full_name: str) -> tuple:
    """Split a full name into (first_name, last_name)."""
    if not full_name:
        return ("", "")
    parts = full_name.strip().split(" ", 1)
    first = parts[0]
    last = parts[1] if len(parts) > 1 else ""
    return (first, last)


def _determine_priority_from_answer(answer: str) -> tuple:
    """
    Determine priority, urgency, and score from the custom question answer.

    Returns:
        (priority: PriorityType, urgency: UrgencyType, score: int)
    """
    answer_lower = answer.lower().strip() if answer else ""

    for key, priority in GOOGLE_ADS_URGENCY_PRIORITY_MAP.items():
        if key in answer_lower:
            urgency = GOOGLE_ADS_URGENCY_MAP.get(key, UrgencyType.EXPLORING)
            score = GOOGLE_ADS_PRIORITY_SCORES.get(priority, 40)
            return (priority, urgency, score)

    # Default: Low priority if unrecognised answer
    return (PriorityType.LOW, UrgencyType.EXPLORING, 40)


@router.post(
    "/google-ads",
    status_code=status.HTTP_200_OK,
    summary="Google Ads Lead Form Webhook",
    description=(
        "Receives leads from Google Ads Lead Form Extensions. "
        "Verifies the webhook key, parses the payload, maps to our lead format, "
        "and saves to the database."
    ),
)
async def google_ads_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Receive and process leads from Google Ads Lead Form Extensions.

    Google Ads sends a JSON POST with:
        - lead_id: Unique lead identifier from Google
        - google_key: Webhook verification key
        - campaign_id: Google Ads campaign ID
        - user_column_data: Array of {column_id, column_value} with form fields

    Field mapping:
        FULL_NAME       -> patient first + last name
        EMAIL           -> email
        PHONE_NUMBER    -> phone
        Custom question -> urgency / priority

    Priority logic:
        "Seeking to start treatment immediately"    -> Hot
        "Looking to start within the next 30 days"  -> Medium
        "Just gathering information for now"         -> Low
    """
    from ..core.config import settings as app_settings

    try:
        # =====================================================================
        # 1. Parse the JSON body
        # =====================================================================
        try:
            body = await request.json()
        except Exception:
            logger.warning("Google Ads webhook: invalid JSON body")
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

        logger.info(f"Google Ads webhook received: lead_id={body.get('lead_id')}, campaign_id={body.get('campaign_id')}")

        # =====================================================================
        # 2. Verify webhook key
        # =====================================================================
        google_key = body.get("google_key", "")
        expected_key = app_settings.google_ads_webhook_key

        if not expected_key:
            logger.error("GOOGLE_ADS_WEBHOOK_KEY is not configured in .env")
            raise HTTPException(status_code=500, detail="Webhook key not configured")

        if google_key != expected_key:
            logger.warning(f"Google Ads webhook: invalid key (received key length={len(google_key)})")
            raise HTTPException(status_code=403, detail="Invalid webhook key")

        # =====================================================================
        # 2b. IDEMPOTENCY CHECK: Google Ads may retry if response is slow.
        #     Use the Google-provided lead_id (stored in notes) to deduplicate.
        # =====================================================================
        google_lead_id = body.get("lead_id", "")
        if google_lead_id:
            from datetime import timedelta
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=IDEMPOTENCY_WINDOW_SECONDS)
            dup = db.query(Lead.id, Lead.lead_number).filter(
                Lead.source == LeadSource.google_ads,
                Lead.notes.contains(f"Lead ID: {google_lead_id}"),
                Lead.created_at >= cutoff,
            ).first()
            if dup:
                logger.info(
                    f"[Google Ads] Duplicate submission detected (lead_id={google_lead_id}), "
                    f"skipping. Original lead: {dup.lead_number}. "
                    f"This is expected for test data (same lead_id) or webhook retries. "
                    f"Real production leads have unique lead_ids and will each create a new lead."
                )
                return JSONResponse(
                    status_code=200,
                    content={
                        "success": True,
                        "message": "Duplicate submission detected, original lead preserved",
                        "lead_number": dup.lead_number,
                        "duplicate": True,
                    },
                )

        # =====================================================================
        # 3. Extract fields from user_column_data
        # =====================================================================
        lead_id = body.get("lead_id", "")
        campaign_id = body.get("campaign_id", "")
        user_column_data = body.get("user_column_data", [])

        columns = _parse_google_ads_user_columns(user_column_data)

        full_name = columns.get("FULL_NAME", "")
        email = columns.get("EMAIL", "")
        phone = columns.get("PHONE_NUMBER", "")
        # The custom question answer — try common column_id patterns
        custom_answer = (
            columns.get("Your Text/Wording", "")
            or columns.get("CUSTOM_QUESTION_1", "")
            or columns.get("your_text_wording", "")
            or columns.get("urgency", "")
        )

        first_name, last_name = _split_full_name(full_name)

        if not first_name and not last_name:
            # Try separate first/last name columns
            first_name = columns.get("FIRST_NAME", "")
            last_name = columns.get("LAST_NAME", "")

        logger.info(
            f"Google Ads lead parsed: name_present={'yes' if first_name else 'no'}, "
            f"email_present={'yes' if email else 'no'}, "
            f"phone_present={'yes' if phone else 'no'}, "
            f"custom_answer='{custom_answer}'"
        )

        # GAP 7 FIX: Warn when ALL PHI fields are empty — typical of "Send test data"
        # from the Google Ads console, which fires with no real lead information.
        if not first_name and not last_name and not email and not phone:
            logger.warning(
                f"[Google Ads] Lead {lead_id} has NO PHI (empty name, email, phone). "
                f"This is typical of 'Send test data' from the Google Ads console. "
                f"Lead will be created with empty fields — review in dashboard and delete if test data."
            )

        # =====================================================================
        # 4. Determine priority, urgency, score
        # =====================================================================
        priority, urgency, score = _determine_priority_from_answer(custom_answer)

        # =====================================================================
        # 5. Encrypt PHI
        # =====================================================================
        first_name_encrypted = EncryptionService.encrypt_field(first_name or "")
        last_name_encrypted = EncryptionService.encrypt_field(last_name or "")
        email_encrypted = EncryptionService.encrypt_field(email or "")
        phone_encrypted = EncryptionService.encrypt_field(normalize_phone(phone or ""))

        # =====================================================================
        # 6. Generate lead number & metadata
        # =====================================================================
        lead_number = generate_unique_lead_number(db)
        client_ip = get_client_ip(request)
        user_agent = request.headers.get("User-Agent", "")
        now = datetime.now(timezone.utc)

        # =====================================================================
        # 7. Create the Lead record (same model as widget/jotform)
        # =====================================================================
        lead = Lead(
            lead_number=lead_number,
            first_name_encrypted=first_name_encrypted,
            last_name_encrypted=last_name_encrypted,
            email_encrypted=email_encrypted,
            phone_encrypted=phone_encrypted,

            # Condition defaults — Google Ads form does not collect clinical detail
            condition=ConditionType.OTHER,
            conditions=[],
            other_condition_text=custom_answer if custom_answer else None,

            # Clinical fields — defaults (not collected from Google Ads)
            symptom_duration=DurationType.LESS_THAN_6_MONTHS,
            prior_treatments=[TreatmentType.NONE],
            has_insurance=False,
            zip_code="00000",
            in_service_area=False,

            # Urgency & Consent
            urgency=urgency,
            hipaa_consent=True,
            hipaa_consent_timestamp=now,
            privacy_consent_timestamp=now,

            # Scoring
            score=score,
            priority=priority,

            # Status
            status=LeadStatus.NEW,
            contact_outcome=ContactOutcome.NEW,
            source=LeadSource.google_ads,

            # Notes with Google Ads metadata
            notes=f"[Google Ads] Lead ID: {lead_id}, Campaign: {campaign_id}, Answer: {custom_answer}",

            # Tracking
            ip_address_hash=EncryptionService.hash_ip(client_ip),
            user_agent=user_agent,
            utm_source="google_ads",
            utm_medium="lead_form",
            utm_campaign=f"gads_{campaign_id}" if campaign_id else "gads",
        )

        db.add(lead)
        db.commit()
        db.refresh(lead)

        logger.info(
            f"Google Ads lead created: {lead.lead_number}, "
            f"priority={priority.value}, score={score}, "
            f"urgency={urgency.value}"
        )

        # Invalidate dashboard cache
        try:
            cache = get_cache()
            cache.invalidate_on_lead_change()
        except Exception:
            pass

        # Send unified confirmation email (Google Ads has NO conditions data) via dispatcher
        try:
            from ..services.sync_notifications import dispatch_lead_receipt_notifications
            if email:
                dispatch_lead_receipt_notifications(
                    lead_id=str(lead.id),
                    email=email,
                    phone=normalize_phone(phone or ""),
                    first_name=first_name or "",
                    lead_number=lead.lead_number,
                    conditions=[],
                    other_condition_text="",
                )
                logger.info(f"Sent confirmation email for Google Ads lead {lead.lead_number}")
        except Exception as e:
            logger.warning(f"Failed to send confirmation email for Google Ads lead {lead.lead_number}: {e}")

        # Audit log
        try:
            audit_service = AuditService(db)
            audit_service.log_create(
                table_name="leads",
                record_id=lead.id,
                ip_address=client_ip,
                endpoint="/api/webhooks/google-ads",
                request_method="POST",
                user_agent=user_agent,
                new_values={
                    "source": "google_ads",
                    "priority": priority.value,
                    "google_lead_id": lead_id,
                    "campaign_id": campaign_id,
                },
            )
        except Exception:
            pass

        # =====================================================================
        # 8. Return success so Google Ads confirms delivery
        # =====================================================================
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Lead received from Google Ads",
                "lead_number": lead.lead_number,
                "priority": priority.value,
                "score": score,
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Google Ads webhook error: {type(e).__name__}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Error processing Google Ads lead")


@router.get("/google-ads/test", summary="Test Google Ads Webhook")
async def test_google_ads_webhook():
    """Test endpoint to verify the Google Ads webhook is accessible."""
    return {
        "status": "ok",
        "message": "Google Ads webhook is active",
        "endpoint": "/api/webhooks/google-ads",
        "method": "POST",
        "required_fields": [
            "google_key",
            "lead_id",
            "user_column_data (array with FULL_NAME, EMAIL, PHONE_NUMBER, custom question)",
        ],
    }
