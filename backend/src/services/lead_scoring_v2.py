"""
Enhanced Lead Scoring Engine v2 for SleepReach.

Sleep clinic scoring for The Insomnia and Sleep Institute of Arizona.
Supports multi-condition intake and granular score breakdown.

SCORING RULES:
- Condition Score: weighted by sleep concern, with small bonus for multiple concerns
- Sleep Treatment Interest: CPAP/BiPAP/Inspire highest, CBT-I moderate, "Not Sure Yet" lowest
- Insurance: in-network=+30, other/out-of-network=+20, no insurance=-20
- Duration: >12 months=+20, 6-12 months=+10, <6 months=0
- Treatment history: prior trials add modest complexity/new-patient points
- Location: AZ ZIP (85xxx/86xxx)=+15, out of area=-100
- Urgency: ASAP=+30, within_30_days=+10, exploring=0
- Age: under 18 = disqualified (-100)

PRIORITY THRESHOLDS:
- >=120: HOT
- 70-119: MEDIUM
- 1-69: LOW
- <0: DISQUALIFIED
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple

from .intake_mapping import LeadInput, is_in_network_provider

logger = logging.getLogger(__name__)


# =============================================================================
# Scoring Constants
# =============================================================================

# Condition scores — multiple conditions ADD together
CONDITION_SCORES = {
    "insomnia": 10,
    "sleep_apnea": 15,
    "restless_leg": 8,
    "narcolepsy": 10,
    "other": 5,
}
MULTI_CONDITION_BONUS = 5
MAX_MULTI_CONDITION_BONUS = 10

# Treatment interest — what the lead wants to explore
SLEEP_TREATMENT_INTEREST_SCORES = {
    "cpap_bipap": 15,
    "inspire": 15,
    "therapy_cbt": 8,
    "sleep_study": 10,
    "medication": 8,
    "not_sure": 5,
}

# Insurance — never penalize
INSURANCE_IN_NETWORK_SCORE = 25
INSURANCE_OTHER_SCORE = 25
INSURANCE_NONE_SCORE = 10  # No insurance still gets points (they still need help)

# Duration — longer = more established need
DURATION_SCORES = {
    "more_than_12_months": 15,
    "6_to_12_months": 10,
    "less_than_6_months": 5,
}

# Treatment history scores
TREATMENT_CPAP_SCORE = 5
TREATMENT_MEDICATION_SCORE = 5
TREATMENT_SLEEP_STUDY_SCORE = 5
TREATMENT_THERAPY_SCORE = 5
TREATMENT_NO_PRIOR_SCORE = 10  # New patient = higher value
TREATMENT_COMPLEXITY_BONUS = 3

# Location — never disqualify, just bonus for in-area
LOCATION_IN_SERVICE_AREA_SCORE = 10
LOCATION_OUT_OF_SERVICE_AREA_SCORE = 0  # No penalty — they might still become patients

# Urgency — most impactful factor
URGENCY_SCORES = {
    "asap": 50,
    "within_30_days": 40,
    "exploring": 15,
}

UNDER_18_PENALTY = 0  # Don't disqualify minors — route them appropriately
REFERRAL_BONUS = 20

# Thresholds — more leads score HOT/MEDIUM
HOT_THRESHOLD = 80
MEDIUM_THRESHOLD = 40
DISQUALIFIED_THRESHOLD = -999  # Never disqualify from scoring alone


# =============================================================================
# Score Breakdown Dataclass
# =============================================================================

@dataclass
class ScoreBreakdown:
    condition_score: int = 0
    therapy_interest_score: int = 0
    severity_score: int = 0
    insurance_score: int = 0
    duration_score: int = 0
    treatment_score: int = 0
    location_score: int = 0
    urgency_score: int = 0
    age_score: int = 0
    referral_bonus: int = 0

    # Severity fields (kept for schema compatibility, always None for sleep)
    depression_severity_score: Optional[int] = None
    depression_severity_level: Optional[str] = None
    anxiety_severity_score: Optional[int] = None
    anxiety_severity_level: Optional[str] = None
    ocd_severity_level: Optional[str] = None
    ptsd_severity_level: Optional[str] = None

    lead_score: int = 0
    priority: str = "low"
    in_service_area: bool = False
    is_under_18: bool = False

    def to_dict(self) -> dict:
        return {
            "condition_score": self.condition_score,
            "therapy_interest_score": self.therapy_interest_score,
            "severity_score": self.severity_score,
            "insurance_score": self.insurance_score,
            "duration_score": self.duration_score,
            "treatment_score": self.treatment_score,
            "location_score": self.location_score,
            "urgency_score": self.urgency_score,
            "age_score": self.age_score,
            "referral_bonus": self.referral_bonus,
            "lead_score": self.lead_score,
            "priority": self.priority,
            "in_service_area": self.in_service_area,
            "is_under_18": self.is_under_18,
        }


# =============================================================================
# Service Area Check
# =============================================================================

def is_in_service_area(zip_code: str) -> bool:
    if not zip_code or len(zip_code) < 2:
        return False
    prefix = zip_code[:2]
    return prefix in ("85", "86")


def calculate_age(date_of_birth: Optional[date]) -> Optional[int]:
    if date_of_birth is None:
        return None
    today = date.today()
    age = today.year - date_of_birth.year
    if (today.month, today.day) < (date_of_birth.month, date_of_birth.day):
        age -= 1
    return age


# =============================================================================
# Main Scoring Function
# =============================================================================

def calculate_lead_score(lead_input: LeadInput, referred_by_provider: bool = False) -> ScoreBreakdown:
    """Calculate complete lead score from LeadInput for sleep clinic."""
    breakdown = ScoreBreakdown()

    # CONDITION SCORE (multi-condition: max of selected)
    condition_points = []
    for condition in lead_input.conditions:
        points = CONDITION_SCORES.get(condition, 0)
        condition_points.append(points)
    base_condition_score = max(condition_points) if condition_points else 0
    extra_conditions = max(0, len(set(lead_input.conditions)) - 1)
    breakdown.condition_score = base_condition_score + min(
        extra_conditions * MULTI_CONDITION_BONUS,
        MAX_MULTI_CONDITION_BONUS,
    )

    # SLEEP TREATMENT INTEREST SCORE
    breakdown.therapy_interest_score = SLEEP_TREATMENT_INTEREST_SCORES.get(
        lead_input.sleep_treatment_interest, 0
    )

    # SEVERITY SCORE (not applicable for sleep clinic - kept at 0)
    breakdown.severity_score = 0

    # INSURANCE SCORE
    if lead_input.has_insurance:
        provider = lead_input.insurance_provider
        if lead_input.other_insurance_provider:
            breakdown.insurance_score = INSURANCE_OTHER_SCORE
        elif is_in_network_provider(provider):
            breakdown.insurance_score = INSURANCE_IN_NETWORK_SCORE
        else:
            breakdown.insurance_score = INSURANCE_OTHER_SCORE
    else:
        breakdown.insurance_score = INSURANCE_NONE_SCORE

    # SYMPTOM DURATION SCORE
    breakdown.duration_score = DURATION_SCORES.get(lead_input.symptom_duration, 0)

    # PRIOR TREATMENT SCORE
    has_cpap = "cpap_bipap" in lead_input.prior_treatments
    has_med = "medication" in lead_input.prior_treatments
    has_study = "sleep_study" in lead_input.prior_treatments
    has_therapy = "therapy_cbt" in lead_input.prior_treatments
    has_none = "none" in lead_input.prior_treatments

    treatment_score = 0
    if has_cpap:
        treatment_score += TREATMENT_CPAP_SCORE
    if has_med:
        treatment_score += TREATMENT_MEDICATION_SCORE
    if has_study:
        treatment_score += TREATMENT_SLEEP_STUDY_SCORE
    if has_therapy:
        treatment_score += TREATMENT_THERAPY_SCORE
    if has_none:
        treatment_score += TREATMENT_NO_PRIOR_SCORE
    tried_count = sum((has_cpap, has_med, has_study, has_therapy))
    if tried_count >= 2:
        treatment_score += TREATMENT_COMPLEXITY_BONUS
    breakdown.treatment_score = treatment_score

    # SERVICE AREA SCORE
    breakdown.in_service_area = is_in_service_area(lead_input.zip_code)
    if breakdown.in_service_area:
        breakdown.location_score = LOCATION_IN_SERVICE_AREA_SCORE
    else:
        breakdown.location_score = LOCATION_OUT_OF_SERVICE_AREA_SCORE

    # URGENCY SCORE
    breakdown.urgency_score = URGENCY_SCORES.get(lead_input.urgency, 0)

    # AGE DISQUALIFICATION
    age = calculate_age(lead_input.date_of_birth)
    if age is not None and age < 18:
        breakdown.is_under_18 = True
        breakdown.age_score = UNDER_18_PENALTY

    # REFERRAL BONUS
    if referred_by_provider or lead_input.referred_by_provider:
        breakdown.referral_bonus = REFERRAL_BONUS

    # CALCULATE TOTAL
    breakdown.lead_score = (
        breakdown.condition_score +
        breakdown.therapy_interest_score +
        breakdown.severity_score +
        breakdown.insurance_score +
        breakdown.duration_score +
        breakdown.treatment_score +
        breakdown.location_score +
        breakdown.urgency_score +
        breakdown.age_score +
        breakdown.referral_bonus
    )

    # Priority assignment — NEVER disqualify from scoring
    if breakdown.lead_score >= HOT_THRESHOLD:
        breakdown.priority = "hot"
    elif breakdown.lead_score >= MEDIUM_THRESHOLD:
        breakdown.priority = "medium"
    else:
        breakdown.priority = "low"

    logger.info(
        f"Lead scoring complete: score={breakdown.lead_score}, priority={breakdown.priority}, "
        f"condition_score={breakdown.condition_score}, insurance_score={breakdown.insurance_score}, "
        f"location_score={breakdown.location_score}"
    )

    return breakdown


# =============================================================================
# Response Time and Confirmation Messages
# =============================================================================

def get_estimated_response_time(priority: str) -> str:
    response_times = {
        "hot": "Within 2 hours",
        "medium": "Within 24 hours",
        "low": "Within 48 hours",
        "disqualified": "We'll be in touch if we can help",
    }
    return response_times.get(priority, "Within 48 hours")


def get_confirmation_message(priority: str, in_service_area: bool) -> str:
    if not in_service_area:
        return (
            "Thank you for your interest! Unfortunately, we currently only serve "
            "patients in Arizona. We'll keep your information on file and reach out "
            "if we expand to your area."
        )
    messages = {
        "hot": (
            "Thank you! Based on your responses, our sleep specialists may be able to help. "
            "A care coordinator will call you within the next 2 hours to discuss your options."
        ),
        "medium": (
            "Thank you for reaching out! A member of our team will contact you within "
            "24 hours to learn more about how we can help with your sleep concerns."
        ),
        "low": (
            "Thank you for your interest in sleep treatment. One of our team members will "
            "reach out within 48 hours to discuss whether we might be right for you."
        ),
        "disqualified": (
            "Thank you for reaching out. We'll still have someone reach out to discuss "
            "alternative resources that might help with your sleep concerns."
        ),
    }
    return messages.get(priority, "Thank you! We'll be in touch soon.")


# =============================================================================
# Backward Compatibility Wrapper
# =============================================================================

def calculate_score_from_lead_data(
    conditions: List[str],
    sleep_treatment_interest: str = "",
    has_insurance: bool = False,
    insurance_provider: str = "",
    other_insurance_provider: str = "",
    symptom_duration: str = "",
    prior_treatments: List[str] = None,
    zip_code: str = "",
    urgency: str = "",
    date_of_birth: Optional[date] = None,
    referred_by_provider: bool = False,
) -> ScoreBreakdown:
    """Wrapper for scoring from individual params."""
    lead_input = LeadInput(
        conditions=conditions,
        sleep_treatment_interest=sleep_treatment_interest or "",
        has_insurance=has_insurance,
        insurance_provider=insurance_provider,
        other_insurance_provider=other_insurance_provider,
        symptom_duration=symptom_duration,
        prior_treatments=prior_treatments or [],
        zip_code=zip_code,
        urgency=urgency,
        date_of_birth=date_of_birth,
        referred_by_provider=referred_by_provider,
    )
    return calculate_lead_score(lead_input)
