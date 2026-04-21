"""
SQLAlchemy ORM models for SleepReach.

Contains database table definitions and relationships.
All PHI fields are stored encrypted in the database.
"""

from .lead import Lead, ConditionType, DurationType, TreatmentType, UrgencyType, PriorityType, LeadStatus, ContactOutcome, LeadSource
from .audit_log import AuditLog, AuditAction
from .provider import ReferringProvider, ProviderSpecialty, ProviderStatus, ProviderContactMethod
from .attachment import LeadAttachment
from .user import User, UserRole, UserStatus
from .lead_note import LeadNote

__all__ = [
    # Lead model and enums
    "Lead",
    "ConditionType",
    "DurationType",
    "TreatmentType",
    "UrgencyType",
    "PriorityType",
    "LeadStatus",
    "ContactOutcome",
    "LeadSource",
    "LeadAttachment",
    # Provider model and enums
    "ReferringProvider",
    "ProviderSpecialty",
    "ProviderStatus",
    "ProviderContactMethod",
    # User model and enums
    "User",
    "UserRole",
    "UserStatus",
    # Note model
    "LeadNote",
    # Audit model and enums
    "AuditLog",
    "AuditAction",
]
