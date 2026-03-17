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
    """
    UTM tracking parameters from widget embedding.
    
    Captures marketing attribution data from URL parameters.
    """
    
    utm_source: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Traffic source (e.g., google, facebook)"
    )
    utm_medium: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Marketing medium (e.g., cpc, email)"
    )
    utm_campaign: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Campaign name"
    )
    utm_term: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Paid search keywords"
    )
    utm_content: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Content identifier for A/B testing"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "utm_source": "google",
                "utm_medium": "cpc",
                "utm_campaign": "tms_awareness_2024",
                "utm_term": "depression treatment",
                "utm_content": "ad_variant_a"
            }
        }
    }


# =============================================================================
# Lead Creation Schema (Widget Submission)
# =============================================================================

class LeadCreate(BaseModel):
    """
    Schema for creating a new lead from widget submission.
    
    Validates all intake form fields before processing.
    PHI fields will be encrypted before storage.
    """
    
    # Contact Information (PHI)
    first_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Patient first name (required)"
    )
    last_name: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Patient last name (optional)"
    )
    email: EmailStr = Field(
        ...,
        description="Patient email address (required)"
    )
    phone: str = Field(
        ...,
        min_length=10,
        max_length=20,
        description="Patient phone number (required)"
    )
    
    # Date of Birth (for age verification - TMS requires 18+)
    date_of_birth: Optional[date] = Field(
        default=None,
        description="Patient date of birth (optional, used for age verification)"
    )

    @field_validator("date_of_birth")
    @classmethod
    def validate_date_of_birth(cls, v: Optional[date]) -> Optional[date]:
        """
        Validate date of birth is not in the future and patient is at least 13 years old.

        TMS therapy is indicated for adults (18+), but we set a conservative
        lower bound of 13 to avoid hard-rejecting edge cases where the clinic
        may accept younger patients with guardian consent.  The clinical team
        reviews all under-18 leads.
        """
        if v is None:
            return v

        from datetime import date as date_cls
        today = date_cls.today()

        # Reject future dates
        if v > today:
            raise ValueError("Date of birth cannot be in the future")

        # Reject clearly impossible ages (>120 years)
        age_years = (today - v).days / 365.25
        if age_years > 120:
            raise ValueError("Invalid date of birth — age exceeds 120 years")

        # Soft guard: log and allow under-18 (clinical team reviews)
        # Hard minimum: 13 years (widget form prevents younger)
        if age_years < 13:
            raise ValueError("Patient must be at least 13 years old to submit this form")

        return v
    
    # Clinical Information
    condition: ConditionType = Field(
        ...,
        description="Primary mental health condition"
    )
    condition_other: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Description if condition is 'OTHER'"
    )
    
    # Multi-condition support (NEW)
    conditions: Optional[List[ConditionType]] = Field(
        default=None,
        description="List of conditions (multi-select)"
    )
    other_condition_text: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Description for 'OTHER' condition"
    )
    
    # Severity Assessments (NEW - conditional based on conditions)
    # PHQ-2 for Depression (0-3 scale each)
    phq2_interest: Optional[int] = Field(
        default=None,
        ge=0, le=3,
        description="PHQ-2: Little interest or pleasure (0-3)"
    )
    phq2_mood: Optional[int] = Field(
        default=None,
        ge=0, le=3,
        description="PHQ-2: Feeling down, depressed, hopeless (0-3)"
    )
    
    # GAD-2 for Anxiety (0-3 scale each)
    gad2_nervous: Optional[int] = Field(
        default=None,
        ge=0, le=3,
        description="GAD-2: Feeling nervous, anxious (0-3)"
    )
    gad2_worry: Optional[int] = Field(
        default=None,
        ge=0, le=3,
        description="GAD-2: Not being able to stop worrying (0-3)"
    )
    
    # OCD severity (1-4 scale)
    ocd_time_occupied: Optional[int] = Field(
        default=None,
        ge=1, le=4,
        description="OCD: Time occupied by obsessions (1-4)"
    )
    
    # PTSD severity (0-4 scale)
    ptsd_intrusion: Optional[int] = Field(
        default=None,
        ge=0, le=4,
        description="PTSD: Intrusion symptoms (0-4)"
    )
    
    # TMS therapy interest (NEW)
    tms_therapy_interest: Optional[str] = Field(
        default=None,
        max_length=50,
        description="TMS therapy interest (daily_tms, accelerated_tms, not_sure)"
    )
    
    # Preferred contact method (NEW)
    preferred_contact_method: Optional[str] = Field(
        default=None,
        max_length=20,
        description="Preferred contact method (phone_call, text, email, any)"
    )
    
    symptom_duration: DurationType = Field(
        ...,
        description="How long symptoms have been present"
    )
    prior_treatments: List[TreatmentType] = Field(
        default=[],
        description="List of prior treatments tried"
    )
    
    # Insurance Information
    has_insurance: bool = Field(
        ...,
        description="Whether patient has health insurance"
    )
    insurance_provider: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Insurance provider name if has_insurance=true"
    )
    other_insurance_provider: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Other insurance provider name"
    )
    
    # Location
    zip_code: str = Field(
        ...,
        min_length=5,
        max_length=10,
        description="Patient ZIP code for service area check"
    )
    
    # Urgency & Consent
    urgency: UrgencyType = Field(
        ...,
        description="How urgently patient wants treatment"
    )
    hipaa_consent: bool = Field(
        ...,
        description="Patient acknowledged HIPAA consent"
    )
    sms_consent: bool = Field(
        default=False,
        description="Patient consents to SMS communication"
    )
    
    # UTM Tracking (optional)
    utm_params: Optional[UTMParams] = Field(
        default=None,
        description="Marketing attribution parameters"
    )
    
    # Referral Information (NEW - matches Jotform)
    is_referral: Optional[bool] = Field(
        default=None,
        description="Whether patient was referred by a healthcare provider"
    )
    referring_provider_name: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Name of referring healthcare provider"
    )
    referring_provider_specialty: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Specialty of referring healthcare provider (e.g., Psychiatrist, Psychologist)"
    )
    referring_clinic: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Clinic/practice name of referring provider"
    )
    referring_provider_email: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Email of referring healthcare provider"
    )
    
    # Metadata (set by backend)
    referrer_url: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Page URL where widget was embedded"
    )
    
    # Idempotency key — generated by frontend widget on load (UUID v4).
    # Backend uses this to deduplicate double-taps and network retries.
    submission_id: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Client-generated UUID for idempotency (24h TTL)"
    )
    
    # ==========================================================================
    # Validators
    # ==========================================================================
    
    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """
        Validate and normalize phone number.
        
        Accepts international phone numbers from any country.
        Supports formats like:
        - +1 (555) 123-4567 (US)
        - +44 20 7946 0958 (UK)
        - +254 712 345 678 (Kenya)
        - +91 98765 43210 (India)
        - +86 138 0013 8000 (China)
        
        Normalizes to E.164 format (digits with optional leading +).
        """
        # Remove common formatting characters but preserve leading +
        has_plus = v.strip().startswith('+')
        cleaned = re.sub(r"[\s\-\(\)\.]", "", v)
        
        # Extract just digits
        digits_only = re.sub(r"[^\d]", "", cleaned)
        
        # Validate minimum length (shortest valid numbers are ~7 digits)
        if len(digits_only) < 7:
            raise ValueError("Phone number must be at least 7 digits")
        
        # Maximum E.164 is 15 digits
        if len(digits_only) > 15:
            raise ValueError("Phone number too long (max 15 digits)")
        
        # Return normalized format with + if it had one
        if has_plus:
            return f"+{digits_only}"
        return digits_only
    
    @field_validator("zip_code")
    @classmethod
    def validate_zip_code(cls, v: str) -> str:
        """
        Validate US ZIP code format.
        
        Accepts 5-digit or 9-digit (ZIP+4) formats.
        """
        # Remove spaces and dashes
        cleaned = v.replace(" ", "").replace("-", "")
        
        if not cleaned.isdigit():
            raise ValueError("ZIP code must contain only digits")
        
        if len(cleaned) not in (5, 9):
            raise ValueError("ZIP code must be 5 or 9 digits")
        
        return cleaned[:5]  # Store only first 5 digits
    
    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        """
        Validate and sanitize name fields.

        Supports all human languages — ASCII and Unicode (accented letters,
        Cyrillic, CJK, etc.) are allowed.  Rejects digits and characters
        commonly used in injection attacks.

        Examples of names that MUST pass:
          María, José, Renée, Nguyễn, Björn, Müller, Ångström, Andrés
        """
        if v is None:
            return v

        # Strip and normalize whitespace
        v = " ".join(v.split())

        # Reject characters that have no place in a human name and are also
        # associated with injection attacks.  We reject rather than allowlist so
        # that every human script (Latin, Arabic, CJK, Cyrillic, …) is accepted.
        DANGEROUS_CHARS = set('<>;:"\`!@#$%^&*()+=[]{}|\\?/~0123456789')
        bad_chars = [c for c in v if c in DANGEROUS_CHARS]
        if bad_chars:
            raise ValueError("Name contains invalid characters")

        # Minimum length check after whitespace normalisation
        if len(v.replace(" ", "")) < 1:
            raise ValueError("Name cannot be empty")

        return v
    
    @model_validator(mode="after")
    def validate_conditional_fields(self) -> "LeadCreate":
        """
        Validate fields that depend on other field values.
        """
        # condition_other OR other_condition_text required if condition is OTHER
        # Accept either field for backward compatibility
        has_other_text = self.condition_other or self.other_condition_text
        
        # Check if OTHER is in conditions array or is the primary condition
        has_other_condition = (
            self.condition == ConditionType.OTHER or 
            (self.conditions and ConditionType.OTHER in self.conditions)
        )
        
        if has_other_condition and not has_other_text:
            raise ValueError("condition_other or other_condition_text is required when condition is 'OTHER'")
        
        # HIPAA consent must be given
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
                "condition": "DEPRESSION",
                "symptom_duration": "MORE_THAN_12_MONTHS",
                "prior_treatments": ["ANTIDEPRESSANTS", "THERAPY_CBT"],
                "has_insurance": True,
                "insurance_provider": "Blue Cross Blue Shield",
                "zip_code": "85001",
                "urgency": "ASAP",
                "hipaa_consent": True,
                "sms_consent": True,
                "utm_params": {
                    "utm_source": "google",
                    "utm_medium": "cpc"
                }
            }
        }
    }


# =============================================================================
# Lead Update Schema
# =============================================================================

class LeadUpdate(BaseModel):
    """
    Schema for updating an existing lead.
    
    All fields are optional - only provided fields will be updated.
    PHI fields will be re-encrypted if modified.
    """
    
    # Contact Information (PHI) - optional updates
    first_name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Patient first name"
    )
    last_name: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Patient last name"
    )
    email: Optional[EmailStr] = Field(
        default=None,
        description="Patient email address"
    )
    phone: Optional[str] = Field(
        default=None,
        max_length=20,
        description="Patient phone number"
    )
    
    # Clinical Information
    condition: Optional[ConditionType] = Field(
        default=None,
        description="Primary mental health condition"
    )
    condition_other: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Description if condition is 'OTHER'"
    )
    symptom_duration: Optional[DurationType] = Field(
        default=None,
        description="How long symptoms have been present"
    )
    prior_treatments: Optional[List[TreatmentType]] = Field(
        default=None,
        description="List of prior treatments tried"
    )
    
    # Insurance Information
    has_insurance: Optional[bool] = Field(
        default=None,
        description="Whether patient has health insurance"
    )
    insurance_provider: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Insurance provider name"
    )
    
    # Location
    zip_code: Optional[str] = Field(
        default=None,
        max_length=10,
        description="Patient ZIP code"
    )
    
    # Urgency
    urgency: Optional[UrgencyType] = Field(
        default=None,
        description="How urgently patient needs treatment"
    )
    
    # TMS Therapy Interest
    tms_therapy_interest: Optional[str] = Field(
        default=None,
        max_length=50,
        description="TMS therapy interest (daily_tms, accelerated_tms, not_sure)"
    )
    
    # Notes
    notes: Optional[str] = Field(
        default=None,
        max_length=5000,
        description="Coordinator notes about the lead"
    )
    
    # Status and Priority
    status: Optional[LeadStatus] = Field(
        default=None,
        description="Current lead status"
    )
    priority: Optional[PriorityType] = Field(
        default=None,
        description="Lead priority level"
    )

    # Optimistic locking — client sends back the updated_at it last received.
    # If the lead has been modified by another coordinator since then, the
    # server rejects the update with HTTP 409 so no silent overwrite occurs.
    # Omit this field (or send None) to skip the check (legacy callers).
    expected_updated_at: Optional[datetime] = Field(
        default=None,
        description="updated_at timestamp from the client's last fetch. "
                    "If provided and it doesn't match the current DB value, "
                    "the update is rejected with HTTP 409 Conflict."
    )

    @field_validator('phone')
    @classmethod
    def normalize_phone(cls, v: Optional[str]) -> Optional[str]:
        """Normalize phone to E.164 format if provided."""
        if v is None:
            return None
        # Remove common formatting characters but preserve leading +
        if v.startswith('+'):
            cleaned = '+' + ''.join(c for c in v[1:] if c.isdigit())
        else:
            cleaned = ''.join(c for c in v if c.isdigit())
            # Add US country code if not present
            if len(cleaned) == 10:
                cleaned = '+1' + cleaned
            elif not cleaned.startswith('1') and len(cleaned) == 11:
                cleaned = '+' + cleaned
            else:
                cleaned = '+' + cleaned
        return cleaned

    model_config = {
        "json_schema_extra": {
            "example": {
                "first_name": "Jane",
                "email": "jane.doe@example.com",
                "notes": "Patient requested morning appointments only",
                "priority": "HOT"
            }
        }
    }


# =============================================================================
# Lead Response Schemas
# =============================================================================

class LeadResponse(BaseModel):
    """
    Schema for lead data returned to authenticated dashboard users.
    
    Includes decrypted PHI for authorized access only.
    """
    
    id: UUID
    
    # Contact Info (decrypted for authorized users)
    first_name: str
    last_name: Optional[str] = None
    email: str
    phone: str
    
    # Clinical Info
    condition: ConditionType
    condition_other: Optional[str] = None
    symptom_duration: DurationType
    prior_treatments: List[TreatmentType]
    
    # Insurance
    has_insurance: bool
    insurance_provider: Optional[str] = None
    
    # Location
    zip_code: str
    in_service_area: bool
    
    # Urgency & Consent
    urgency: UrgencyType
    hipaa_consent: bool
    hipaa_consent_timestamp: Optional[datetime] = None
    privacy_consent_timestamp: Optional[datetime] = None
    sms_consent: bool
    sms_consent_timestamp: Optional[datetime] = None
    
    # Scoring
    score: int
    priority: PriorityType
    
    # TMS Therapy Interest
    tms_therapy_interest: Optional[str] = None
    
    # Status
    status: LeadStatus
    notes: Optional[str] = None
    
    # UTM
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    contacted_at: Optional[datetime] = None
    
    # Scheduling fields
    scheduled_callback_at: Optional[datetime] = None
    scheduled_notes: Optional[str] = None
    contact_method: Optional[ContactMethodType] = None
    last_contact_attempt: Optional[datetime] = None
    contact_attempts: Optional[int] = 0
    next_follow_up_at: Optional[datetime] = None
    
    # Contact Outcome
    contact_outcome: ContactOutcome = ContactOutcome.NEW
    
    # Follow-up tracking
    follow_up_reason: Optional[str] = Field(
        default=None,
        description="Reason for follow-up (e.g., 'No Answer', 'Not Interested', 'No Show')"
    )
    follow_up_date: Optional[datetime] = Field(
        default=None,
        description="When to follow up with this lead"
    )
    
    # Last Activity timestamp
    last_updated_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp of last modification to this lead (NULL for new untouched leads)"
    )

    model_config = {
        "from_attributes": True
    }


class LeadListResponse(BaseModel):
    """
    Schema for lead list items (minimal data for table display).
    
    Used in dashboard lead table for performance.
    Includes phone and email for coordinator outreach.
    """
    
    id: UUID
    lead_number: Optional[str] = None
    first_name: str
    last_name: Optional[str] = None
    # Contact info for coordinator outreach
    email: str
    phone: str
    condition: ConditionType
    # Multi-condition support
    conditions: Optional[List[str]] = None
    other_condition_text: Optional[str] = None
    # Preferred contact method
    preferred_contact_method: Optional[str] = None
    score: int
    priority: PriorityType
    status: LeadStatus
    in_service_area: bool
    created_at: datetime
    scheduled_callback_at: Optional[datetime] = None
    
    # Contact Outcome for coordinator tracking
    contact_outcome: ContactOutcome = ContactOutcome.NEW
    contact_attempts: Optional[int] = 0
    last_contact_attempt: Optional[datetime] = None
    
    # Referral tracking fields
    is_referral: bool = False
    referring_provider_id: Optional[UUID] = None
    referring_provider_name: Optional[str] = None
    
    # Follow-up tracking
    follow_up_reason: Optional[str] = Field(
        default=None,
        description="Reason for follow-up (e.g., 'No Answer', 'Not Interested', 'No Show')"
    )
    
    # Lead source (widget, jotform, manual, etc.)
    source: Optional[str] = Field(
        default=None,
        description="Lead source (widget, jotform, google_ads, referral, manual, etc.)"
    )

    # Last Activity timestamp
    last_updated_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp of last modification to this lead (NULL for new untouched leads)"
    )

    model_config = {
        "from_attributes": True
    }


# =============================================================================
# Contact Outcome Schemas
# =============================================================================

class UpdateContactOutcomeRequest(BaseModel):
    """
    Schema for updating a lead's contact outcome.
    
    Used by coordinators to track outreach results.
    """
    
    contact_outcome: ContactOutcome = Field(
        ...,
        description="Result of contact attempt"
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Notes about the contact outcome"
    )
    next_follow_up_at: Optional[datetime] = Field(
        default=None,
        description="Next scheduled follow-up (for NO_ANSWER, CALLBACK_REQUESTED)"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "contact_outcome": "NO_ANSWER",
                "notes": "Called twice, no answer. Will try again tomorrow.",
                "next_follow_up_at": "2026-01-23T10:00:00Z"
            }
        }
    }


# =============================================================================
# Scheduling Schemas
# =============================================================================

class ScheduleCallbackRequest(BaseModel):
    """
    Schema for scheduling a coordinator callback OR consultation.
    
    CRITICAL ROUTING LOGIC:
    - schedule_type='callback': Sets contact_outcome=CALLBACK_REQUESTED, keeps in Follow-up Queue
    - schedule_type='consultation': Sets status=SCHEDULED, contact_outcome=SCHEDULED, moves to Scheduled Queue
    """
    
    scheduled_callback_at: datetime = Field(
        ...,
        description="Date and time for the scheduled callback/consultation"
    )
    scheduled_notes: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Notes for the scheduled callback/consultation"
    )
    contact_method: ContactMethodType = Field(
        default=ContactMethodType.PHONE,
        description="Preferred method of contact"
    )
    schedule_type: Optional[str] = Field(
        default="callback",
        description="Type of schedule: 'callback' (stays in follow-up) or 'consultation' (moves to scheduled)"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "scheduled_callback_at": "2026-01-22T10:00:00Z",
                "scheduled_notes": "Patient prefers morning calls",
                "contact_method": "PHONE",
                "schedule_type": "callback"
            }
        }
    }


class LogContactAttemptRequest(BaseModel):
    """
    Schema for logging a contact attempt.
    """
    
    contact_method: ContactMethodType = Field(
        ...,
        description="Method used to contact the lead"
    )
    was_successful: bool = Field(
        ...,
        description="Whether the contact attempt was successful"
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Notes about the contact attempt"
    )
    next_follow_up_at: Optional[datetime] = Field(
        default=None,
        description="Next scheduled follow-up if not reached"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "contact_method": "PHONE",
                "was_successful": False,
                "notes": "No answer, left voicemail",
                "next_follow_up_at": "2026-01-23T14:00:00Z"
            }
        }
    }


class ScheduledLeadResponse(BaseModel):
    """
    Schema for scheduled leads in calendar view.
    """
    
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
    phone: Optional[str] = None  # Decrypted for authorized users

    model_config = {
        "from_attributes": True
    }


# =============================================================================
# Manual Lead Creation Schema (Coordinator Entry)
# =============================================================================

class ManualLeadCreate(BaseModel):
    """
    Schema for manually creating a lead from the coordinator dashboard.
    
    Only first_name is required. All other fields are optional so coordinators
    can quickly add a lead with minimal information and fill in details later.
    """
    
    first_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Patient first name (required)"
    )
    last_name: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Patient last name"
    )
    email: Optional[EmailStr] = Field(
        default=None,
        description="Patient email address"
    )
    phone: Optional[str] = Field(
        default=None,
        max_length=20,
        description="Patient phone number"
    )
    condition: Optional[ConditionType] = Field(
        default=None,
        description="Primary mental health condition"
    )
    condition_other: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Description if condition is 'OTHER'"
    )
    symptom_duration: Optional[DurationType] = Field(
        default=None,
        description="How long symptoms have been present"
    )
    prior_treatments: Optional[List[TreatmentType]] = Field(
        default=None,
        description="List of prior treatments tried"
    )
    has_insurance: Optional[bool] = Field(
        default=None,
        description="Whether patient has health insurance"
    )
    insurance_provider: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Insurance provider name"
    )
    zip_code: Optional[str] = Field(
        default=None,
        max_length=10,
        description="Patient ZIP code"
    )
    urgency: Optional[UrgencyType] = Field(
        default=None,
        description="How urgently patient needs treatment"
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=5000,
        description="Coordinator notes about the lead"
    )

    @field_validator("phone")
    @classmethod
    def normalize_phone_manual(cls, v: Optional[str]) -> Optional[str]:
        """Normalize phone to E.164 format if provided."""
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
        """Validate US ZIP code format if provided."""
        if v is None or v.strip() == "":
            return None
        cleaned = v.replace(" ", "").replace("-", "")
        if not cleaned.isdigit():
            raise ValueError("ZIP code must contain only digits")
        if len(cleaned) not in (5, 9):
            raise ValueError("ZIP code must be 5 or 9 digits")
        return cleaned[:5]

    model_config = {
        "json_schema_extra": {
            "example": {
                "first_name": "John",
                "last_name": "Doe",
                "phone": "(555) 123-4567",
                "condition": "DEPRESSION",
                "notes": "Called in, interested in TMS therapy"
            }
        }
    }


class LeadSubmitResponse(BaseModel):
    """
    Schema for widget submission response.
    
    Returns minimal data to confirm submission without exposing internals.
    """
    
    success: bool = Field(
        ...,
        description="Whether submission was successful"
    )
    message: str = Field(
        ...,
        description="User-friendly confirmation message"
    )
    lead_id: Optional[UUID] = Field(
        default=None,
        description="ID of created lead (for tracking)"
    )
    priority: Optional[PriorityType] = Field(
        default=None,
        description="Calculated priority level"
    )
    estimated_response_time: Optional[str] = Field(
        default=None,
        description="Estimated time for clinic to respond"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "message": "Thank you! A care coordinator will contact you within 24 hours.",
                "lead_id": "123e4567-e89b-12d3-a456-426614174000",
                "priority": "HOT",
                "estimated_response_time": "Within 24 hours"
            }
        }
    }
