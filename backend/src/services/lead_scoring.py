"""
Lead scoring service.

Calculates lead priority based on clinical fit and readiness.
Implements the scoring algorithm defined in the specification.
"""

from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple

from ..models.lead import (
    ConditionType,
    DurationType,
    TreatmentType,
    UrgencyType,
    PriorityType,
)
from ..schemas.lead import LeadCreate
from ..core.security import is_in_service_area


# =============================================================================
# Scoring Constants
# =============================================================================

# Condition scores (TMS-treatable conditions)
CONDITION_SCORES = {
    ConditionType.DEPRESSION: 50,
    ConditionType.ANXIETY: 50,
    ConditionType.OCD: 50,
    ConditionType.PTSD: 50,
    ConditionType.OTHER: 0,  # Needs manual review
}

# Symptom duration scores
DURATION_SCORES = {
    DurationType.MORE_THAN_12_MONTHS: 20,
    DurationType.SIX_TO_TWELVE_MONTHS: 10,
    DurationType.LESS_THAN_6_MONTHS: 0,
}

# Prior treatment scores
TREATMENT_SCORES = {
    TreatmentType.ANTIDEPRESSANTS: 20,
    TreatmentType.THERAPY_CBT: 15,
    TreatmentType.BOTH: 35,  # Combined score + bonus
    TreatmentType.NONE: 0,
    TreatmentType.OTHER: 5,
}

# Bonus for trying both meds and therapy
BOTH_TREATMENTS_BONUS = 10

# Insurance scores
INSURANCE_YES_SCORE = 30
INSURANCE_NO_SCORE = -20  # Cash pay penalty

# Service area scores
IN_SERVICE_AREA_SCORE = 25
OUT_OF_SERVICE_AREA_SCORE = -100  # Disqualifying factor

# Urgency scores
URGENCY_SCORES = {
    UrgencyType.ASAP: 25,
    UrgencyType.WITHIN_30_DAYS: 10,
    UrgencyType.EXPLORING: 0,
}

# Disqualification threshold
UNDER_18_PENALTY = -100  # If we add age field later

# Priority thresholds
HOT_THRESHOLD = 120
MEDIUM_THRESHOLD = 70
DISQUALIFIED_THRESHOLD = 0


# =============================================================================
# Score Breakdown Dataclass
# =============================================================================

@dataclass
class ScoreBreakdown:
    """
    Detailed breakdown of how lead score was calculated.
    
    Useful for debugging and explaining scores to coordinators.
    """
    
    condition_score: int
    duration_score: int
    treatment_score: int
    treatment_bonus: int
    insurance_score: int
    service_area_score: int
    urgency_score: int
    age_score: int  # Added for under-18 disqualification
    total_score: int
    priority: PriorityType
    is_under_18: bool = False  # Flag for age-based disqualification
    
    def to_dict(self) -> dict:
        """Convert breakdown to dictionary."""
        return {
            "condition_score": self.condition_score,
            "duration_score": self.duration_score,
            "treatment_score": self.treatment_score,
            "treatment_bonus": self.treatment_bonus,
            "insurance_score": self.insurance_score,
            "service_area_score": self.service_area_score,
            "urgency_score": self.urgency_score,
            "age_score": self.age_score,
            "is_under_18": self.is_under_18,
            "total_score": self.total_score,
            "priority": self.priority.value,
        }


# =============================================================================
# Lead Scoring Service
# =============================================================================

class LeadScoringService:
    """
    Service for calculating lead scores and priorities.
    
    Implements the scoring algorithm defined in the specification:
    - +50: TMS-treatable condition (depression, anxiety, OCD, PTSD)
    - +20: Symptoms >12 months
    - +10: Symptoms 6-12 months
    - +20: Tried antidepressants
    - +15: Tried therapy/CBT
    - +10: Bonus for both meds + therapy
    - +30: Has insurance
    - -20: No insurance (cash pay)
    - +25: In service area (Arizona: ZIP 85xxx, 86xxx)
    - -100: Out of service area
    - +25: Urgency = ASAP
    - +10: Urgency = Within 30 days
    
    Priority thresholds:
    - ≥120 = HOT
    - 70-119 = MEDIUM
    - 0-69 = LOW
    - <0 = DISQUALIFIED
    """
    
    @staticmethod
    def calculate_condition_score(condition: ConditionType) -> int:
        """
        Calculate score based on condition.
        
        TMS-treatable conditions get +50 points.
        
        Args:
            condition: Selected condition type
            
        Returns:
            Score for condition
        """
        return CONDITION_SCORES.get(condition, 0)
    
    @staticmethod
    def calculate_duration_score(duration: DurationType) -> int:
        """
        Calculate score based on symptom duration.
        
        Longer duration indicates chronic condition suitable for TMS.
        
        Args:
            duration: Symptom duration range
            
        Returns:
            Score for duration
        """
        return DURATION_SCORES.get(duration, 0)
    
    @staticmethod
    def calculate_treatment_score(treatments: List[TreatmentType]) -> Tuple[int, int]:
        """
        Calculate score based on prior treatments.
        
        Patients who have tried other treatments are better TMS candidates.
        Bonus points if they've tried both medications and therapy.
        
        Args:
            treatments: List of prior treatments tried
            
        Returns:
            Tuple of (base_score, bonus_score)
        """
        if not treatments:
            return 0, 0
        
        # Check for BOTH enum value first
        if TreatmentType.BOTH in treatments:
            return TREATMENT_SCORES[TreatmentType.BOTH], 0
        
        base_score = 0
        has_meds = False
        has_therapy = False
        
        for treatment in treatments:
            if treatment == TreatmentType.ANTIDEPRESSANTS:
                base_score += TREATMENT_SCORES[TreatmentType.ANTIDEPRESSANTS]
                has_meds = True
            elif treatment == TreatmentType.THERAPY_CBT:
                base_score += TREATMENT_SCORES[TreatmentType.THERAPY_CBT]
                has_therapy = True
            elif treatment == TreatmentType.OTHER:
                base_score += TREATMENT_SCORES[TreatmentType.OTHER]
        
        # Bonus for trying both
        bonus = BOTH_TREATMENTS_BONUS if (has_meds and has_therapy) else 0
        
        return base_score, bonus
    
    @staticmethod
    def calculate_insurance_score(has_insurance: bool) -> int:
        """
        Calculate score based on insurance status.
        
        Insurance indicates better ability to afford treatment.
        
        Args:
            has_insurance: Whether patient has insurance
            
        Returns:
            Score for insurance status
        """
        return INSURANCE_YES_SCORE if has_insurance else INSURANCE_NO_SCORE
    
    @staticmethod
    def calculate_service_area_score(zip_code: str) -> Tuple[int, bool]:
        """
        Calculate score based on service area.
        
        Patients in Arizona service area get priority.
        Out of area is heavily penalized (essentially disqualifying).
        
        Args:
            zip_code: Patient ZIP code
            
        Returns:
            Tuple of (score, is_in_service_area)
        """
        in_area = is_in_service_area(zip_code)
        score = IN_SERVICE_AREA_SCORE if in_area else OUT_OF_SERVICE_AREA_SCORE
        return score, in_area
    
    @staticmethod
    def calculate_urgency_score(urgency: UrgencyType) -> int:
        """
        Calculate score based on urgency.
        
        Higher urgency indicates higher conversion likelihood.
        
        Args:
            urgency: Patient's urgency level
            
        Returns:
            Score for urgency
        """
        return URGENCY_SCORES.get(urgency, 0)
    
    @staticmethod
    def calculate_age_score(date_of_birth: Optional[date]) -> Tuple[int, bool]:
        """
        Calculate score based on age.
        
        TMS therapy requires patients to be 18+.
        Under-18 leads are disqualified with a -100 penalty.
        
        Args:
            date_of_birth: Patient's date of birth (optional)
            
        Returns:
            Tuple of (age_score, is_under_18)
        """
        if date_of_birth is None:
            # If no DOB provided, no penalty (will be verified at intake)
            return 0, False
        
        # Calculate age
        today = date.today()
        age = today.year - date_of_birth.year
        
        # Adjust if birthday hasn't occurred yet this year
        if (today.month, today.day) < (date_of_birth.month, date_of_birth.day):
            age -= 1
        
        # Under 18 disqualification
        if age < 18:
            return UNDER_18_PENALTY, True
        
        return 0, False
    
    @staticmethod
    def determine_priority(score: int) -> PriorityType:
        """
        Determine lead priority based on total score.
        
        Args:
            score: Total lead score
            
        Returns:
            Priority level (HOT, MEDIUM, LOW, or DISQUALIFIED)
        """
        if score >= HOT_THRESHOLD:
            return PriorityType.HOT
        elif score >= MEDIUM_THRESHOLD:
            return PriorityType.MEDIUM
        elif score >= DISQUALIFIED_THRESHOLD:
            return PriorityType.LOW
        else:
            return PriorityType.DISQUALIFIED
    
    @classmethod
    def calculate_score(
        cls,
        lead_data: LeadCreate
    ) -> Tuple[int, PriorityType, bool, ScoreBreakdown]:
        """
        Calculate total lead score and priority.
        
        Main entry point for lead scoring.
        
        Args:
            lead_data: Lead creation data from widget
            
        Returns:
            Tuple of (score, priority, in_service_area, breakdown)
        """
        # Calculate individual scores
        condition_score = cls.calculate_condition_score(lead_data.condition)
        duration_score = cls.calculate_duration_score(lead_data.symptom_duration)
        treatment_score, treatment_bonus = cls.calculate_treatment_score(
            lead_data.prior_treatments
        )
        insurance_score = cls.calculate_insurance_score(lead_data.has_insurance)
        service_area_score, in_service_area = cls.calculate_service_area_score(
            lead_data.zip_code
        )
        urgency_score = cls.calculate_urgency_score(lead_data.urgency)
        
        # Calculate age score (under-18 disqualification)
        # Get date_of_birth if present on lead_data
        date_of_birth = getattr(lead_data, 'date_of_birth', None)
        age_score, is_under_18 = cls.calculate_age_score(date_of_birth)
        
        # Calculate total (now includes age penalty if applicable)
        total_score = (
            condition_score +
            duration_score +
            treatment_score +
            treatment_bonus +
            insurance_score +
            service_area_score +
            urgency_score +
            age_score
        )
        
        # Determine priority
        priority = cls.determine_priority(total_score)
        
        # Create breakdown for transparency
        breakdown = ScoreBreakdown(
            condition_score=condition_score,
            duration_score=duration_score,
            treatment_score=treatment_score,
            treatment_bonus=treatment_bonus,
            insurance_score=insurance_score,
            service_area_score=service_area_score,
            urgency_score=urgency_score,
            age_score=age_score,
            total_score=total_score,
            priority=priority,
            is_under_18=is_under_18,
        )
        
        return total_score, priority, in_service_area, breakdown


# =============================================================================
# Convenience Function
# =============================================================================

def calculate_lead_score(
    lead_data: LeadCreate
) -> Tuple[int, PriorityType, bool, ScoreBreakdown]:
    """
    Calculate lead score (convenience wrapper).
    
    Args:
        lead_data: Lead creation data from widget
        
    Returns:
        Tuple of (score, priority, in_service_area, breakdown)
    """
    return LeadScoringService.calculate_score(lead_data)


# =============================================================================
# Response Time Estimation
# =============================================================================

def get_estimated_response_time(priority: PriorityType) -> str:
    """
    Get estimated response time based on priority.
    
    Used to set expectations for patients after submission.
    
    Args:
        priority: Calculated lead priority
        
    Returns:
        Human-readable response time estimate
    """
    response_times = {
        PriorityType.HOT: "Within 2 hours",
        PriorityType.MEDIUM: "Within 24 hours",
        PriorityType.LOW: "Within 48 hours",
        PriorityType.DISQUALIFIED: "We'll be in touch if we can help",
    }
    return response_times.get(priority, "Within 48 hours")


def get_confirmation_message(priority: PriorityType, in_service_area: bool) -> str:
    """
    Get confirmation message based on lead priority and location.
    
    Provides appropriate messaging for different lead types.
    
    Args:
        priority: Calculated lead priority
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
        PriorityType.HOT: (
            "Thank you! Based on your responses, TMS therapy may be a great fit for you. "
            "A care coordinator will call you within the next 2 hours to discuss your options."
        ),
        PriorityType.MEDIUM: (
            "Thank you for reaching out! A member of our team will contact you within "
            "24 hours to learn more about how we can help."
        ),
        PriorityType.LOW: (
            "Thank you for your interest in TMS therapy. One of our team members will "
            "reach out within 48 hours to discuss whether TMS might be right for you."
        ),
        PriorityType.DISQUALIFIED: (
            "Thank you for reaching out. Based on the information provided, TMS may not "
            "be the best option for your situation. However, we'll still have someone "
            "reach out to discuss alternative resources that might help."
        ),
    }
    
    return messages.get(priority, "Thank you! We'll be in touch soon.")
