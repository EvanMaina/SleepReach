"""
Canonical Intake Mapping Layer.

This module provides a single source of truth for mapping intake data
from multiple sources (Jotform, Widget) to a standardized LeadInput format.

Both Jotform and Widget submissions MUST flow through this mapping layer
to ensure consistent field handling, validation, and normalization.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from datetime import date

logger = logging.getLogger(__name__)


# =============================================================================
# Canonical LeadInput Dataclass
# =============================================================================

@dataclass
class LeadInput:
    """
    Canonical lead input data structure.
    
    This is the single source of truth for all lead data,
    regardless of whether it comes from Jotform or Widget.
    """
    
    # Contact Information
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""
    date_of_birth: Optional[date] = None
    
    # Multi-condition support (normalized lowercase keys)
    # Valid values: depression, anxiety, ocd, ptsd, other
    conditions: List[str] = field(default_factory=list)
    primary_condition: str = ""  # Derived from conditions for backward compatibility
    other_condition_text: str = ""  # Free text when 'other' is selected
    
    # TMS Therapy Interest
    tms_therapy_interest: str = ""  # daily_tms, accelerated_tms, not_sure
    
    # Preferred Contact Method
    preferred_contact_method: str = ""  # phone_call, text, email, any
    
    # Depression PHQ-2 Assessment (0-3 each)
    phq2_interest: Optional[int] = None
    phq2_mood: Optional[int] = None
    
    # Anxiety GAD-2 Assessment (0-3 each)
    gad2_nervous: Optional[int] = None
    gad2_worry: Optional[int] = None
    
    # OCD Assessment (1-4)
    ocd_time_occupied: Optional[int] = None
    
    # PTSD Assessment (0-4)
    ptsd_intrusion: Optional[int] = None
    
    # Insurance Information
    has_insurance: bool = False
    insurance_provider: str = ""
    other_insurance_provider: str = ""  # When provider = 'Other'
    
    # Location
    zip_code: str = ""
    
    # Symptom Duration
    symptom_duration: str = ""  # less_than_6_months, 6_to_12_months, more_than_12_months
    
    # Prior Treatments
    prior_treatments: List[str] = field(default_factory=list)  # antidepressants, therapy_cbt, both, none, other
    
    # Urgency
    urgency: str = ""  # asap, within_30_days, exploring
    
    # Consent
    hipaa_consent: bool = False
    sms_consent: bool = False
    
    # Referral Information
    referred_by_provider: bool = False
    referring_provider_name: str = ""
    referring_clinic: str = ""
    referring_provider_email: str = ""
    referring_provider_specialty: str = ""  # Provider's specialty (Psychiatrist, Neurologist, etc.)
    
    # UTM Tracking
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_term: Optional[str] = None
    utm_content: Optional[str] = None
    
    # Metadata
    referrer_url: Optional[str] = None
    
    def __post_init__(self):
        """Derive primary_condition from conditions array."""
        if self.conditions and not self.primary_condition:
            # Set primary_condition to first non-other condition, or first condition
            for cond in self.conditions:
                if cond != 'other':
                    self.primary_condition = cond
                    break
            if not self.primary_condition and self.conditions:
                self.primary_condition = self.conditions[0]


# =============================================================================
# Normalization Helpers
# =============================================================================

def sanitize_input(value: Any) -> str:
    """Sanitize input to prevent injection attacks."""
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return str(value)
    return str(value).strip()


def normalize_phone(phone: str) -> str:
    """Normalize phone number to digits only with optional +."""
    if not phone:
        return ""
    has_plus = phone.strip().startswith('+')
    digits = re.sub(r"[^\d]", "", phone)
    if has_plus and digits:
        return f"+{digits}"
    return digits if digits else ""


def normalize_zip(zip_code: str) -> str:
    """Normalize ZIP code to 5 digits."""
    if not zip_code:
        return "00000"
    digits = re.sub(r"[^\d]", "", zip_code)
    return digits[:5] if len(digits) >= 5 else digits.zfill(5)


def parse_yes_no(value: Any) -> bool:
    """Parse yes/no string to boolean."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    return str(value).lower().strip() in ["yes", "true", "1", "y"]


def safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    """Safely convert value to int."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


# =============================================================================
# Condition Mapping
# =============================================================================

CONDITION_KEYWORDS = {
    "depression": ["depression", "depressed", "depressive"],
    "anxiety": ["anxiety", "anxious", "gad"],
    "ocd": ["ocd", "obsessive", "compulsive"],
    "ptsd": ["ptsd", "trauma", "post-traumatic", "post traumatic"],
    "other": ["other"],
}


def normalize_condition(condition_str: str) -> str:
    """
    Normalize a condition string to canonical key.
    
    Returns: depression | anxiety | ocd | ptsd | other
    """
    if not condition_str:
        return "other"
    
    condition_lower = condition_str.lower().strip()
    
    for key, keywords in CONDITION_KEYWORDS.items():
        for keyword in keywords:
            if keyword in condition_lower:
                return key
    
    return "other"


def normalize_conditions_list(conditions_raw: Any) -> List[str]:
    """
    Normalize conditions input to list of canonical keys.
    
    Handles:
    - Single string: "Depression"
    - Comma-separated: "Depression, Anxiety"
    - Array: ["Depression", "OCD"]
    - Checkbox format from Jotform
    """
    if not conditions_raw:
        return []
    
    # Convert to list
    if isinstance(conditions_raw, str):
        # Could be comma-separated or single value
        raw_list = [c.strip() for c in conditions_raw.split(",") if c.strip()]
    elif isinstance(conditions_raw, list):
        raw_list = [str(c).strip() for c in conditions_raw if c]
    else:
        raw_list = [str(conditions_raw).strip()]
    
    # Normalize each condition
    normalized = []
    for raw in raw_list:
        normalized_key = normalize_condition(raw)
        if normalized_key and normalized_key not in normalized:
            normalized.append(normalized_key)
    
    return normalized


# =============================================================================
# Duration Mapping
# =============================================================================

DURATION_MAP = {
    "less than 6 months": "less_than_6_months",
    "less_than_6_months": "less_than_6_months",
    "< 6 months": "less_than_6_months",
    "6 to 12 months": "6_to_12_months",
    "6-12 months": "6_to_12_months",
    "six_to_twelve_months": "6_to_12_months",
    "more than 12 months": "more_than_12_months",
    "> 12 months": "more_than_12_months",
    "more_than_12_months": "more_than_12_months",
}


def normalize_duration(duration: str) -> str:
    """Normalize symptom duration to canonical key."""
    if not duration:
        return "less_than_6_months"
    
    duration_lower = duration.lower().strip()
    
    for key, value in DURATION_MAP.items():
        if key in duration_lower or duration_lower == value:
            return value
    
    # Default fallback
    return "less_than_6_months"


# =============================================================================
# Treatment Mapping
# =============================================================================

TREATMENT_KEYWORDS = {
    "antidepressants": [
        "antidepressant", "zoloft", "lexapro", "prozac", "anti-anxiety",
        "xanax", "ativan", "buspar", "medication", "ssri", "snri"
    ],
    "therapy_cbt": [
        "therapy", "cbt", "cognitive", "counseling", "psychotherapy",
        "behavioral", "talk therapy"
    ],
    "both": ["both"],
    "none": ["none", "no treatment", "nothing"],
}


def normalize_treatments(treatments_raw: Any) -> List[str]:
    """Normalize prior treatments to list of canonical keys."""
    if not treatments_raw:
        return []
    
    # Convert to list
    if isinstance(treatments_raw, str):
        raw_list = [c.strip() for c in treatments_raw.split(",") if c.strip()]
    elif isinstance(treatments_raw, list):
        raw_list = [str(c).strip() for c in treatments_raw if c]
    else:
        raw_list = [str(treatments_raw).strip()]
    
    normalized = set()
    for raw in raw_list:
        raw_lower = raw.lower()
        
        # Check for explicit "both" first
        if "both" in raw_lower:
            normalized.add("antidepressants")
            normalized.add("therapy_cbt")
            continue
        
        matched = False
        for key, keywords in TREATMENT_KEYWORDS.items():
            if key == "both":
                continue
            for keyword in keywords:
                if keyword in raw_lower:
                    normalized.add(key)
                    matched = True
                    break
        
        if not matched and raw_lower not in ["none", "no treatment", "nothing"]:
            normalized.add("other")
    
    return list(normalized) if normalized else []


# =============================================================================
# Urgency Mapping
# =============================================================================

URGENCY_MAP = {
    "as soon as possible": "asap",
    "asap": "asap",
    "immediately": "asap",
    "urgent": "asap",
    "within a month": "within_30_days",
    "within 30 days": "within_30_days",
    "within_30_days": "within_30_days",
    "within a few months": "exploring",
    "exploring": "exploring",
    "just exploring options": "exploring",
    "not sure": "exploring",
}


def normalize_urgency(urgency: str) -> str:
    """Normalize urgency to canonical key."""
    if not urgency:
        return "exploring"
    
    urgency_lower = urgency.lower().strip()
    
    for key, value in URGENCY_MAP.items():
        if key in urgency_lower or urgency_lower == value:
            return value
    
    return "exploring"


# =============================================================================
# TMS Therapy Interest Mapping
# =============================================================================

TMS_INTEREST_MAP = {
    "daily tms": "daily_tms",
    "daily_tms": "daily_tms",
    "standard tms": "daily_tms",
    "traditional tms": "daily_tms",
    "accelerated tms": "accelerated_tms",
    "accelerated_tms": "accelerated_tms",
    "not sure": "not_sure",
    "not_sure": "not_sure",
    "unsure": "not_sure",
}


def normalize_tms_interest(interest: str) -> str:
    """Normalize TMS therapy interest to canonical key."""
    if not interest:
        return "not_sure"
    
    interest_lower = interest.lower().strip()
    
    for key, value in TMS_INTEREST_MAP.items():
        if key in interest_lower or interest_lower == value:
            return value
    
    return "not_sure"


# =============================================================================
# Preferred Contact Method Mapping
# =============================================================================

CONTACT_METHOD_MAP = {
    "phone call": "phone_call",
    "phone_call": "phone_call",
    "phone": "phone_call",
    "call": "phone_call",
    "text": "text",
    "sms": "text",
    "text message": "text",
    "email": "email",
    "e-mail": "email",
    "any": "any",
    "no preference": "any",
}


def normalize_contact_method(method: str) -> str:
    """Normalize preferred contact method to canonical key."""
    if not method:
        return "any"
    
    method_lower = method.lower().strip()
    
    for key, value in CONTACT_METHOD_MAP.items():
        if key in method_lower or method_lower == value:
            return value
    
    return "any"


# =============================================================================
# Insurance Provider Mapping
# =============================================================================

IN_NETWORK_PROVIDERS = [
    "aetna",
    "blue cross blue shield",
    "bcbs",
    "cigna",
    "united healthcare",
    "unitedhealthcare",
    "tricare",
    "medicare",
    "humana",
    "kaiser",
    "kaiser permanente",
]


def is_in_network_provider(provider: str) -> bool:
    """Check if insurance provider is in-network."""
    if not provider:
        return False
    
    provider_lower = provider.lower().strip()
    
    for in_network in IN_NETWORK_PROVIDERS:
        if in_network in provider_lower or provider_lower in in_network:
            return True
    
    return False


def normalize_insurance_provider(provider: str) -> Tuple[str, bool]:
    """
    Normalize insurance provider.
    
    Returns: (normalized_provider, is_other)
    """
    if not provider:
        return "", False
    
    provider_clean = provider.strip()
    
    # Check if it's explicitly "Other"
    if provider_clean.lower() in ["other", "other provider", "different provider"]:
        return "Other", True
    
    return provider_clean, False


# =============================================================================
# Jotform Field Extraction Helpers
# =============================================================================

def extract_patient_name_from_jotform(data: Dict[str, Any]) -> Tuple[str, str]:
    """
    Extract patient name from Jotform submission.
    
    Handles multiple field patterns for contact/name info.
    Returns (first_name, last_name).
    """
    first_name = ""
    last_name = ""
    
    # Try multiple field patterns
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
    
    # Try separate first/last name fields
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


# =============================================================================
# Main Mapping Functions
# =============================================================================

def extract_jotform_conditions(form_data: Dict[str, Any]) -> Tuple[List[str], str]:
    """
    Extract conditions from Jotform submission with robust field detection.
    
    Handles multiple Jotform field name patterns and formats:
    - Array format: ["Depression", "Anxiety"]
    - String format: "Depression"
    - Comma-separated: "Depression, Anxiety"
    - Nested objects with answer/text fields
    - "Other" with embedded text (e.g., "Other: Bipolar")
    - "Other (please specify)" with separate text field
    
    Args:
        form_data: Raw Jotform submission data
        
    Returns:
        Tuple of (conditions list, other_condition_text)
    """
    conditions_raw = None
    other_text = ""
    
    # List of possible field names for conditions (Jotform field IDs vary)
    condition_fields = [
        "q12_whatCondition",
        "q12_condition",
        "q12_whatConditions",
        "q11_whatCondition",
        "q11_condition",
        "q13_whatCondition",
        "q13_condition",
        "whatCondition",
        "condition",
        "conditions",
        "primaryCondition",
        "primary_condition",
        "mental_health_condition",
        "diagnosis",
    ]
    
    # Try each field pattern
    for field in condition_fields:
        if field in form_data:
            value = form_data[field]
            if value:
                conditions_raw = value
                logger.info(f"Jotform condition found in field '{field}': {value}")
                break
    
    # Also scan for any field containing "condition" in the key
    if not conditions_raw:
        for key, value in form_data.items():
            key_lower = key.lower()
            if "condition" in key_lower and "other" not in key_lower and value:
                conditions_raw = value
                logger.info(f"Jotform condition found via pattern matching in '{key}': {value}")
                break
    
    # Handle nested Jotform answer format: {"answer": "Depression"} or {"text": "Depression"}
    if isinstance(conditions_raw, dict):
        if "answer" in conditions_raw:
            conditions_raw = conditions_raw["answer"]
        elif "text" in conditions_raw:
            conditions_raw = conditions_raw["text"]
        elif "value" in conditions_raw:
            conditions_raw = conditions_raw["value"]
        # Also check for "other" key in the dict (Jotform checkbox with "Other" option)
        if "other" in conditions_raw and conditions_raw["other"]:
            other_text = sanitize_input(conditions_raw["other"])
            logger.info(f"Jotform 'other' condition found in nested dict: {other_text}")
    
    # Extract "Other" condition text from various field patterns
    other_fields = [
        "q13_otherCondition",
        "q12_otherCondition",
        "q14_otherCondition",
        "q12_otherCondition12",  # Jotform sometimes appends field ID
        "q13_otherCondition13",
        "otherCondition",
        "other_condition",
        "other_condition_text",
        "conditionOther",
        "condition_other",
        "pleaseSpecify",
        "please_specify",
        "q12_pleaseSpecify",
        "q13_pleaseSpecify",
        "specify",
        "other",
    ]
    
    if not other_text:  # Only search if not already found
        for field in other_fields:
            if field in form_data and form_data[field]:
                other_text = sanitize_input(form_data[field])
                logger.info(f"Jotform 'other' condition text found in field '{field}': {other_text}")
                break
    
    # Also check for any field containing "other" and "condition" together
    if not other_text:
        for key, value in form_data.items():
            key_lower = key.lower()
            if ("other" in key_lower and "condition" in key_lower) or \
               ("specify" in key_lower) or \
               (key_lower.endswith("_other")) or \
               (key_lower.endswith("other")):
                if value and isinstance(value, str) and value.strip():
                    # Skip if it's just "Other" without actual text
                    if value.lower().strip() not in ["other", "n/a", "na", ""]:
                        other_text = sanitize_input(value)
                        logger.info(f"Jotform 'other' found via pattern in '{key}': {other_text}")
                        break
    
    # Handle conditions as list - check for "Other" with embedded text
    if isinstance(conditions_raw, list):
        for i, item in enumerate(conditions_raw):
            if isinstance(item, str):
                item_lower = item.lower().strip()
                # Check for "Other: <text>" or "Other - <text>" patterns
                if item_lower.startswith("other:"):
                    other_text = item[6:].strip()  # Extract text after "Other:"
                    logger.info(f"Jotform 'other' extracted from condition value: {other_text}")
                elif item_lower.startswith("other -"):
                    other_text = item[7:].strip()  # Extract text after "Other -"
                    logger.info(f"Jotform 'other' extracted from condition value (dash): {other_text}")
                elif item_lower.startswith("other (") and ")" in item:
                    # Handle "Other (please specify): <text>" format
                    paren_end = item.index(")")
                    if len(item) > paren_end + 1:
                        suffix = item[paren_end + 1:].strip()
                        if suffix.startswith(":"):
                            other_text = suffix[1:].strip()
                        elif suffix:
                            other_text = suffix
                        logger.info(f"Jotform 'other' extracted from parenthetical: {other_text}")
            elif isinstance(item, dict):
                # Handle nested structure in array: [{"value": "Other", "text": "Bipolar"}]
                if item.get("value", "").lower() == "other" and item.get("text"):
                    other_text = sanitize_input(item["text"])
                    logger.info(f"Jotform 'other' from nested array dict: {other_text}")
    
    # Handle single string condition with "Other: <text>" pattern
    if isinstance(conditions_raw, str):
        cond_lower = conditions_raw.lower().strip()
        if cond_lower.startswith("other:"):
            other_text = conditions_raw[6:].strip()
            logger.info(f"Jotform 'other' extracted from string condition: {other_text}")
        elif cond_lower.startswith("other -"):
            other_text = conditions_raw[7:].strip()
            logger.info(f"Jotform 'other' extracted from string condition (dash): {other_text}")
    
    conditions = normalize_conditions_list(conditions_raw)
    
    # If "other" is in conditions but no other_text, check one more time for any text field
    if "other" in conditions and not other_text:
        # Last resort: scan ALL form fields for potential "other" text
        for key, value in form_data.items():
            if isinstance(value, str) and value.strip():
                # Skip known non-other fields
                if key.lower() in ["formid", "submissionid", "ip", "rawrequest"]:
                    continue
                # Check if this looks like an "other" specification field
                key_lower = key.lower()
                if "other" in key_lower or "specify" in key_lower or "describe" in key_lower:
                    if value.lower().strip() not in ["other", "n/a", "na", "none", ""]:
                        other_text = sanitize_input(value)
                        logger.info(f"Jotform 'other' found in last-resort scan '{key}': {other_text}")
                        break
    
    # Log summary for debugging
    logger.info(f"Jotform conditions extracted: {conditions}, other_text: '{other_text}'")
    
    # If no conditions found but we have form data, log for debugging
    if not conditions:
        logger.warning(f"No conditions extracted from Jotform. Available fields: {list(form_data.keys())}")
        # Check if any field values contain condition keywords
        for key, value in form_data.items():
            if isinstance(value, str):
                value_lower = value.lower()
                for condition_keyword in ["depression", "anxiety", "ocd", "ptsd"]:
                    if condition_keyword in value_lower:
                        logger.info(f"Potential condition found in field '{key}': {value}")
    
    return conditions, other_text


def extract_jotform_preferred_contact(form_data: Dict[str, Any]) -> str:
    """
    Extract preferred contact method from Jotform with robust field detection.
    
    Handles multiple field name patterns and formats.
    Returns normalized contact method: phone_call, text, email, any
    """
    contact_raw = None
    
    # List of possible field names for preferred contact method
    contact_fields = [
        "q41_preferredContact",
        "q42_preferredContact",
        "q40_preferredContact",
        "q39_preferredContact",
        "preferredContact",
        "preferred_contact",
        "preferredContactMethod",
        "preferred_contact_method",
        "contact_method",
        "contactMethod",
        "howContact",
        "how_contact",
    ]
    
    # Try each field pattern
    for field in contact_fields:
        if field in form_data:
            value = form_data[field]
            if value:
                contact_raw = value
                logger.info(f"Jotform preferred contact found in field '{field}': {value}")
                break
    
    # Also scan for any field containing "contact" and "prefer" in the key
    if not contact_raw:
        for key, value in form_data.items():
            key_lower = key.lower()
            if ("contact" in key_lower or "prefer" in key_lower) and "method" not in key_lower.replace("contactmethod", ""):
                # Avoid false positives with contact info fields
                if "information" not in key_lower and "info" not in key_lower and "email" not in key_lower and "phone" not in key_lower:
                    if value and isinstance(value, (str, list)):
                        contact_raw = value
                        logger.info(f"Jotform preferred contact found via pattern matching in '{key}': {value}")
                        break
    
    # Handle nested Jotform answer format
    if isinstance(contact_raw, dict):
        if "answer" in contact_raw:
            contact_raw = contact_raw["answer"]
        elif "text" in contact_raw:
            contact_raw = contact_raw["text"]
        elif "value" in contact_raw:
            contact_raw = contact_raw["value"]
    
    # Handle array format (checkboxes)
    if isinstance(contact_raw, list):
        # Take first non-empty value
        for item in contact_raw:
            if item:
                contact_raw = str(item)
                break
        else:
            contact_raw = ""
    
    # If still no contact found, log for debugging
    if not contact_raw:
        logger.warning(f"No preferred contact extracted from Jotform. Available fields: {list(form_data.keys())}")
        return ""  # Return empty - DO NOT default to phone
    
    # Normalize the value
    return normalize_contact_method(str(contact_raw))


def map_jotform_submission_to_lead_input(form_data: Dict[str, Any]) -> LeadInput:
    """
    Map Jotform submission data to canonical LeadInput.
    
    This is the single source of truth for Jotform field mapping.
    All Jotform field names and their transformations are defined here.
    
    Args:
        form_data: Raw Jotform submission data (parsed JSON)
        
    Returns:
        LeadInput: Normalized lead input data
    """
    # Extract patient name
    first_name, last_name = extract_patient_name_from_jotform(form_data)
    
    # Email - try multiple field patterns
    email = ""
    email_fields = ["q39_email", "q38_email", "q40_email", "email", "patientEmail", "patient_email"]
    for field in email_fields:
        if field in form_data and form_data[field]:
            email = sanitize_input(form_data[field])
            break
    
    # Phone - handle nested structure and multiple field patterns
    phone = ""
    phone_fields = ["q40_phoneNumber", "q39_phoneNumber", "q41_phoneNumber", "phoneNumber", "phone", "patient_phone"]
    for field in phone_fields:
        if field in form_data:
            phone_data = form_data[field]
            if isinstance(phone_data, dict):
                phone = normalize_phone(sanitize_input(phone_data.get("full", "")))
            else:
                phone = normalize_phone(sanitize_input(phone_data))
            if phone:
                break
    
    # Conditions (multi-select) - use robust extraction
    conditions, other_condition_text = extract_jotform_conditions(form_data)
    
    # If other_condition_text wasn't found by extract function, try direct field
    if not other_condition_text:
        other_condition_text = sanitize_input(form_data.get("q13_otherCondition", ""))
    
    # TMS therapy interest
    tms_interest = normalize_tms_interest(sanitize_input(form_data.get("q14_tmsInterest", "")))
    
    # Preferred contact method - use robust extraction (NO DEFAULT!)
    preferred_contact = extract_jotform_preferred_contact(form_data)
    
    # PHQ-2 Depression Assessment
    phq2_interest = safe_int(form_data.get("q15_phq2Interest"))
    phq2_mood = safe_int(form_data.get("q16_phq2Mood"))
    
    # GAD-2 Anxiety Assessment
    gad2_nervous = safe_int(form_data.get("q17_gad2Nervous"))
    gad2_worry = safe_int(form_data.get("q18_gad2Worry"))
    
    # OCD Assessment
    ocd_time_occupied = safe_int(form_data.get("q19_ocdTime"))
    
    # PTSD Assessment
    ptsd_intrusion = safe_int(form_data.get("q20_ptsdIntrusion"))
    
    # Symptom duration
    duration = normalize_duration(sanitize_input(form_data.get("q21_howLong", "")))
    
    # Prior treatments
    treatments_raw = form_data.get("q22_whatTreatments", [])
    treatments = normalize_treatments(treatments_raw)
    
    # Insurance
    has_insurance = parse_yes_no(sanitize_input(form_data.get("q24_doYou", "")))
    insurance_provider_raw = sanitize_input(form_data.get("q25_insuranceProvider", ""))
    insurance_provider, is_other_insurance = normalize_insurance_provider(insurance_provider_raw)
    other_insurance = sanitize_input(form_data.get("q25b_otherInsurance", "")) if is_other_insurance else ""
    
    # ZIP code
    zip_code = normalize_zip(sanitize_input(form_data.get("q26_whatIs", "")))
    
    # Urgency
    urgency = normalize_urgency(sanitize_input(form_data.get("q27_whenWould", "")))
    
    # Consent
    hipaa_consent = parse_yes_no(sanitize_input(form_data.get("q28_hipaaConsent", "")))
    sms_consent = parse_yes_no(sanitize_input(form_data.get("q29_smsConsent", "")))
    
    # Referral information
    referred_by_provider = parse_yes_no(sanitize_input(form_data.get("q43_wereYou", "")))
    referring_provider_name = sanitize_input(form_data.get("q44_referringProviders", ""))
    referring_clinic = sanitize_input(form_data.get("q45_clinicpracticeName", ""))
    
    # Provider email - try multiple field patterns (comprehensive list)
    referring_provider_email = ""
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
        "q49_providersEmail",
        "q49_providerEmail",
        "q50_providersEmail",
        "q50_providerEmail",
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
        value = form_data.get(field, "")
        if value and isinstance(value, str) and "@" in value:
            referring_provider_email = sanitize_input(value).lower()
            logger.info(f"Jotform provider email found in field '{field}': {referring_provider_email}")
            break
    
    # If not found, try pattern matching on all field names containing "email" + "provider"
    if not referring_provider_email:
        for key, value in form_data.items():
            key_lower = key.lower()
            if "email" in key_lower and ("provider" in key_lower or "referr" in key_lower):
                if value and isinstance(value, str) and "@" in value:
                    referring_provider_email = sanitize_input(value).lower()
                    logger.info(f"Jotform provider email found via pattern match in '{key}': {referring_provider_email}")
                    break
    
    # Last resort: Check for any email field that's not the patient email
    if not referring_provider_email:
        patient_email = email  # We extracted patient email earlier
        for key, value in form_data.items():
            if isinstance(value, str) and "@" in value:
                email_value = sanitize_input(value).lower()
                # Skip if it's the patient email
                if email_value != patient_email.lower() and email_value:
                    referring_provider_email = email_value
                    logger.info(f"Jotform provider email found in last-resort scan '{key}': {referring_provider_email}")
                    break
    
    if not referring_provider_email and referred_by_provider:
        logger.warning(f"Jotform provider email NOT FOUND despite referral=Yes. Available fields: {list(form_data.keys())}")
    
    # Provider specialty - try multiple field patterns (comprehensive list)
    referring_provider_specialty = ""
    specialty_fields = [
        # Jotform question ID patterns (qXX_)
        "q48_providerSpecialty",
        "q47_providerSpecialty",
        "q46_providerSpecialty",
        "q49_providerSpecialty",
        "q50_providerSpecialty",
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
        value = form_data.get(field, "")
        if value and isinstance(value, str) and value.strip():
            referring_provider_specialty = sanitize_input(value).strip()
            logger.info(f"Jotform provider specialty found in field '{field}': {referring_provider_specialty}")
            break
    
    # If not found, try pattern matching on all field names containing "specialty"
    if not referring_provider_specialty:
        for key, value in form_data.items():
            key_lower = key.lower()
            if "specialty" in key_lower or "speciality" in key_lower:  # Handle common misspelling
                if value and isinstance(value, str) and value.strip():
                    referring_provider_specialty = sanitize_input(value).strip()
                    logger.info(f"Jotform provider specialty found via pattern match in '{key}': {referring_provider_specialty}")
                    break
    
    if not referring_provider_specialty and referred_by_provider:
        logger.info(f"Jotform provider specialty NOT FOUND (optional field)")
    
    return LeadInput(
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        conditions=conditions,
        other_condition_text=other_condition_text,
        tms_therapy_interest=tms_interest,
        preferred_contact_method=preferred_contact,
        phq2_interest=phq2_interest,
        phq2_mood=phq2_mood,
        gad2_nervous=gad2_nervous,
        gad2_worry=gad2_worry,
        ocd_time_occupied=ocd_time_occupied,
        ptsd_intrusion=ptsd_intrusion,
        symptom_duration=duration,
        prior_treatments=treatments,
        has_insurance=has_insurance,
        insurance_provider=insurance_provider,
        other_insurance_provider=other_insurance,
        zip_code=zip_code,
        urgency=urgency,
        hipaa_consent=hipaa_consent,
        sms_consent=sms_consent,
        referred_by_provider=referred_by_provider,
        referring_provider_name=referring_provider_name,
        referring_clinic=referring_clinic,
        referring_provider_email=referring_provider_email,
        referring_provider_specialty=referring_provider_specialty,
    )


def map_widget_submission_to_lead_input(payload: Dict[str, Any]) -> LeadInput:
    """
    Map Widget submission data to canonical LeadInput.
    
    This is the single source of truth for Widget field mapping.
    Widget uses snake_case field names matching the API schema.
    
    Args:
        payload: Widget submission data
        
    Returns:
        LeadInput: Normalized lead input data
    """
    # Conditions (multi-select array)
    conditions_raw = payload.get("conditions", [])
    if not conditions_raw:
        # Fallback to single condition field
        single_condition = payload.get("condition", "")
        conditions_raw = [single_condition] if single_condition else []
    conditions = normalize_conditions_list(conditions_raw)
    
    # Other condition text
    other_condition_text = sanitize_input(payload.get("other_condition_text", "") or payload.get("condition_other", ""))
    
    # TMS therapy interest
    tms_interest = normalize_tms_interest(sanitize_input(payload.get("tms_therapy_interest", "")))
    
    # Preferred contact method
    preferred_contact = normalize_contact_method(sanitize_input(payload.get("preferred_contact_method", "")))
    
    # PHQ-2 Depression Assessment
    phq2_interest = safe_int(payload.get("phq2_interest"))
    phq2_mood = safe_int(payload.get("phq2_mood"))
    
    # GAD-2 Anxiety Assessment
    gad2_nervous = safe_int(payload.get("gad2_nervous"))
    gad2_worry = safe_int(payload.get("gad2_worry"))
    
    # OCD Assessment
    ocd_time_occupied = safe_int(payload.get("ocd_time_occupied"))
    
    # PTSD Assessment
    ptsd_intrusion = safe_int(payload.get("ptsd_intrusion"))
    
    # Symptom duration
    duration = normalize_duration(sanitize_input(payload.get("symptom_duration", "")))
    
    # Prior treatments
    treatments_raw = payload.get("prior_treatments", [])
    treatments = normalize_treatments(treatments_raw)
    
    # Insurance
    has_insurance = parse_yes_no(payload.get("has_insurance", False))
    insurance_provider_raw = sanitize_input(payload.get("insurance_provider", ""))
    insurance_provider, is_other_insurance = normalize_insurance_provider(insurance_provider_raw)
    other_insurance = sanitize_input(payload.get("other_insurance_provider", "")) if is_other_insurance else ""
    
    # Date of birth
    dob_str = payload.get("date_of_birth", "")
    date_of_birth = None
    if dob_str:
        try:
            date_of_birth = date.fromisoformat(dob_str)
        except (ValueError, TypeError):
            pass
    
    # UTM parameters
    utm_params = payload.get("utm_params", {}) or {}
    
    # Referral information (NEW - Widget now supports referrals like Jotform)
    is_referral_raw = payload.get("is_referral")
    referred_by_provider = parse_yes_no(is_referral_raw) if is_referral_raw is not None else False
    referring_provider_name = sanitize_input(payload.get("referring_provider_name", ""))
    referring_clinic = sanitize_input(payload.get("referring_clinic", ""))
    referring_provider_email = sanitize_input(payload.get("referring_provider_email", "")).lower() if payload.get("referring_provider_email") else ""
    referring_provider_specialty = sanitize_input(payload.get("referring_provider_specialty", ""))
    
    return LeadInput(
        first_name=sanitize_input(payload.get("first_name", "")),
        last_name=sanitize_input(payload.get("last_name", "")),
        email=sanitize_input(payload.get("email", "")),
        phone=normalize_phone(sanitize_input(payload.get("phone", ""))),
        date_of_birth=date_of_birth,
        conditions=conditions,
        other_condition_text=other_condition_text,
        tms_therapy_interest=tms_interest,
        preferred_contact_method=preferred_contact,
        phq2_interest=phq2_interest,
        phq2_mood=phq2_mood,
        gad2_nervous=gad2_nervous,
        gad2_worry=gad2_worry,
        ocd_time_occupied=ocd_time_occupied,
        ptsd_intrusion=ptsd_intrusion,
        symptom_duration=duration,
        prior_treatments=treatments,
        has_insurance=has_insurance,
        insurance_provider=insurance_provider,
        other_insurance_provider=other_insurance,
        zip_code=normalize_zip(sanitize_input(payload.get("zip_code", ""))),
        urgency=normalize_urgency(sanitize_input(payload.get("urgency", ""))),
        hipaa_consent=parse_yes_no(payload.get("hipaa_consent", False)),
        sms_consent=parse_yes_no(payload.get("sms_consent", False)),
        # Referral information
        referred_by_provider=referred_by_provider,
        referring_provider_name=referring_provider_name,
        referring_clinic=referring_clinic,
        referring_provider_email=referring_provider_email,
        referring_provider_specialty=referring_provider_specialty,
        # UTM tracking
        utm_source=utm_params.get("utm_source"),
        utm_medium=utm_params.get("utm_medium"),
        utm_campaign=utm_params.get("utm_campaign"),
        utm_term=utm_params.get("utm_term"),
        utm_content=utm_params.get("utm_content"),
        referrer_url=payload.get("referrer_url"),
    )
