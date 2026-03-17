"""
Lead database model.

Represents patient intake leads with encrypted PHI fields.
Matches the PostgreSQL schema defined in database/init/001_initial_schema.sql
"""

import enum
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from sqlalchemy import (
    Column,
    String,
    Boolean,
    Integer,
    Text,
    LargeBinary,
    DateTime,
    Date,
    Enum as SQLEnum,
    ARRAY,
    ForeignKey,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from ..core.database import Base


# =============================================================================
# Enum Definitions
# =============================================================================

class ConditionType(str, enum.Enum):
    """TMS-treatable conditions."""
    DEPRESSION = "DEPRESSION"
    ANXIETY = "ANXIETY"
    OCD = "OCD"
    PTSD = "PTSD"
    OTHER = "OTHER"


class DurationType(str, enum.Enum):
    """Symptom duration ranges."""
    LESS_THAN_6_MONTHS = "LESS_THAN_6_MONTHS"
    SIX_TO_TWELVE_MONTHS = "SIX_TO_TWELVE_MONTHS"
    MORE_THAN_12_MONTHS = "MORE_THAN_12_MONTHS"


class TreatmentType(str, enum.Enum):
    """Prior treatment options."""
    ANTIDEPRESSANTS = "ANTIDEPRESSANTS"
    THERAPY_CBT = "THERAPY_CBT"
    BOTH = "BOTH"
    NONE = "NONE"
    OTHER = "OTHER"


class UrgencyType(str, enum.Enum):
    """Urgency levels for treatment."""
    ASAP = "ASAP"
    WITHIN_30_DAYS = "WITHIN_30_DAYS"
    EXPLORING = "EXPLORING"


class PriorityType(str, enum.Enum):
    """Lead priority calculated from scoring."""
    HOT = "HOT"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    DISQUALIFIED = "DISQUALIFIED"


class LeadStatus(str, enum.Enum):
    """Lead status for tracking through funnel."""
    NEW = "NEW"
    CONTACTED = "CONTACTED"
    SCHEDULED = "SCHEDULED"
    CONSULTATION_COMPLETE = "CONSULTATION_COMPLETE"
    TREATMENT_STARTED = "TREATMENT_STARTED"
    LOST = "LOST"
    DISQUALIFIED = "DISQUALIFIED"


class ContactOutcome(str, enum.Enum):
    """
    Contact outcome for coordinator outreach tracking.
    
    Tracks the result of each contact attempt, enabling:
    - Filtering leads by outcome (show only 'no answer' leads)
    - Progress tracking through outreach workflow
    - Reporting on contact success rates
    """
    NEW = "NEW"                      # Not contacted yet
    ANSWERED = "ANSWERED"            # Spoke with lead, can proceed to schedule
    NO_ANSWER = "NO_ANSWER"          # Called but no pickup, needs follow-up
    UNREACHABLE = "UNREACHABLE"      # Wrong number, disconnected, etc.
    CALLBACK_REQUESTED = "CALLBACK_REQUESTED"  # Lead asked to call back at specific time
    SCHEDULED = "SCHEDULED"          # Consultation has been scheduled
    COMPLETED = "COMPLETED"          # Consultation completed successfully
    NOT_INTERESTED = "NOT_INTERESTED"  # Lead declined, archive


class ContactMethodType(str, enum.Enum):
    """Preferred contact method for lead."""
    PHONE = "PHONE"
    EMAIL = "EMAIL"
    SMS = "SMS"
    VIDEO_CALL = "VIDEO_CALL"


class LeadSource(str, enum.Enum):
    """Lead source/platform for tracking.
    
    IMPORTANT: Enum member NAMES must be lowercase to match PostgreSQL enum values.
    SQLAlchemy with create_type=False uses member NAMES for comparison, not values.
    Database enum: {widget,jotform,google_ads,referral,manual,api,import}
    """
    widget = "widget"
    jotform = "jotform"
    google_ads = "google_ads"
    referral = "referral"
    manual = "manual"
    api = "api"
    # Note: 'import' is a Python reserved keyword, using IMPORT with special handling
    IMPORT = "import"


# =============================================================================
# Lead Model
# =============================================================================

class Lead(Base):
    """
    Patient intake lead model.
    
    Stores patient information from the intake widget.
    All PHI (Protected Health Information) is encrypted at rest.
    
    Attributes:
        id: UUID primary key
        first_name_encrypted: AES-256 encrypted first name (PHI)
        last_name_encrypted: AES-256 encrypted last name (PHI)
        email_encrypted: AES-256 encrypted email (PHI)
        phone_encrypted: AES-256 encrypted phone (PHI)
        condition: Selected mental health condition
        symptom_duration: Duration of symptoms
        prior_treatments: Array of prior treatments tried
        has_insurance: Insurance status
        zip_code: ZIP code for service area check
        in_service_area: Whether ZIP is in service area
        urgency: Treatment urgency level
        hipaa_consent: HIPAA consent given
        sms_consent: SMS communication consent
        score: Calculated lead score
        priority: Calculated priority level
        status: Current lead status
    """
    
    __tablename__ = "leads"
    
    # Primary key
    id = Column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
        nullable=False,
    )
    
    # Lead Number (auto-generated: NR-YYYY-XXX)
    lead_number = Column(
        String(20),
        unique=True,
        nullable=False,
        index=True,
    )
    
    # Contact Information (PHI - encrypted)
    first_name_encrypted = Column(LargeBinary, nullable=False)
    last_name_encrypted = Column(LargeBinary, nullable=True)
    email_encrypted = Column(LargeBinary, nullable=False)
    phone_encrypted = Column(LargeBinary, nullable=False)
    
    # Date of Birth (for age verification - must be 18+)
    date_of_birth = Column(Date, nullable=True)
    
    # Clinical Information
    condition = Column(
        SQLEnum(ConditionType, name="condition_type", create_type=False),
        nullable=False,
    )
    condition_other = Column(Text, nullable=True)  # Only if condition = 'OTHER'
    
    # Multi-condition support (normalized lowercase keys: depression, anxiety, ocd, ptsd, other)
    conditions = Column(ARRAY(Text), nullable=True, default=[])
    other_condition_text = Column(Text, nullable=True)  # Free text when 'other' selected
    
    # TMS Therapy Interest
    tms_therapy_interest = Column(Text, nullable=True)  # daily_tms, accelerated_tms, not_sure
    
    # Preferred Contact Method
    preferred_contact_method = Column(Text, nullable=True)  # phone_call, text, email, any
    
    # Depression PHQ-2 Assessment (0-3 each)
    phq2_interest = Column(Integer, nullable=True)
    phq2_mood = Column(Integer, nullable=True)
    depression_severity_score = Column(Integer, nullable=True)  # 0-6
    depression_severity_level = Column(Text, nullable=True)  # minimal, mild, moderate, severe
    
    # Anxiety GAD-2 Assessment (0-3 each)
    gad2_nervous = Column(Integer, nullable=True)
    gad2_worry = Column(Integer, nullable=True)
    anxiety_severity_score = Column(Integer, nullable=True)  # 0-6
    anxiety_severity_level = Column(Text, nullable=True)  # minimal, mild, moderate, severe
    
    # OCD Assessment
    ocd_time_occupied = Column(Integer, nullable=True)  # 1-4
    ocd_severity_level = Column(Text, nullable=True)  # mild, moderate, moderate_severe, severe
    
    # PTSD Assessment
    ptsd_intrusion = Column(Integer, nullable=True)  # 0-4
    ptsd_severity_level = Column(Text, nullable=True)  # minimal, mild, moderate, moderate_severe, severe
    
    symptom_duration = Column(
        SQLEnum(DurationType, name="duration_type", create_type=False),
        nullable=False,
    )
    prior_treatments = Column(
        ARRAY(SQLEnum(TreatmentType, name="treatment_type", create_type=False)),
        nullable=False,
        default=[],
    )
    
    # Insurance Information
    has_insurance = Column(Boolean, nullable=False)
    insurance_provider = Column(Text, nullable=True)
    other_insurance_provider = Column(Text, nullable=True)  # When provider = 'Other'
    
    # Location
    zip_code = Column(String(10), nullable=False)
    in_service_area = Column(Boolean, nullable=False, default=False)
    
    # Urgency & Consent
    urgency = Column(
        SQLEnum(UrgencyType, name="urgency_type", create_type=False),
        nullable=False,
    )
    hipaa_consent = Column(Boolean, nullable=False, default=False)
    hipaa_consent_timestamp = Column(DateTime(timezone=True), nullable=True)  # When HIPAA consent was given
    privacy_consent_timestamp = Column(DateTime(timezone=True), nullable=True)  # When privacy consent was given
    sms_consent = Column(Boolean, nullable=False, default=False)
    sms_consent_timestamp = Column(DateTime(timezone=True), nullable=True)  # When SMS consent was given
    
    # Scoring & Priority
    score = Column(Integer, nullable=False, default=0)
    lead_score = Column(Integer, nullable=True, default=0)  # Alias for score
    priority = Column(
        SQLEnum(PriorityType, name="priority_type", create_type=False),
        nullable=False,
        default=PriorityType.LOW,
    )
    
    # Score Breakdown Fields (for transparency)
    condition_score = Column(Integer, nullable=True, default=0)
    therapy_interest_score = Column(Integer, nullable=True, default=0)
    severity_score = Column(Integer, nullable=True, default=0)
    insurance_score = Column(Integer, nullable=True, default=0)
    duration_score = Column(Integer, nullable=True, default=0)
    treatment_score = Column(Integer, nullable=True, default=0)
    location_score = Column(Integer, nullable=True, default=0)
    urgency_score = Column(Integer, nullable=True, default=0)
    
    # Lead Management
    status = Column(
        SQLEnum(LeadStatus, name="lead_status", create_type=False),
        nullable=False,
        default=LeadStatus.NEW,
    )
    assigned_to = Column(PGUUID(as_uuid=True), nullable=True)  # Future: FK to users
    notes = Column(Text, nullable=True)
    
    # Lead Source/Platform
    source = Column(
        SQLEnum(LeadSource, name="lead_source", create_type=False),
        nullable=False,
        default=LeadSource.widget,
    )
    
    # UTM Tracking
    utm_source = Column(String(255), nullable=True)
    utm_medium = Column(String(255), nullable=True)
    utm_campaign = Column(String(255), nullable=True)
    utm_term = Column(String(255), nullable=True)
    utm_content = Column(String(255), nullable=True)
    
    # Metadata
    ip_address_hash = Column(String(64), nullable=True)  # SHA-256 hashed
    user_agent = Column(Text, nullable=True)
    referrer_url = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )
    contacted_at = Column(DateTime(timezone=True), nullable=True)
    converted_at = Column(DateTime(timezone=True), nullable=True)
    
    # Last activity timestamp (NULL for new untouched leads)
    # Updated whenever ANY action is taken: status change, notes, scheduling, contact attempts, etc.
    last_updated_at = Column(DateTime(timezone=True), nullable=True, index=True)
    
    # Soft delete
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    
    # Scheduling fields (for coordinator callbacks)
    scheduled_callback_at = Column(DateTime(timezone=True), nullable=True)
    scheduled_notes = Column(Text, nullable=True)
    contact_method = Column(
        SQLEnum(ContactMethodType, name="contact_method", create_type=False),
        nullable=True,
        default=ContactMethodType.PHONE,
    )
    last_contact_attempt = Column(DateTime(timezone=True), nullable=True)
    contact_attempts = Column(Integer, nullable=True, default=0)
    next_follow_up_at = Column(DateTime(timezone=True), nullable=True)
    
    # Contact Outcome (result of coordinator outreach)
    contact_outcome = Column(
        SQLEnum(ContactOutcome, name="contact_outcome_type", create_type=False),
        nullable=False,
        default=ContactOutcome.NEW,
    )
    
    # Follow-up tracking (set by outcome workflow logic)
    follow_up_reason = Column(String(100), nullable=True)  # e.g., "No Answer", "Not Interested", "No Show"
    follow_up_date = Column(DateTime(timezone=True), nullable=True)  # When to follow up
    
    # Automated follow-up tracking (6-hour SMS + email cycle)
    last_follow_up_sent_at = Column(DateTime(timezone=True), nullable=True)
    
    # ==========================================================================
    # Referral Information
    # ==========================================================================
    
    # Flag for quick filtering of referral leads
    is_referral = Column(Boolean, nullable=False, default=False, index=True)
    
    # Foreign key to referring provider (nullable - some referrals may not have matched provider)
    referring_provider_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("referring_providers.id"),
        nullable=True,
        index=True,
    )
    
    # Raw referral data from Jotform (preserved even if provider matching fails)
    referring_provider_raw = Column(JSONB, nullable=True)
    
    # Relationship to ReferringProvider
    referring_provider = relationship(
        "ReferringProvider",
        foreign_keys=[referring_provider_id],
        backref="referrals",
    )
    
    def __repr__(self) -> str:
        """
        String representation without exposing PHI.
        
        Returns:
            Safe string representation of lead
        """
        return (
            f"<Lead(id={self.id}, "
            f"condition={self.condition.value}, "
            f"priority={self.priority.value}, "
            f"status={self.status.value})>"
        )
    
    def to_safe_dict(self) -> dict:
        """
        Convert to dictionary without PHI for logging/debugging.
        
        Returns:
            Dictionary with non-PHI fields only
        """
        return {
            "id": str(self.id),
            "condition": self.condition.value,
            "symptom_duration": self.symptom_duration.value,
            "has_insurance": self.has_insurance,
            "zip_code": self.zip_code[:3] + "**" if self.zip_code else None,  # Partial ZIP
            "in_service_area": self.in_service_area,
            "urgency": self.urgency.value,
            "score": self.score,
            "priority": self.priority.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
