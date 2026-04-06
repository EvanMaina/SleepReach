"""
Canonical Intake Mapping Layer for SleepReach.

Maps intake data from multiple sources (Jotform, Widget) to a
standardized LeadInput format for the sleep clinic.

Conditions: insomnia, sleep_apnea, restless_leg, narcolepsy, other
Treatments: cpap_bipap, medication, sleep_study, therapy_cbt, none, other
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
    sleep_treatment_interest: str = ""  # cpap_bipap, sleep_study, medication, not_sure

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
    return str(value).lower().strip() in ["yes", "true", "1", "y"]


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
    for key, keywords in CONDITION_KEYWORDS.items():
        for keyword in keywords:
            if keyword in condition_lower:
                return key
    return "other"


def normalize_conditions_list(conditions_raw: Any) -> List[str]:
    if not conditions_raw:
        return []
    if isinstance(conditions_raw, str):
        raw_list = [c.strip() for c in conditions_raw.split(",") if c.strip()]
    elif isinstance(conditions_raw, list):
        raw_list = [str(c).strip() for c in conditions_raw if c]
    else:
        raw_list = [str(conditions_raw).strip()]

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
    "none": ["none", "no treatment", "nothing"],
}


def normalize_treatments(treatments_raw: Any) -> List[str]:
    if not treatments_raw:
        return []
    if isinstance(treatments_raw, str):
        raw_list = [c.strip() for c in treatments_raw.split(",") if c.strip()]
    elif isinstance(treatments_raw, list):
        raw_list = [str(c).strip() for c in treatments_raw if c]
    else:
        raw_list = [str(treatments_raw).strip()]

    normalized = set()
    for raw in raw_list:
        raw_lower = raw.lower()
        matched = False
        for key, keywords in TREATMENT_KEYWORDS.items():
            if key == "none":
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
    "sleep study": "sleep_study",
    "sleep_study": "sleep_study",
    "medication": "medication",
    "not sure": "not_sure",
    "not_sure": "not_sure",
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

    name_fields = [
        "q30_fullName", "q30_name",
        "q38_contactInformation", "q3_fullName", "q3_name",
        "q4_fullName", "q4_name", "name", "full_name",
        "patient_name", "patientName",
    ]

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

    NEW Jotform form (260953996150062) question ID mapping:
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

    Each field tries the new q-ID first, then falls back to old IDs for compatibility.
    """
    first_name, last_name = extract_patient_name_from_jotform(form_data)

    # Email — q19 (new) or q39 (old)
    email = ""
    for fld in ["q19_email", "q19_emailAddress", "q39_email", "q38_email", "email"]:
        if fld in form_data and form_data[fld]:
            email = sanitize_input(form_data[fld])
            break

    # Phone — q20 (new) or q40 (old)
    phone = ""
    for fld in ["q20_phoneNumber", "q20_phone", "q40_phoneNumber", "q39_phoneNumber", "phoneNumber", "phone"]:
        if fld in form_data:
            phone_data = form_data[fld]
            if isinstance(phone_data, dict):
                phone = normalize_phone(sanitize_input(phone_data.get("full", "")))
            else:
                phone = normalize_phone(sanitize_input(phone_data))
            if phone:
                break

    # Sleep concerns (conditions) — q6 (new) or q12 (old)
    conditions_raw = None
    for fld in ["q6_whatSleep", "q6_sleepConcerns", "q12_whatCondition", "q12_condition", "condition", "conditions"]:
        if fld in form_data and form_data[fld]:
            conditions_raw = form_data[fld]
            break
    conditions = normalize_conditions_list(conditions_raw)

    # Other sleep concern text — q7 (new) or q13_otherCondition (old)
    other_condition_text = ""
    for fld in ["q7_tellUs", "q7_sleepConcern", "q13_otherCondition", "otherCondition", "other_condition", "condition_other"]:
        if fld in form_data and form_data[fld]:
            other_condition_text = sanitize_input(form_data[fld])
            break

    # Sleep treatment interest — q8 (new) or q14 (old)
    sleep_interest = ""
    for fld in ["q8_whatAre", "q8_treatmentInterest", "q14_sleepTreatment", "q14_tmsInterest"]:
        val = form_data.get(fld, "")
        if val:
            sleep_interest = normalize_sleep_treatment_interest(sanitize_input(val))
            break

    # Preferred contact method — q22 (new) or q41/q42 (old)
    preferred_contact = ""
    for fld in ["q22_howWould", "q22_preferredContact", "q41_preferredContact", "q42_preferredContact", "preferredContact"]:
        if fld in form_data and form_data[fld]:
            preferred_contact = normalize_contact_method(sanitize_input(form_data[fld]))
            break

    # Symptom duration — q9 (new) or q21 (old)
    duration = normalize_duration(sanitize_input(
        form_data.get("q9_howLong", "") or form_data.get("q9_symptomDuration", "")
        or form_data.get("q21_howLong", "")
    ))

    # Prior treatments — q10 (new) or q22 (old, but q22 is now preferred_contact in new form)
    treatments_raw = None
    for fld in ["q10_whatHave", "q10_treatmentHistory", "q22_whatTreatments"]:
        if fld in form_data and form_data[fld]:
            treatments_raw = form_data[fld]
            break
    treatments = normalize_treatments(treatments_raw if treatments_raw else [])

    # Insurance — q24
    has_insurance = parse_yes_no(sanitize_input(
        form_data.get("q24_doYou", "") or form_data.get("q24_insurance", "")
    ))
    insurance_provider_raw = sanitize_input(
        form_data.get("q25_insuranceProvider", "") or form_data.get("q25_insurance", "")
    )
    insurance_provider, is_other_insurance = normalize_insurance_provider(insurance_provider_raw)
    other_insurance = sanitize_input(form_data.get("q25b_otherInsurance", "")) if is_other_insurance else ""

    # ZIP code — q26
    zip_code = normalize_zip(sanitize_input(
        form_data.get("q26_zipCode", "") or form_data.get("q26_whatIs", "")
    ))

    # Urgency — q11 (new) or q27 (old)
    urgency = normalize_urgency(sanitize_input(
        form_data.get("q11_howSoon", "") or form_data.get("q11_urgency", "")
        or form_data.get("q27_whenWould", "")
    ))

    # Consent — q5 (privacy/HIPAA), q23 (SMS)
    hipaa_consent = parse_yes_no(sanitize_input(
        form_data.get("q5_privacyConsent", "") or form_data.get("q5_consent", "")
        or form_data.get("q28_hipaaConsent", "")
    ))
    sms_consent = parse_yes_no(sanitize_input(
        form_data.get("q23_smsConsent", "") or form_data.get("q23_sms", "")
        or form_data.get("q29_smsConsent", "")
    ))

    # Referral — q12 (new Yes/No) or q43 (old)
    referred_by_provider = parse_yes_no(sanitize_input(
        form_data.get("q12_wereYou", "") or form_data.get("q12_referral", "")
        or form_data.get("q43_wereYou", "")
    ))

    # Provider name — q13 (new) or q44 (old)
    referring_provider_name = sanitize_input(
        form_data.get("q13_providerName", "") or form_data.get("q13_provider", "")
        or form_data.get("q44_referringProviders", "")
    )

    # Clinic — q16 (new) or q45 (old)
    referring_clinic = sanitize_input(
        form_data.get("q16_clinicOr", "") or form_data.get("q16_clinic", "")
        or form_data.get("q45_clinicpracticeName", "")
    )

    # Provider email — q15 (new) or q46/q47 (old)
    referring_provider_email = ""
    for fld in ["q15_providerEmail", "q15_providersEmail", "q46_providersEmail", "q46_providerEmail", "q47_providersEmail", "providerEmail"]:
        value = form_data.get(fld, "")
        if value and isinstance(value, str) and "@" in value:
            referring_provider_email = sanitize_input(value).lower()
            break

    # Provider specialty — q14 (new) or q48 (old)
    referring_provider_specialty = ""
    for fld in ["q14_specialty", "q14_providerSpecialty", "q48_providerSpecialty", "q47_providerSpecialty", "providerSpecialty", "specialty"]:
        value = form_data.get(fld, "")
        if value and isinstance(value, str) and value.strip():
            referring_provider_specialty = sanitize_input(value).strip()
            break

    return LeadInput(
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
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
