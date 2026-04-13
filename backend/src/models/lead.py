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
# Enum Definitions (must match database/init/001_initial_schema.sql)
# =============================================================================

class ConditionType(str, enum.Enum):
    """Sleep-treatable conditions."""
    INSOMNIA = "INSOMNIA"
    SLEEP_APNEA = "SLEEP_APNEA"
    RESTLESS_LEG = "RESTLESS_LEG"
    NARCOLEPSY = "NARCOLEPSY"
    OTHER = "OTHER"


class DurationType(str, enum.Enum):
    """Symptom duration ranges."""
    LESS_THAN_6_MONTHS = "LESS_THAN_6_MONTHS"
    SIX_TO_TWELVE_MONTHS = "SIX_TO_TWELVE_MONTHS"
    MORE_THAN_12_MONTHS = "MORE_THAN_12_MONTHS"


class TreatmentType(str, enum.Enum):
    """Prior treatment options for sleep disorders."""
    CPAP_BIPAP = "CPAP_BIPAP"
    MEDICATION = "MEDICATION"
    SLEEP_STUDY = "SLEEP_STUDY"
    THERAPY_CBT = "THERAPY_CBT"
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
    """Contact outcome for coordinator outreach tracking."""
    NEW = "NEW"
    ANSWERED = "ANSWERED"
    NO_ANSWER = "NO_ANSWER"
    UNREACHABLE = "UNREACHABLE"
    CALLBACK_REQUESTED = "CALLBACK_REQUESTED"
    SCHEDULED = "SCHEDULED"
    COMPLETED = "COMPLETED"
    NOT_INTERESTED = "NOT_INTERESTED"


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
    Database enum: {widget,jotform,referral,manual,api,import}
    """
    widget = "widget"
    jotform = "jotform"
    referral = "referral"
    manual = "manual"
    api = "api"
    IMPORT = "import"


# =============================================================================
# Lead Model
# =============================================================================

class Lead(Base):
    """
    Patient intake lead model for Sleep Institute of Arizona.
    
    Stores patient information from the intake widget.
    All PHI (Protected Health Information) is encrypted at rest.
    """
    
    __tablename__ = "leads"
    
    # Primary key
    id = Column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
        nullable=False,
    )
    
    # Lead Number (auto-generated: SR-YYYY-XXX)
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
    
    # Date of Birth
    date_of_birth = Column(Date, nullable=True)
    
    # Clinical Information
    condition = Column(
        SQLEnum(ConditionType, name="condition_type", create_type=False),
        nullable=False,
    )
    condition_other = Column(Text, nullable=True)
    
    # Multi-condition support
    conditions = Column(ARRAY(Text), nullable=True, default=[])
    other_condition_text = Column(Text, nullable=True)
    
    # Sleep Treatment Interest
    sleep_treatment_interest = Column(Text, nullable=True)
    
    # Preferred Contact Method
    preferred_contact_method = Column(Text, nullable=True)
    
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
    other_insurance_provider = Column(Text, nullable=True)
    
    # Location
    zip_code = Column(String(10), nullable=False)
    in_service_area = Column(Boolean, nullable=False, default=False, index=True)
    lead_location = Column(String(200), nullable=True)  # City/area recorded by coordinator (e.g., "Gilbert, AZ")
    
    # Urgency & Consent
    urgency = Column(
        SQLEnum(UrgencyType, name="urgency_type", create_type=False),
        nullable=False,
    )
    hipaa_consent = Column(Boolean, nullable=False, default=False)
    hipaa_consent_timestamp = Column(DateTime(timezone=True), nullable=True)
    privacy_consent_timestamp = Column(DateTime(timezone=True), nullable=True)
    sms_consent = Column(Boolean, nullable=False, default=False)
    sms_consent_timestamp = Column(DateTime(timezone=True), nullable=True)
    
    # Scoring & Priority
    score = Column(Integer, nullable=False, default=0)
    lead_score = Column(Integer, nullable=True, default=0)
    priority = Column(
        SQLEnum(PriorityType, name="priority_type", create_type=False),
        nullable=False,
        default=PriorityType.LOW,
        index=True,
    )
    
    # Score Breakdown Fields
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
        index=True,
    )
    assigned_to = Column(PGUUID(as_uuid=True), nullable=True)
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
    ip_address_hash = Column(String(64), nullable=True)
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
    last_updated_at = Column(DateTime(timezone=True), nullable=True, index=True)
    
    # Soft delete
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    
    # Scheduling fields
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
    
    # Contact Outcome
    contact_outcome = Column(
        SQLEnum(ContactOutcome, name="contact_outcome_type", create_type=False),
        nullable=False,
        default=ContactOutcome.NEW,
    )
    
    # Follow-up tracking
    follow_up_reason = Column(String(100), nullable=True)
    follow_up_date = Column(DateTime(timezone=True), nullable=True)
    last_follow_up_sent_at = Column(DateTime(timezone=True), nullable=True)
    
    # Referral Information
    is_referral = Column(Boolean, nullable=False, default=False, index=True)
    referring_provider_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("referring_providers.id"),
        nullable=True,
        index=True,
    )
    referring_provider_raw = Column(JSONB, nullable=True)
    
    # Relationship to ReferringProvider
    referring_provider = relationship(
        "ReferringProvider",
        foreign_keys=[referring_provider_id],
        backref="referrals",
    )
    
    def __repr__(self) -> str:
        return (
            f"<Lead(id={self.id}, "
            f"condition={self.condition.value}, "
            f"priority={self.priority.value}, "
            f"status={self.status.value})>"
        )
    
    def to_safe_dict(self) -> dict:
        return {
            "id": str(self.id),
            "condition": self.condition.value,
            "symptom_duration": self.symptom_duration.value,
            "has_insurance": self.has_insurance,
            "zip_code": self.zip_code[:3] + "**" if self.zip_code else None,
            "in_service_area": self.in_service_area,
            "urgency": self.urgency.value,
            "score": self.score,
            "priority": self.priority.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
