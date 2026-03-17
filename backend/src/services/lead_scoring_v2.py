"""
Enhanced Lead Scoring Engine v2.

This module implements the complete lead scoring algorithm as specified,
with support for multi-condition intake, severity assessments, and
granular score breakdown.

SCORING RULES (EXACT AS SPECIFIED):
- Condition Score: max of selected conditions (depression/anxiety/ocd/ptsd = 50, other = 25)
- TMS Therapy Interest: Daily=5, Accelerated=15, Not Sure=0
- Severity Score: max across selected conditions based on PHQ-2/GAD-2/OCD/PTSD
- Insurance: in-network=+30, other/out-of-network=+20, no insurance=-20
- Duration: >12 months=+20, 6-12 months=+10, <6 months=0
- Treatment: meds=+20, therapy=+15, both=+10 bonus
- Location: AZ ZIP (85xxx/86xxx)=+25, out of area=-100
- Urgency: ASAP=+25, within_30_days=+10, exploring=0
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

# Condition Scores (Section 5.1)
CONDITION_SCORES = {
    "depression": 50,
    "anxiety": 50,
    "ocd": 50,
    "ptsd": 50,
    "other": 25,
}

# TMS Therapy Interest Scores (Section 5.2)
# Accelerated TMS scored at 15 to maintain hot lead generation rate.
TMS_INTEREST_SCORES = {
    "daily_tms": 5,
    "accelerated_tms": 15,
    "not_sure": 0,
}

# Depression Severity Points (Section 5.3 - PHQ-2)
# PHQ-2 score = phq2_interest + phq2_mood (0-6)
DEPRESSION_SEVERITY_POINTS = {
    "minimal": 5,    # 0-1
    "mild": 10,      # 2-3
    "moderate": 15,  # 4-5
    "severe": 20,    # 6
}

# Anxiety Severity Points (Section 5.3 - GAD-2)
# GAD-2 score = gad2_nervous + gad2_worry (0-6)
ANXIETY_SEVERITY_POINTS = {
    "minimal": 5,    # 0-1
    "mild": 10,      # 2-3
    "moderate": 15,  # 4-5
    "severe": 20,    # 6
}

# OCD Severity Points (Section 5.3)
# ocd_time_occupied: 1=<1h, 2=1-3h, 3=3-8h, 4=>8h
OCD_SEVERITY_POINTS = {
    "mild": 5,            # 1 (<1 hour)
    "moderate": 10,       # 2 (1-3 hours)
    "moderate_severe": 15, # 3 (3-8 hours)
    "severe": 20,         # 4 (>8 hours)
}

# PTSD Severity Points (Section 5.3)
# ptsd_intrusion: 0-4 scale
PTSD_SEVERITY_POINTS = {
    "minimal": 5,          # 0
    "mild": 10,            # 1
    "moderate": 12,        # 2
    "moderate_severe": 15, # 3
    "severe": 20,          # 4
}

# Insurance Scores (Section 5.4)
INSURANCE_IN_NETWORK_SCORE = 30
INSURANCE_OTHER_SCORE = 20  # out-of-network or "Other"
INSURANCE_NONE_SCORE = -20

# Duration Scores (Section 5.5)
DURATION_SCORES = {
    "more_than_12_months": 20,
    "6_to_12_months": 10,
    "less_than_6_months": 0,
}

# Treatment Scores (Section 5.6)
TREATMENT_MEDS_SCORE = 20
TREATMENT_THERAPY_SCORE = 15
TREATMENT_BOTH_BONUS = 10

# Location Scores (Section 5.7)
LOCATION_IN_SERVICE_AREA_SCORE = 25
LOCATION_OUT_OF_SERVICE_AREA_SCORE = -100

# Urgency Scores (Section 5.8)
URGENCY_SCORES = {
    "asap": 25,
    "within_30_days": 10,
    "exploring": 0,
}

# Disqualification (Section 5.9)
UNDER_18_PENALTY = -100

# Referral Bonus (optional enhancement)
REFERRAL_BONUS = 15

# Priority Thresholds (Section 5.10)
HOT_THRESHOLD = 120
MEDIUM_THRESHOLD = 70
DISQUALIFIED_THRESHOLD = 0


# =============================================================================
# Score Breakdown Dataclass
# =============================================================================

@dataclass
class ScoreBreakdown:
    """
    Detailed breakdown of lead score calculation.
    
    All score components are persisted to DB for transparency.
    """
    # Individual score components
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
    
    # Computed severity values
    depression_severity_score: Optional[int] = None
    depression_severity_level: Optional[str] = None
    anxiety_severity_score: Optional[int] = None
    anxiety_severity_level: Optional[str] = None
    ocd_severity_level: Optional[str] = None
    ptsd_severity_level: Optional[str] = None
    
    # Final values
    lead_score: int = 0
    priority: str = "low"
    in_service_area: bool = False
    is_under_18: bool = False
    
    def to_dict(self) -> dict:
        """Convert to dictionary for persistence."""
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
            "depression_severity_score": self.depression_severity_score,
            "depression_severity_level": self.depression_severity_level,
            "anxiety_severity_score": self.anxiety_severity_score,
            "anxiety_severity_level": self.anxiety_severity_level,
            "ocd_severity_level": self.ocd_severity_level,
            "ptsd_severity_level": self.ptsd_severity_level,
            "lead_score": self.lead_score,
            "priority": self.priority,
            "in_service_area": self.in_service_area,
            "is_under_18": self.is_under_18,
        }


# =============================================================================
# Severity Calculation Functions
# =============================================================================

def calculate_depression_severity(phq2_interest: Optional[int], phq2_mood: Optional[int]) -> Tuple[Optional[int], Optional[str], int]:
    """
    Calculate depression severity from PHQ-2 scores.
    
    Args:
        phq2_interest: PHQ-2 Q1 score (0-3)
        phq2_mood: PHQ-2 Q2 score (0-3)
        
    Returns:
        Tuple of (severity_score, severity_level, points)
    """
    if phq2_interest is None or phq2_mood is None:
        return None, None, 0
    
    # PHQ-2 total score (0-6)
    total = phq2_interest + phq2_mood
    
    # Determine severity level and points
    if total <= 1:
        level = "minimal"
    elif total <= 3:
        level = "mild"
    elif total <= 5:
        level = "moderate"
    else:
        level = "severe"
    
    points = DEPRESSION_SEVERITY_POINTS.get(level, 0)
    return total, level, points


def calculate_anxiety_severity(gad2_nervous: Optional[int], gad2_worry: Optional[int]) -> Tuple[Optional[int], Optional[str], int]:
    """
    Calculate anxiety severity from GAD-2 scores.
    
    Args:
        gad2_nervous: GAD-2 Q1 score (0-3)
        gad2_worry: GAD-2 Q2 score (0-3)
        
    Returns:
        Tuple of (severity_score, severity_level, points)
    """
    if gad2_nervous is None or gad2_worry is None:
        return None, None, 0
    
    # GAD-2 total score (0-6)
    total = gad2_nervous + gad2_worry
    
    # Determine severity level and points
    if total <= 1:
        level = "minimal"
    elif total <= 3:
        level = "mild"
    elif total <= 5:
        level = "moderate"
    else:
        level = "severe"
    
    points = ANXIETY_SEVERITY_POINTS.get(level, 0)
    return total, level, points


def calculate_ocd_severity(ocd_time_occupied: Optional[int]) -> Tuple[Optional[str], int]:
    """
    Calculate OCD severity from time occupied score.
    
    Args:
        ocd_time_occupied: Time occupied (1-4)
        
    Returns:
        Tuple of (severity_level, points)
    """
    if ocd_time_occupied is None:
        return None, 0
    
    # Map time occupied to severity
    severity_map = {
        1: "mild",
        2: "moderate",
        3: "moderate_severe",
        4: "severe",
    }
    
    level = severity_map.get(ocd_time_occupied)
    points = OCD_SEVERITY_POINTS.get(level, 0) if level else 0
    return level, points


def calculate_ptsd_severity(ptsd_intrusion: Optional[int]) -> Tuple[Optional[str], int]:
    """
    Calculate PTSD severity from intrusion frequency.
    
    Args:
        ptsd_intrusion: Intrusion frequency (0-4)
        
    Returns:
        Tuple of (severity_level, points)
    """
    if ptsd_intrusion is None:
        return None, 0
    
    # Map intrusion frequency to severity
    severity_map = {
        0: "minimal",
        1: "mild",
        2: "moderate",
        3: "moderate_severe",
        4: "severe",
    }
    
    level = severity_map.get(ptsd_intrusion)
    points = PTSD_SEVERITY_POINTS.get(level, 0) if level else 0
    return level, points


# =============================================================================
# Service Area Check
# =============================================================================

def is_in_service_area(zip_code: str) -> bool:
    """
    Check if ZIP code is in Arizona service area.
    
    Arizona ZIP codes start with 85 or 86.
    
    Args:
        zip_code: 5-digit ZIP code
        
    Returns:
        True if in service area
    """
    if not zip_code or len(zip_code) < 2:
        return False
    
    prefix = zip_code[:2]
    return prefix in ("85", "86")


# =============================================================================
# Age Calculation
# =============================================================================

def calculate_age(date_of_birth: Optional[date]) -> Optional[int]:
    """
    Calculate age from date of birth.
    
    Args:
        date_of_birth: Date of birth
        
    Returns:
        Age in years, or None if DOB not provided
    """
    if date_of_birth is None:
        return None
    
    today = date.today()
    age = today.year - date_of_birth.year
    
    # Adjust if birthday hasn't occurred yet this year
    if (today.month, today.day) < (date_of_birth.month, date_of_birth.day):
        age -= 1
    
    return age


# =============================================================================
# Main Scoring Function
# =============================================================================

def calculate_lead_score(lead_input: LeadInput, referred_by_provider: bool = False) -> ScoreBreakdown:
    """
    Calculate complete lead score from LeadInput.
    
    This is the single source of truth for lead scoring logic.
    All scoring rules are implemented exactly as specified.
    
    Args:
        lead_input: Canonical lead input data
        referred_by_provider: Whether this is a provider referral
        
    Returns:
        ScoreBreakdown with all score components and final values
    """
    breakdown = ScoreBreakdown()
    
    # =========================================================================
    # 5.1 CONDITION SCORE (multi-condition)
    # =========================================================================
    # Score = max of selected conditions (not sum, to avoid inflation)
    condition_points = []
    for condition in lead_input.conditions:
        points = CONDITION_SCORES.get(condition, 0)
        condition_points.append(points)
    
    breakdown.condition_score = max(condition_points) if condition_points else 0
    
    # =========================================================================
    # 5.2 TMS THERAPY INTEREST SCORE
    # =========================================================================
    breakdown.therapy_interest_score = TMS_INTEREST_SCORES.get(
        lead_input.tms_therapy_interest, 0
    )
    
    # =========================================================================
    # 5.3 SEVERITY SCORE (multi-condition)
    # =========================================================================
    # Compute severity points per selected condition, use max
    severity_points = []
    
    # Depression severity (if depression selected)
    if "depression" in lead_input.conditions:
        dep_score, dep_level, dep_points = calculate_depression_severity(
            lead_input.phq2_interest, lead_input.phq2_mood
        )
        breakdown.depression_severity_score = dep_score
        breakdown.depression_severity_level = dep_level
        if dep_points > 0:
            severity_points.append(dep_points)
    
    # Anxiety severity (if anxiety selected)
    if "anxiety" in lead_input.conditions:
        anx_score, anx_level, anx_points = calculate_anxiety_severity(
            lead_input.gad2_nervous, lead_input.gad2_worry
        )
        breakdown.anxiety_severity_score = anx_score
        breakdown.anxiety_severity_level = anx_level
        if anx_points > 0:
            severity_points.append(anx_points)
    
    # OCD severity (if ocd selected)
    if "ocd" in lead_input.conditions:
        ocd_level, ocd_points = calculate_ocd_severity(lead_input.ocd_time_occupied)
        breakdown.ocd_severity_level = ocd_level
        if ocd_points > 0:
            severity_points.append(ocd_points)
    
    # PTSD severity (if ptsd selected)
    if "ptsd" in lead_input.conditions:
        ptsd_level, ptsd_points = calculate_ptsd_severity(lead_input.ptsd_intrusion)
        breakdown.ptsd_severity_level = ptsd_level
        if ptsd_points > 0:
            severity_points.append(ptsd_points)
    
    # "other" condition: +0 severity
    breakdown.severity_score = max(severity_points) if severity_points else 0
    
    # =========================================================================
    # 5.4 INSURANCE SCORE
    # =========================================================================
    if lead_input.has_insurance:
        # Determine if in-network or out-of-network
        provider = lead_input.insurance_provider
        if lead_input.other_insurance_provider:
            # "Other" insurance provider -> treat as out-of-network
            breakdown.insurance_score = INSURANCE_OTHER_SCORE
        elif is_in_network_provider(provider):
            breakdown.insurance_score = INSURANCE_IN_NETWORK_SCORE
        else:
            breakdown.insurance_score = INSURANCE_OTHER_SCORE
    else:
        breakdown.insurance_score = INSURANCE_NONE_SCORE
    
    # =========================================================================
    # 5.5 SYMPTOM DURATION SCORE
    # =========================================================================
    breakdown.duration_score = DURATION_SCORES.get(lead_input.symptom_duration, 0)
    
    # =========================================================================
    # 5.6 PRIOR TREATMENT SCORE
    # =========================================================================
    has_meds = "antidepressants" in lead_input.prior_treatments
    has_therapy = "therapy_cbt" in lead_input.prior_treatments
    
    treatment_score = 0
    if has_meds:
        treatment_score += TREATMENT_MEDS_SCORE
    if has_therapy:
        treatment_score += TREATMENT_THERAPY_SCORE
    if has_meds and has_therapy:
        treatment_score += TREATMENT_BOTH_BONUS
    
    breakdown.treatment_score = treatment_score
    
    # =========================================================================
    # 5.7 SERVICE AREA SCORE (AZ ZIP)
    # =========================================================================
    breakdown.in_service_area = is_in_service_area(lead_input.zip_code)
    if breakdown.in_service_area:
        breakdown.location_score = LOCATION_IN_SERVICE_AREA_SCORE
    else:
        breakdown.location_score = LOCATION_OUT_OF_SERVICE_AREA_SCORE
    
    # =========================================================================
    # 5.8 URGENCY SCORE
    # =========================================================================
    breakdown.urgency_score = URGENCY_SCORES.get(lead_input.urgency, 0)
    
    # =========================================================================
    # 5.9 DISQUALIFICATION (Age < 18)
    # =========================================================================
    age = calculate_age(lead_input.date_of_birth)
    if age is not None and age < 18:
        breakdown.is_under_18 = True
        breakdown.age_score = UNDER_18_PENALTY
    
    # =========================================================================
    # REFERRAL BONUS (optional enhancement)
    # =========================================================================
    if referred_by_provider or lead_input.referred_by_provider:
        breakdown.referral_bonus = REFERRAL_BONUS
    
    # =========================================================================
    # 5.10 CALCULATE TOTAL SCORE AND PRIORITY
    # =========================================================================
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
    
    # Determine priority
    if breakdown.is_under_18:
        breakdown.lead_score = UNDER_18_PENALTY  # Override to disqualified
        breakdown.priority = "disqualified"
    elif breakdown.lead_score >= HOT_THRESHOLD:
        breakdown.priority = "hot"
    elif breakdown.lead_score >= MEDIUM_THRESHOLD:
        breakdown.priority = "medium"
    elif breakdown.lead_score >= DISQUALIFIED_THRESHOLD:
        breakdown.priority = "low"
    else:
        breakdown.priority = "disqualified"
    
    logger.info(
        f"Lead scoring complete: score={breakdown.lead_score}, priority={breakdown.priority}, "
        f"condition_score={breakdown.condition_score}, severity_score={breakdown.severity_score}, "
        f"insurance_score={breakdown.insurance_score}, location_score={breakdown.location_score}"
    )
    
    return breakdown


# =============================================================================
# Response Time and Confirmation Messages
# =============================================================================

def get_estimated_response_time(priority: str) -> str:
    """
    Get estimated response time based on priority.
    
    Args:
        priority: Lead priority (hot, medium, low, disqualified)
        
    Returns:
        Human-readable response time estimate
    """
    response_times = {
        "hot": "Within 2 hours",
        "medium": "Within 24 hours",
        "low": "Within 48 hours",
        "disqualified": "We'll be in touch if we can help",
    }
    return response_times.get(priority, "Within 48 hours")


def get_confirmation_message(priority: str, in_service_area: bool) -> str:
    """
    Get confirmation message based on lead priority and location.
    
    Args:
        priority: Lead priority
        in_service_area: Whether patient is in service area
        
    Returns:
        User-friendly confirmation message
    """
    if not in_service_area:
        return (
            "Thank you for your interest! Unfortunately, we currently only serve "
            "patients in Arizona. We'll keep your information on file and reach out "
            "if we expand to your area."
        )
    
    messages = {
        "hot": (
            "Thank you! Based on your responses, TMS therapy may be a great fit for you. "
            "A care coordinator will call you within the next 2 hours to discuss your options."
        ),
        "medium": (
            "Thank you for reaching out! A member of our team will contact you within "
            "24 hours to learn more about how we can help."
        ),
        "low": (
            "Thank you for your interest in TMS therapy. One of our team members will "
            "reach out within 48 hours to discuss whether TMS might be right for you."
        ),
        "disqualified": (
            "Thank you for reaching out. Based on the information provided, TMS may not "
            "be the best option for your situation. However, we'll still have someone "
            "reach out to discuss alternative resources that might help."
        ),
    }
    
    return messages.get(priority, "Thank you! We'll be in touch soon.")


# =============================================================================
# Backward Compatibility Wrapper
# =============================================================================

def calculate_score_from_lead_data(
    conditions: List[str],
    tms_therapy_interest: str,
    phq2_interest: Optional[int],
    phq2_mood: Optional[int],
    gad2_nervous: Optional[int],
    gad2_worry: Optional[int],
    ocd_time_occupied: Optional[int],
    ptsd_intrusion: Optional[int],
    has_insurance: bool,
    insurance_provider: str,
    other_insurance_provider: str,
    symptom_duration: str,
    prior_treatments: List[str],
    zip_code: str,
    urgency: str,
    date_of_birth: Optional[date] = None,
    referred_by_provider: bool = False,
) -> ScoreBreakdown:
    """
    Calculate lead score from individual parameters.
    
    This is a convenience wrapper for backward compatibility
    when you don't have a full LeadInput object.
    """
    lead_input = LeadInput(
        conditions=conditions,
        tms_therapy_interest=tms_therapy_interest,
        phq2_interest=phq2_interest,
        phq2_mood=phq2_mood,
        gad2_nervous=gad2_nervous,
        gad2_worry=gad2_worry,
        ocd_time_occupied=ocd_time_occupied,
        ptsd_intrusion=ptsd_intrusion,
        has_insurance=has_insurance,
        insurance_provider=insurance_provider,
        other_insurance_provider=other_insurance_provider,
        symptom_duration=symptom_duration,
        prior_treatments=prior_treatments,
        zip_code=zip_code,
        urgency=urgency,
        date_of_birth=date_of_birth,
        referred_by_provider=referred_by_provider,
    )
    
    return calculate_lead_score(lead_input)
