"""
Lead Pydantic schemas for request/response validation.

Defines DTOs for lead submission and retrieval.
Validates all inputs at API boundaries before processing.
"""

import re
from datetime import datetime, date
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field, EmailStr, field_validator, model_validator

from ..models.lead import (
    ConditionType,
    DurationType,
    TreatmentType,
    UrgencyType,
    PriorityType,
    LeadStatus,
    ContactMethodType,
    ContactOutcome,
)


# =============================================================================
# UTM Parameters Schema
# =============================================================================

class UTMParams(BaseModel):
    utm_source: Optional[str] = Field(default=None, max_length=255)
    utm_medium: Optional[str] = Field(default=None, max_length=255)
    utm_campaign: Optional[str] = Field(default=None, max_length=255)
    utm_term: Optional[str] = Field(default=None, max_length=255)
    utm_content: Optional[str] = Field(default=None, max_length=255)


# =============================================================================
# Lead Creation Schema (Widget Submission)
# =============================================================================

class LeadCreate(BaseModel):
    """Schema for creating a new lead from widget submission."""

    # Contact Information (PHI)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)
    email: EmailStr
    phone: str = Field(..., min_length=10, max_length=20)
    date_of_birth: Optional[date] = None

    @field_validator("date_of_birth")
    @classmethod
    def validate_date_of_birth(cls, v: Optional[date]) -> Optional[date]:
        if v is None:
            return v
        from datetime import date as date_cls
        today = date_cls.today()
        if v > today:
            raise ValueError("Date of birth cannot be in the future")
        age_years = (today - v).days / 365.25
        if age_years > 120:
            raise ValueError("Invalid date of birth")
        if age_years < 13:
            raise ValueError("Patient must be at least 13 years old")
        return v

    # Clinical Information
    condition: ConditionType
    condition_other: Optional[str] = Field(default=None, max_length=500)
    conditions: Optional[List[ConditionType]] = None
    other_condition_text: Optional[str] = Field(default=None, max_length=500)

    # Sleep Treatment Interest
    sleep_treatment_interest: Optional[str] = Field(default=None, max_length=100)

    # Preferred contact method
    preferred_contact_method: Optional[str] = Field(default=None, max_length=20)

    symptom_duration: DurationType
    prior_treatments: List[TreatmentType] = Field(default=[])

    # Insurance
    has_insurance: bool
    insurance_provider: Optional[str] = Field(default=None, max_length=255)
    other_insurance_provider: Optional[str] = Field(default=None, max_length=255)

    # Location
    zip_code: str = Field(..., min_length=5, max_length=10)

    # Urgency & Consent
    urgency: UrgencyType
    hipaa_consent: bool
    sms_consent: bool = False

    # UTM Tracking
    utm_params: Optional[UTMParams] = None

    # Referral
    is_referral: Optional[bool] = None
    referring_provider_name: Optional[str] = Field(default=None, max_length=255)
    referring_provider_specialty: Optional[str] = Field(default=None, max_length=255)
    referring_clinic: Optional[str] = Field(default=None, max_length=255)
    referring_provider_email: Optional[str] = Field(default=None, max_length=255)

    # Metadata
    referrer_url: Optional[str] = Field(default=None, max_length=2000)
    submission_id: Optional[str] = Field(default=None, max_length=128)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        has_plus = v.strip().startswith('+')
        cleaned = re.sub(r"[\s\-\(\)\.]", "", v)
        digits_only = re.sub(r"[^\d]", "", cleaned)
        if len(digits_only) < 7:
            raise ValueError("Phone number must be at least 7 digits")
        if len(digits_only) > 15:
            raise ValueError("Phone number too long (max 15 digits)")
        if has_plus:
            return f"+{digits_only}"
        return digits_only

    @field_validator("zip_code")
    @classmethod
    def validate_zip_code(cls, v: str) -> str:
        cleaned = v.replace(" ", "").replace("-", "")
        if not cleaned.isdigit():
            raise ValueError("ZIP code must contain only digits")
        if len(cleaned) not in (5, 9):
            raise ValueError("ZIP code must be 5 or 9 digits")
        return cleaned[:5]

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = " ".join(v.split())
        DANGEROUS_CHARS = set('<>;:"`!@#$%^&*()+=[]{}|\\?/~0123456789')
        bad_chars = [c for c in v if c in DANGEROUS_CHARS]
        if bad_chars:
            raise ValueError("Name contains invalid characters")
        if len(v.replace(" ", "")) < 1:
            raise ValueError("Name cannot be empty")
        return v

    @model_validator(mode="after")
    def validate_conditional_fields(self) -> "LeadCreate":
        has_other_text = self.condition_other or self.other_condition_text
        has_other_condition = (
            self.condition == ConditionType.OTHER or
            (self.conditions and ConditionType.OTHER in self.conditions)
        )
        if has_other_condition and not has_other_text:
            raise ValueError("condition_other or other_condition_text is required when condition is 'OTHER'")
        if not self.hipaa_consent:
            raise ValueError("HIPAA consent is required to submit")
        return self

    model_config = {
        "json_schema_extra": {
            "example": {
                "first_name": "John",
                "last_name": "Doe",
                "email": "john.doe@example.com",
                "phone": "(555) 123-4567",
                "condition": "INSOMNIA",
                "symptom_duration": "MORE_THAN_12_MONTHS",
                "prior_treatments": ["MEDICATION", "SLEEP_STUDY"],
                "has_insurance": True,
                "insurance_provider": "Blue Cross Blue Shield",
                "zip_code": "85001",
                "urgency": "ASAP",
                "hipaa_consent": True,
                "sms_consent": True,
            }
        }
    }


# =============================================================================
# Lead Update Schema
# =============================================================================

class LeadUpdate(BaseModel):
    first_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=20)
    condition: Optional[ConditionType] = None
    condition_other: Optional[str] = Field(default=None, max_length=500)
    symptom_duration: Optional[DurationType] = None
    prior_treatments: Optional[List[TreatmentType]] = None
    has_insurance: Optional[bool] = None
    insurance_provider: Optional[str] = Field(default=None, max_length=255)
    zip_code: Optional[str] = Field(default=None, max_length=10)
    urgency: Optional[UrgencyType] = None
    sleep_treatment_interest: Optional[str] = Field(default=None, max_length=100)
    notes: Optional[str] = Field(default=None, max_length=5000)
    lead_location: Optional[str] = Field(default=None, max_length=200)
    status: Optional[LeadStatus] = None
    priority: Optional[PriorityType] = None
    expected_updated_at: Optional[datetime] = None

    @field_validator('phone')
    @classmethod
    def normalize_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if v.startswith('+'):
            cleaned = '+' + ''.join(c for c in v[1:] if c.isdigit())
        else:
            cleaned = ''.join(c for c in v if c.isdigit())
            if len(cleaned) == 10:
                cleaned = '+1' + cleaned
            elif not cleaned.startswith('1') and len(cleaned) == 11:
                cleaned = '+' + cleaned
            else:
                cleaned = '+' + cleaned
        return cleaned


# =============================================================================
# Lead Response Schemas
# =============================================================================

class LeadResponse(BaseModel):
    id: UUID
    lead_number: Optional[str] = None
    first_name: str
    last_name: Optional[str] = None
    email: str
    phone: str
    condition: ConditionType
    condition_other: Optional[str] = None
    conditions: Optional[List[str]] = None
    other_condition_text: Optional[str] = None
    preferred_contact_method: Optional[str] = None
    symptom_duration: DurationType
    prior_treatments: List[TreatmentType]
    has_insurance: bool
    insurance_provider: Optional[str] = None
    zip_code: str
    in_service_area: bool
    lead_location: Optional[str] = None
    urgency: UrgencyType
    hipaa_consent: bool
    hipaa_consent_timestamp: Optional[datetime] = None
    privacy_consent_timestamp: Optional[datetime] = None
    sms_consent: bool
    sms_consent_timestamp: Optional[datetime] = None
    score: int
    priority: PriorityType
    sleep_treatment_interest: Optional[str] = None
    status: LeadStatus
    notes: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    contacted_at: Optional[datetime] = None
    scheduled_callback_at: Optional[datetime] = None
    scheduled_notes: Optional[str] = None
    contact_method: Optional[ContactMethodType] = None
    last_contact_attempt: Optional[datetime] = None
    contact_attempts: Optional[int] = 0
    next_follow_up_at: Optional[datetime] = None
    contact_outcome: ContactOutcome = ContactOutcome.NEW
    follow_up_reason: Optional[str] = None
    follow_up_date: Optional[datetime] = None
    last_updated_at: Optional[datetime] = None
    is_referral: bool = False
    referring_provider_id: Optional[UUID] = None
    referring_provider_name: Optional[str] = None

    model_config = {"from_attributes": True}


class LeadListResponse(BaseModel):
    id: UUID
    lead_number: Optional[str] = None
    first_name: str
    last_name: Optional[str] = None
    email: str
    phone: str
    condition: ConditionType
    conditions: Optional[List[str]] = None
    other_condition_text: Optional[str] = None
    preferred_contact_method: Optional[str] = None
    score: int
    priority: PriorityType
    status: LeadStatus
    in_service_area: bool
    created_at: datetime
    scheduled_callback_at: Optional[datetime] = None
    contact_outcome: ContactOutcome = ContactOutcome.NEW
    contact_attempts: Optional[int] = 0
    last_contact_attempt: Optional[datetime] = None
    is_referral: bool = False
    referring_provider_id: Optional[UUID] = None
    referring_provider_name: Optional[str] = None
    follow_up_reason: Optional[str] = None
    source: Optional[str] = None
    last_updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# =============================================================================
# Contact Outcome Schemas
# =============================================================================

class UpdateContactOutcomeRequest(BaseModel):
    contact_outcome: ContactOutcome
    notes: Optional[str] = Field(default=None, max_length=1000)
    next_follow_up_at: Optional[datetime] = None


class ScheduleCallbackRequest(BaseModel):
    scheduled_callback_at: datetime
    scheduled_notes: Optional[str] = Field(default=None, max_length=1000)
    contact_method: ContactMethodType = ContactMethodType.PHONE
    schedule_type: Optional[str] = "callback"


class LogContactAttemptRequest(BaseModel):
    contact_method: ContactMethodType
    was_successful: bool
    notes: Optional[str] = Field(default=None, max_length=1000)
    next_follow_up_at: Optional[datetime] = None


class ScheduledLeadResponse(BaseModel):
    id: UUID
    lead_number: Optional[str] = None
    first_name: str
    last_name: Optional[str] = None
    condition: ConditionType
    priority: PriorityType
    status: LeadStatus
    scheduled_callback_at: datetime
    scheduled_notes: Optional[str] = None
    contact_method: Optional[ContactMethodType] = None
    contact_attempts: Optional[int] = 0
    phone: Optional[str] = None

    model_config = {"from_attributes": True}


# =============================================================================
# Manual Lead Creation Schema
# =============================================================================

class ManualLeadCreate(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=20)
    condition: Optional[ConditionType] = None
    condition_other: Optional[str] = Field(default=None, max_length=500)
    symptom_duration: Optional[DurationType] = None
    prior_treatments: Optional[List[TreatmentType]] = None
    has_insurance: Optional[bool] = None
    insurance_provider: Optional[str] = Field(default=None, max_length=255)
    zip_code: Optional[str] = Field(default=None, max_length=10)
    urgency: Optional[UrgencyType] = None
    notes: Optional[str] = Field(default=None, max_length=5000)
    is_referral: Optional[bool] = None
    referring_provider_name: Optional[str] = Field(default=None, max_length=255)
    referring_provider_contact: Optional[str] = Field(default=None, max_length=255)
    referring_provider_specialty: Optional[str] = Field(default=None, max_length=255)

    @field_validator("phone")
    @classmethod
    def normalize_phone_manual(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v.strip() == "":
            return None
        has_plus = v.strip().startswith('+')
        cleaned = re.sub(r"[\s\-\(\)\.]", "", v)
        digits_only = re.sub(r"[^\d]", "", cleaned)
        if len(digits_only) < 7:
            raise ValueError("Phone number must be at least 7 digits")
        if len(digits_only) > 15:
            raise ValueError("Phone number too long (max 15 digits)")
        if has_plus:
            return f"+{digits_only}"
        if len(digits_only) == 10:
            return f"+1{digits_only}"
        return f"+{digits_only}"

    @field_validator("zip_code")
    @classmethod
    def validate_zip_manual(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v.strip() == "":
            return None
        cleaned = v.replace(" ", "").replace("-", "")
        if not cleaned.isdigit():
            raise ValueError("ZIP code must contain only digits")
        if len(cleaned) not in (5, 9):
            raise ValueError("ZIP code must be 5 or 9 digits")
        return cleaned[:5]


class LeadSubmitResponse(BaseModel):
    success: bool
    message: str
    lead_id: Optional[UUID] = None
    lead_number: Optional[str] = None
    priority: Optional[PriorityType] = None
    estimated_response_time: Optional[str] = None
