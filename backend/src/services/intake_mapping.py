"""
Canonical Intake Mapping Layer for SleepReach.

Maps intake data from multiple sources (Jotform, Widget) to a
standardized LeadInput format for the sleep clinic.

Conditions: insomnia, sleep_apnea, restless_leg, narcolepsy, other
Treatments: cpap_bipap, medication, sleep_study, therapy_cbt, none, other
"""

import ast
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from datetime import date, datetime

logger = logging.getLogger(__name__)

MASKED_PLACEHOLDER_PATTERN = re.compile(r"^[\*\u2022\u25cf\u25a0#xX\-_\. ]+$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# =============================================================================
# Canonical LeadInput Dataclass
# =============================================================================

@dataclass
class LeadInput:
    """Canonical lead input data structure for sleep clinic."""

    # Contact Information
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""
    date_of_birth: Optional[date] = None

    # Multi-condition support (normalized lowercase keys)
    # Valid values: insomnia, sleep_apnea, restless_leg, narcolepsy, other
    conditions: List[str] = field(default_factory=list)
    primary_condition: str = ""
    other_condition_text: str = ""

    # Sleep Treatment Interest
    sleep_treatment_interest: str = ""  # cpap_bipap, inspire, therapy_cbt, sleep_study, medication, not_sure

    # Preferred Contact Method
    preferred_contact_method: str = ""  # phone_call, text, email, any

    # Insurance Information
    has_insurance: bool = False
    insurance_provider: str = ""
    other_insurance_provider: str = ""

    # Location
    zip_code: str = ""

    # Symptom Duration
    symptom_duration: str = ""  # less_than_6_months, 6_to_12_months, more_than_12_months

    # Prior Treatments
    prior_treatments: List[str] = field(default_factory=list)  # cpap_bipap, medication, sleep_study, therapy_cbt, none, other

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
    referring_provider_specialty: str = ""

    # UTM Tracking
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_term: Optional[str] = None
    utm_content: Optional[str] = None

    # Metadata
    referrer_url: Optional[str] = None

    def __post_init__(self):
        if self.conditions and not self.primary_condition:
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
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return str(value)
    return str(value).strip()


def _jget(data: Dict[str, Any], qid: str) -> Any:
    """
    Get a Jotform field by question ID prefix.

    Jotform generates field names like q19_q19_email17, q6_q6_checkbox4,
    q30_fullName. This helper finds the first key starting with 'q{id}_'.
    """
    prefix = f"q{qid}_"
    for key in data:
        if key.startswith(prefix):
            return data[key]
    return None


def is_masked_placeholder(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, dict):
        return any(is_masked_placeholder(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(is_masked_placeholder(item) for item in value)

    text = str(value).strip()
    if not text:
        return False

    if "@" in text:
        local_part = text.split("@", 1)[0].strip()
        if local_part and MASKED_PLACEHOLDER_PATTERN.fullmatch(local_part):
            return True

    return bool(MASKED_PLACEHOLDER_PATTERN.fullmatch(text)) and any(
        marker in text for marker in ("*", "\u2022", "\u25cf", "\u25a0", "#")
    )


def has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip()) and not is_masked_placeholder(value)
    if isinstance(value, dict):
        return any(has_value(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(has_value(item) for item in value)
    return True


def validate_canonical_lead_input(lead_input: LeadInput) -> List[str]:
    """
    Validate canonical lead input before persistence.

    This is especially important for Jotform HIPAA webhooks, which may mask PHI
    as "***" if the form is not configured to send PHI to webhooks.
    """
    errors: List[str] = []

    def _add(message: str) -> None:
        if message not in errors:
            errors.append(message)

    if not lead_input.hipaa_consent:
        _add("HIPAA consent is required.")

    if not lead_input.first_name or is_masked_placeholder(lead_input.first_name):
        _add("First name is missing or masked.")
    if not lead_input.last_name or is_masked_placeholder(lead_input.last_name):
        _add("Last name is missing or masked.")

    email = (lead_input.email or "").strip()
    if not email or is_masked_placeholder(email) or not EMAIL_PATTERN.fullmatch(email):
        _add("Email address is missing or invalid.")

    phone_digits = re.sub(r"\D", "", lead_input.phone or "")
    if not phone_digits or len(phone_digits) < 10:
        _add("Phone number is missing or invalid.")

    if not lead_input.conditions:
        _add("At least one sleep concern is required.")

    if "other" in lead_input.conditions:
        if not lead_input.other_condition_text or is_masked_placeholder(lead_input.other_condition_text):
            _add("Other sleep concern details are missing or masked.")

    if not lead_input.sleep_treatment_interest:
        _add("Treatment interest is required.")

    if not lead_input.symptom_duration:
        _add("Symptom duration is required.")

    if not lead_input.prior_treatments:
        _add("Treatment history is required.")

    if not lead_input.urgency:
        _add("Urgency is required.")

    if not lead_input.preferred_contact_method:
        _add("Preferred contact method is required.")

    zip_code = (lead_input.zip_code or "").strip()
    if not re.fullmatch(r"\d{5}", zip_code or "") or zip_code == "00000":
        _add("ZIP code must be a valid 5-digit service-area ZIP.")

    if lead_input.has_insurance:
        if not lead_input.insurance_provider or is_masked_placeholder(lead_input.insurance_provider):
            _add("Insurance provider is required when insurance is selected.")

    if lead_input.referred_by_provider:
        if not lead_input.referring_provider_name or is_masked_placeholder(lead_input.referring_provider_name):
            _add("Referring provider name is required when referral is selected.")
        if lead_input.referring_provider_email:
            email_value = lead_input.referring_provider_email.strip()
            if is_masked_placeholder(email_value) or not EMAIL_PATTERN.fullmatch(email_value):
                _add("Referring provider email is invalid.")

    return errors


def get_first_non_empty(data: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data and has_value(data[key]):
            return data[key]
    return None


def extract_multi_values(raw_value: Any) -> List[str]:
    values: List[str] = []

    def _collect(value: Any) -> None:
        if value is None:
            return

        if isinstance(value, dict):
            for nested in value.values():
                _collect(nested)
            return

        if isinstance(value, (list, tuple, set)):
            for nested in value:
                _collect(nested)
            return

        text = str(value).strip()
        if not text:
            return

        if (text.startswith("[") and text.endswith("]")) or (
            text.startswith("{") and text.endswith("}")
        ):
            try:
                parsed = ast.literal_eval(text)
            except (SyntaxError, ValueError):
                parsed = None
            if parsed is not None and parsed != value:
                _collect(parsed)
                return

        parts = re.split(r"\s*,\s*", text) if "," in text else [text]
        for part in parts:
            cleaned = part.strip().strip("\"'").strip()
            if cleaned:
                values.append(cleaned)

    _collect(raw_value)
    return values


def normalize_phone(phone: str) -> str:
    if not phone:
        return ""
    has_plus = phone.strip().startswith('+')
    digits = re.sub(r"[^\d]", "", phone)
    if has_plus and digits:
        return f"+{digits}"
    return digits if digits else ""


def normalize_zip(zip_code: str) -> str:
    if not zip_code:
        return "00000"
    digits = re.sub(r"[^\d]", "", zip_code)
    return digits[:5] if len(digits) >= 5 else digits.zfill(5)


def parse_yes_no(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        return any(parse_yes_no(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(parse_yes_no(item) for item in value)

    normalized = re.sub(r"\s+", " ", str(value).lower().strip())
    if not normalized:
        return False

    false_values = {
        "no",
        "false",
        "0",
        "n",
        "off",
        "no insurance",
    }
    if normalized in false_values or normalized.startswith("no "):
        return False

    true_values = {"yes", "true", "1", "y", "on", "checked"}
    if normalized in true_values or normalized.startswith("yes"):
        return True

    return any(token in normalized for token in ("consent", "agree", "acknowledge"))


def safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


# =============================================================================
# Condition Mapping (Sleep Disorders)
# =============================================================================

CONDITION_KEYWORDS = {
    "insomnia": ["insomnia", "can't sleep", "cant sleep", "sleepless", "trouble sleeping"],
    "sleep_apnea": ["sleep apnea", "apnea", "osa", "obstructive sleep", "breathing"],
    "restless_leg": ["restless leg", "rls", "restless legs", "leg syndrome"],
    "narcolepsy": ["narcolepsy", "narcoleptic", "excessive sleepiness", "cataplexy"],
    "other": ["other"],
}


def normalize_condition(condition_str: str) -> str:
    if not condition_str:
        return "other"
    condition_lower = condition_str.lower().strip()
    condition_normalized = condition_lower.replace("_", " ").replace("-", " ")
    for key, keywords in CONDITION_KEYWORDS.items():
        for keyword in keywords:
            if keyword in condition_lower or keyword in condition_normalized:
                return key
    return "other"


def normalize_conditions_list(conditions_raw: Any) -> List[str]:
    if not conditions_raw:
        return []
    raw_list = extract_multi_values(conditions_raw)

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
    if not duration:
        return "less_than_6_months"
    duration_lower = duration.lower().strip()
    for key, value in DURATION_MAP.items():
        if key in duration_lower or duration_lower == value:
            return value
    return "less_than_6_months"


# =============================================================================
# Treatment Mapping (Sleep Treatments)
# =============================================================================

TREATMENT_KEYWORDS = {
    "cpap_bipap": [
        "cpap", "bipap", "bi-pap", "c-pap", "positive airway", "pap therapy",
        "continuous positive", "bilevel"
    ],
    "medication": [
        "medication", "ambien", "lunesta", "trazodone", "melatonin",
        "sleep aid", "sleeping pill", "prescription"
    ],
    "sleep_study": [
        "sleep study", "polysomnography", "psg", "sleep test", "overnight study"
    ],
    "therapy_cbt": [
        "therapy", "cbt", "cognitive", "counseling", "cbt-i",
        "behavioral", "psychotherapy"
    ],
    "none": ["none", "no treatment", "no prior treatment", "nothing"],
}


def normalize_treatments(treatments_raw: Any) -> List[str]:
    if not treatments_raw:
        return []
    raw_list = extract_multi_values(treatments_raw)

    normalized = set()
    for raw in raw_list:
        raw_lower = raw.lower()
        if any(keyword in raw_lower for keyword in TREATMENT_KEYWORDS["none"]):
            normalized.add("none")
            continue
        matched = False
        for key, keywords in TREATMENT_KEYWORDS.items():
            if key == "none":
                continue
            for keyword in keywords:
                if keyword in raw_lower:
                    normalized.add(key)
                    matched = True
                    break
        if not matched and raw_lower not in ["none", "no treatment", "no prior treatment", "nothing"]:
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
    if not urgency:
        return "exploring"
    urgency_lower = urgency.lower().strip()
    for key, value in URGENCY_MAP.items():
        if key in urgency_lower or urgency_lower == value:
            return value
    return "exploring"


# =============================================================================
# Sleep Treatment Interest Mapping
# =============================================================================

SLEEP_TREATMENT_MAP = {
    "cpap": "cpap_bipap",
    "bipap": "cpap_bipap",
    "cpap_bipap": "cpap_bipap",
    "cpap/bipap": "cpap_bipap",
    "inspire": "inspire",
    "inspire therapy": "inspire",
    "therapy_cbt": "therapy_cbt",
    "cbt-i": "therapy_cbt",
    "cbt i": "therapy_cbt",
    "cbti": "therapy_cbt",
    "therapy or cbt-i": "therapy_cbt",
    "cbt-i therapy": "therapy_cbt",
    "sleep study": "sleep_study",
    "sleep_study": "sleep_study",
    "medication": "medication",
    "medication review": "medication",
    "not sure": "not_sure",
    "not_sure": "not_sure",
    "not sure yet": "not_sure",
    "unsure": "not_sure",
}


def normalize_sleep_treatment_interest(interest: str) -> str:
    if not interest:
        return "not_sure"
    interest_lower = interest.lower().strip()
    for key, value in SLEEP_TREATMENT_MAP.items():
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
    "banner",
    "mercy care",
]


def is_in_network_provider(provider: str) -> bool:
    if not provider:
        return False
    provider_lower = provider.lower().strip()
    for in_network in IN_NETWORK_PROVIDERS:
        if in_network in provider_lower or provider_lower in in_network:
            return True
    return False


def normalize_insurance_provider(provider: str) -> Tuple[str, bool]:
    if not provider:
        return "", False
    provider_clean = provider.strip()
    if provider_clean.lower() in ["other", "other provider", "different provider"]:
        return "Other", True
    return provider_clean, False


# =============================================================================
# Jotform Field Extraction Helpers
# =============================================================================

def extract_patient_name_from_jotform(data: Dict[str, Any]) -> Tuple[str, str]:
    first_name = ""
    last_name = ""

    # Try _jget for q30 first (matches q30_fullName, q30_q30_xxx, etc.)
    q30_val = _jget(data, "30")
    if q30_val:
        if isinstance(q30_val, dict):
            first = sanitize_input(q30_val.get("first", "") or q30_val.get("firstName", ""))
            last = sanitize_input(q30_val.get("last", "") or q30_val.get("lastName", ""))
            if first or last:
                return first, last
        elif isinstance(q30_val, str) and q30_val.strip():
            parts = q30_val.strip().split(' ', 1)
            return sanitize_input(parts[0]), sanitize_input(parts[1]) if len(parts) > 1 else ""

    name_fields = ["q30_fullName", "q30_name", "full_name", "name"]

    for fld in name_fields:
        if fld in data:
            value = data[fld]
            if isinstance(value, dict):
                first = sanitize_input(value.get("first", "") or value.get("firstName", ""))
                last = sanitize_input(value.get("last", "") or value.get("lastName", ""))
                if first or last:
                    first_name, last_name = first, last
                    break
            elif isinstance(value, str) and value.strip():
                parts = value.strip().split(' ', 1)
                first_name = sanitize_input(parts[0])
                last_name = sanitize_input(parts[1]) if len(parts) > 1 else ""
                break

    if not first_name:
        bracket_first = sanitize_input(get_first_non_empty(data, "q30_fullName[first]", "q30_first"))
        bracket_last = sanitize_input(get_first_non_empty(data, "q30_fullName[last]", "q30_last"))
        if bracket_first or bracket_last:
            return bracket_first, bracket_last

        for fld in ["first_name", "firstName"]:
            if fld in data and data[fld]:
                first_name = sanitize_input(str(data[fld]))
                break
        for fld in ["last_name", "lastName"]:
            if fld in data and data[fld]:
                last_name = sanitize_input(str(data[fld]))
                break

    return first_name, last_name


# =============================================================================
# Main Mapping Functions
# =============================================================================

def map_jotform_submission_to_lead_input(form_data: Dict[str, Any]) -> LeadInput:
    """
    Map Jotform submission data to canonical LeadInput for sleep clinic.

    Jotform form ID: 260953996150062
    Question ID → Field (exact mapping, no fallbacks):
      q5  → privacy_consent          q6  → sleep_concerns (multi)
      q7  → sleep_concern_other      q8  → treatment_interest
      q9  → symptom_duration         q10 → treatment_history (multi)
      q11 → urgency                  q12 → referred_by_provider
      q13 → provider_name            q14 → specialty
      q15 → provider_email           q16 → clinic/practice
      q30 → full_name                q19 → email
      q20 → phone                    q21 → date_of_birth
      q22 → preferred_contact        q24 → has_insurance
      q25 → insurance_provider       q26 → zip_code
      q23 → sms_consent
    """
    first_name, last_name = extract_patient_name_from_jotform(form_data)

    # q19 — Email
    email = sanitize_input(
        _jget(form_data, "19") or get_first_non_empty(form_data, "q19_q19_email17", "q19_email", "q19_emailAddress") or ""
    )

    # q20 — Phone
    phone = ""
    phone_data = _jget(form_data, "20") or get_first_non_empty(form_data, "q20_q20_phone18", "q20_q20_phone18[full]", "q20_phoneNumber", "q20_phone")
    if isinstance(phone_data, dict):
        phone = normalize_phone(sanitize_input(phone_data.get("full", "") or phone_data.get("phone", "")))
    elif phone_data:
        phone = normalize_phone(sanitize_input(phone_data))

    # q21 — Date of birth (optional)
    date_of_birth = None
    dob_data = _jget(form_data, "21") or get_first_non_empty(form_data, "q21_q21_datetime19", "q21_dateOfBirth", "q21_date")
    if isinstance(dob_data, dict):
        month = sanitize_input(dob_data.get("month", ""))
        day = sanitize_input(dob_data.get("day", ""))
        year = sanitize_input(dob_data.get("year", ""))
    else:
        month = sanitize_input(get_first_non_empty(form_data, "q21_q21_datetime19[month]") or "")
        day = sanitize_input(get_first_non_empty(form_data, "q21_q21_datetime19[day]") or "")
        year = sanitize_input(get_first_non_empty(form_data, "q21_q21_datetime19[year]") or "")
        if dob_data and not (month and day and year):
            text = sanitize_input(dob_data)
            for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
                try:
                    if fmt == "%Y-%m-%d":
                        date_of_birth = date.fromisoformat(text)
                    else:
                        date_of_birth = datetime.strptime(text, fmt).date()
                    break
                except Exception:
                    continue
    if date_of_birth is None and month and day and year:
        try:
            date_of_birth = date(int(year), int(month), int(day))
        except (TypeError, ValueError):
            date_of_birth = None

    # q6 — Sleep concerns (multi-select)
    conditions_raw = (
        _jget(form_data, "6")
        or get_first_non_empty(form_data, "q6_q6_checkbox4[]", "q6_q6_checkbox4", "q6_whatSleep", "q6_sleepConcerns")
    )
    conditions = normalize_conditions_list(conditions_raw)
    logger.info("Jotform q6 conditions: raw=%r normalized=%s", conditions_raw, conditions)

    # q7 — Other sleep concern text
    other_condition_text = sanitize_input(
        _jget(form_data, "7")
        or get_first_non_empty(form_data, "q7_q7_textbox5", "q7_tellUs", "q7_sleepConcern")
        or ""
    )
    if other_condition_text and "other" not in conditions:
        conditions.append("other")

    # q8 — Treatment interest
    sleep_interest = normalize_sleep_treatment_interest(
        sanitize_input(_jget(form_data, "8") or get_first_non_empty(form_data, "q8_q8_radio6", "q8_whatAre", "q8_treatmentInterest") or "")
    )

    # q22 — Preferred contact method
    preferred_contact = normalize_contact_method(
        sanitize_input(_jget(form_data, "22") or get_first_non_empty(form_data, "q22_q22_radio20", "q22_howWould", "q22_preferredContact") or "")
    )

    # q9 — Symptom duration
    duration = normalize_duration(
        sanitize_input(_jget(form_data, "9") or get_first_non_empty(form_data, "q9_q9_radio7", "q9_howLong", "q9_symptomDuration") or "")
    )

    # q10 — Prior treatments (multi-select)
    treatments_raw = (
        _jget(form_data, "10")
        or get_first_non_empty(form_data, "q10_q10_checkbox8[]", "q10_q10_checkbox8", "q10_whatHave", "q10_treatmentHistory")
    )
    treatments = normalize_treatments(treatments_raw if treatments_raw else [])

    # q24 — Insurance
    has_insurance = parse_yes_no(
        _jget(form_data, "24") or get_first_non_empty(form_data, "q24_q24_radio22", "q24_doYou", "q24_insurance")
    )
    # q25 — Insurance provider
    insurance_provider_raw = sanitize_input(
        _jget(form_data, "25") or get_first_non_empty(form_data, "q25_q25_textbox23", "q25_insuranceProvider", "q25_insurance") or ""
    )
    insurance_provider, is_other_insurance = normalize_insurance_provider(insurance_provider_raw)
    other_insurance = sanitize_input(form_data.get("q25b_otherInsurance", "")) if is_other_insurance else ""

    # q26 — ZIP code
    zip_code = normalize_zip(
        sanitize_input(_jget(form_data, "26") or get_first_non_empty(form_data, "q26_q26_textbox24", "q26_zipCode", "q26_whatIs") or "")
    )

    # q11 — Urgency
    urgency = normalize_urgency(
        sanitize_input(_jget(form_data, "11") or get_first_non_empty(form_data, "q11_q11_radio9", "q11_howSoon", "q11_urgency") or "")
    )

    # q5 — Privacy/HIPAA consent
    hipaa_consent = parse_yes_no(
        _jget(form_data, "5") or get_first_non_empty(form_data, "q5_q5_checkbox3[]", "q5_q5_checkbox3", "q5_privacyConsent", "q5_consent")
    )
    # q23 — SMS consent
    sms_consent = parse_yes_no(
        _jget(form_data, "23") or get_first_non_empty(form_data, "q23_q23_checkbox21[]", "q23_q23_checkbox21", "q23_smsConsent", "q23_sms")
    )

    # q12 — Referred by provider (Yes/No)
    referred_by_provider = parse_yes_no(
        _jget(form_data, "12") or get_first_non_empty(form_data, "q12_q12_radio10", "q12_wereYou", "q12_referral")
    )
    # q13 — Provider name
    referring_provider_name = sanitize_input(
        _jget(form_data, "13") or get_first_non_empty(form_data, "q13_q13_textbox11", "q13_providerName", "q13_provider") or ""
    )
    # q16 — Clinic/practice
    referring_clinic = sanitize_input(
        _jget(form_data, "16") or get_first_non_empty(form_data, "q16_q16_textbox14", "q16_clinicOr", "q16_clinic") or ""
    )

    # q15 — Provider email
    referring_provider_email = ""
    raw_email = sanitize_input(
        _jget(form_data, "15") or get_first_non_empty(form_data, "q15_q15_email13", "q15_providerEmail", "q15_providersEmail") or ""
    )
    if raw_email and "@" in raw_email:
        referring_provider_email = raw_email.lower()

    # q14 — Provider specialty
    referring_provider_specialty = sanitize_input(
        _jget(form_data, "14") or get_first_non_empty(form_data, "q14_q14_textbox12", "q14_specialty", "q14_providerSpecialty") or ""
    )

    return LeadInput(
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        date_of_birth=date_of_birth,
        conditions=conditions,
        other_condition_text=other_condition_text,
        sleep_treatment_interest=sleep_interest,
        preferred_contact_method=preferred_contact,
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
    """Map Widget submission data to canonical LeadInput for sleep clinic."""
    # Conditions
    conditions_raw = payload.get("conditions", [])
    if not conditions_raw:
        single_condition = payload.get("condition", "")
        conditions_raw = [single_condition] if single_condition else []
    conditions = normalize_conditions_list(conditions_raw)

    other_condition_text = sanitize_input(
        payload.get("other_condition_text", "") or payload.get("condition_other", "")
    )

    sleep_interest = normalize_sleep_treatment_interest(
        sanitize_input(payload.get("sleep_treatment_interest", ""))
    )

    preferred_contact = normalize_contact_method(
        sanitize_input(payload.get("preferred_contact_method", ""))
    )

    duration = normalize_duration(sanitize_input(payload.get("symptom_duration", "")))
    treatments_raw = payload.get("prior_treatments", [])
    treatments = normalize_treatments(treatments_raw)

    has_insurance = parse_yes_no(payload.get("has_insurance", False))
    insurance_provider_raw = sanitize_input(payload.get("insurance_provider", ""))
    insurance_provider, is_other_insurance = normalize_insurance_provider(insurance_provider_raw)
    other_insurance = sanitize_input(payload.get("other_insurance_provider", "")) if is_other_insurance else ""

    dob_str = payload.get("date_of_birth", "")
    date_of_birth = None
    if dob_str:
        try:
            date_of_birth = date.fromisoformat(dob_str)
        except (ValueError, TypeError):
            pass

    utm_params = payload.get("utm_params", {}) or {}

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
        sleep_treatment_interest=sleep_interest,
        preferred_contact_method=preferred_contact,
        symptom_duration=duration,
        prior_treatments=treatments,
        has_insurance=has_insurance,
        insurance_provider=insurance_provider,
        other_insurance_provider=other_insurance,
        zip_code=normalize_zip(sanitize_input(payload.get("zip_code", ""))),
        urgency=normalize_urgency(sanitize_input(payload.get("urgency", ""))),
        hipaa_consent=parse_yes_no(payload.get("hipaa_consent", False)),
        sms_consent=parse_yes_no(payload.get("sms_consent", False)),
        referred_by_provider=referred_by_provider,
        referring_provider_name=referring_provider_name,
        referring_clinic=referring_clinic,
        referring_provider_email=referring_provider_email,
        referring_provider_specialty=referring_provider_specialty,
        utm_source=utm_params.get("utm_source"),
        utm_medium=utm_params.get("utm_medium"),
        utm_campaign=utm_params.get("utm_campaign"),
        utm_term=utm_params.get("utm_term"),
        utm_content=utm_params.get("utm_content"),
        referrer_url=payload.get("referrer_url"),
    )
