"""
Lead scoring service for SleepReach.

Calculates lead priority based on clinical fit and readiness
for sleep disorder treatment at The Insomnia and Sleep Institute of Arizona.
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

TREATMENT_SCORES = {
    TreatmentType.CPAP_BIPAP: 20,
    TreatmentType.MEDICATION: 15,
    TreatmentType.SLEEP_STUDY: 10,
    TreatmentType.THERAPY_CBT: 15,
    TreatmentType.NONE: 0,
    TreatmentType.OTHER: 5,
}

BOTH_TREATMENTS_BONUS = 10

INSURANCE_YES_SCORE = 30
INSURANCE_NO_SCORE = -20

IN_SERVICE_AREA_SCORE = 25
OUT_OF_SERVICE_AREA_SCORE = -100

URGENCY_SCORES = {
    UrgencyType.ASAP: 25,
    UrgencyType.WITHIN_30_DAYS: 10,
    UrgencyType.EXPLORING: 0,
}

UNDER_18_PENALTY = -100

HOT_THRESHOLD = 120
MEDIUM_THRESHOLD = 70
DISQUALIFIED_THRESHOLD = 0


@dataclass
class ScoreBreakdown:
    condition_score: int
    duration_score: int
    treatment_score: int
    treatment_bonus: int
    insurance_score: int
    service_area_score: int
    urgency_score: int
    age_score: int
    total_score: int
    priority: PriorityType
    is_under_18: bool = False

    def to_dict(self) -> dict:
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


class LeadScoringService:
    @staticmethod
    def calculate_condition_score(condition: ConditionType) -> int:
        return CONDITION_SCORES.get(condition, 0)

    @staticmethod
    def calculate_duration_score(duration: DurationType) -> int:
        return DURATION_SCORES.get(duration, 0)

    @staticmethod
    def calculate_treatment_score(treatments: List[TreatmentType]) -> Tuple[int, int]:
        if not treatments:
            return 0, 0

        base_score = 0
        has_device = False  # CPAP/BiPAP
        has_med = False

        for treatment in treatments:
            score = TREATMENT_SCORES.get(treatment, 0)
            base_score += score
            if treatment == TreatmentType.CPAP_BIPAP:
                has_device = True
            elif treatment == TreatmentType.MEDICATION:
                has_med = True

        bonus = BOTH_TREATMENTS_BONUS if (has_device and has_med) else 0
        return base_score, bonus

    @staticmethod
    def calculate_insurance_score(has_insurance: bool) -> int:
        return INSURANCE_YES_SCORE if has_insurance else INSURANCE_NO_SCORE

    @staticmethod
    def calculate_service_area_score(zip_code: str) -> Tuple[int, bool]:
        in_area = is_in_service_area(zip_code)
        score = IN_SERVICE_AREA_SCORE if in_area else OUT_OF_SERVICE_AREA_SCORE
        return score, in_area

    @staticmethod
    def calculate_urgency_score(urgency: UrgencyType) -> int:
        return URGENCY_SCORES.get(urgency, 0)

    @staticmethod
    def calculate_age_score(date_of_birth: Optional[date]) -> Tuple[int, bool]:
        if date_of_birth is None:
            return 0, False
        today = date.today()
        age = today.year - date_of_birth.year
        if (today.month, today.day) < (date_of_birth.month, date_of_birth.day):
            age -= 1
        if age < 18:
            return UNDER_18_PENALTY, True
        return 0, False

    @staticmethod
    def determine_priority(score: int) -> PriorityType:
        if score >= HOT_THRESHOLD:
            return PriorityType.HOT
        elif score >= MEDIUM_THRESHOLD:
            return PriorityType.MEDIUM
        elif score >= DISQUALIFIED_THRESHOLD:
            return PriorityType.LOW
        else:
            return PriorityType.DISQUALIFIED

    @classmethod
    def calculate_score(cls, lead_data: LeadCreate) -> Tuple[int, PriorityType, bool, ScoreBreakdown]:
        condition_score = cls.calculate_condition_score(lead_data.condition)
        duration_score = cls.calculate_duration_score(lead_data.symptom_duration)
        treatment_score, treatment_bonus = cls.calculate_treatment_score(lead_data.prior_treatments)
        insurance_score = cls.calculate_insurance_score(lead_data.has_insurance)
        service_area_score, in_service_area = cls.calculate_service_area_score(lead_data.zip_code)
        urgency_score = cls.calculate_urgency_score(lead_data.urgency)
        date_of_birth = getattr(lead_data, 'date_of_birth', None)
        age_score, is_under_18 = cls.calculate_age_score(date_of_birth)

        total_score = (
            condition_score + duration_score + treatment_score +
            treatment_bonus + insurance_score + service_area_score +
            urgency_score + age_score
        )
        priority = cls.determine_priority(total_score)

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


def calculate_lead_score(lead_data: LeadCreate) -> Tuple[int, PriorityType, bool, ScoreBreakdown]:
    return LeadScoringService.calculate_score(lead_data)


def get_estimated_response_time(priority: PriorityType) -> str:
    response_times = {
        PriorityType.HOT: "Within 2 hours",
        PriorityType.MEDIUM: "Within 24 hours",
        PriorityType.LOW: "Within 48 hours",
        PriorityType.DISQUALIFIED: "We'll be in touch if we can help",
    }
    return response_times.get(priority, "Within 48 hours")


def get_confirmation_message(priority: PriorityType, in_service_area: bool) -> str:
    if not in_service_area:
        return (
            "Thank you for your interest! Unfortunately, we currently only serve "
            "patients in Arizona. We'll keep your information on file and reach out "
            "if we expand to your area."
        )
    messages = {
        PriorityType.HOT: (
            "Thank you! Based on your responses, our sleep specialists may be able to help. "
            "A care coordinator will call you within the next 2 hours to discuss your options."
        ),
        PriorityType.MEDIUM: (
            "Thank you for reaching out! A member of our team will contact you within "
            "24 hours to learn more about how we can help with your sleep concerns."
        ),
        PriorityType.LOW: (
            "Thank you for your interest in sleep treatment. One of our team members will "
            "reach out within 48 hours to discuss whether we might be right for you."
        ),
        PriorityType.DISQUALIFIED: (
            "Thank you for reaching out. We'll still have someone reach out to discuss "
            "alternative resources that might help with your sleep concerns."
        ),
    }
    return messages.get(priority, "Thank you! We'll be in touch soon.")
