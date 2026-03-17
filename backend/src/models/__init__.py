"""
SQLAlchemy ORM models for NeuroReach AI.

Contains database table definitions and relationships.
All PHI fields are stored encrypted in the database.
"""

from .lead import Lead, ConditionType, DurationType, TreatmentType, UrgencyType, PriorityType, LeadStatus, ContactOutcome, LeadSource
from .audit_log import AuditLog, AuditAction
from .provider import ReferringProvider, ProviderSpecialty, ProviderStatus, ProviderContactMethod

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
    # Provider model and enums
    "ReferringProvider",
    "ProviderSpecialty",
    "ProviderStatus",
    "ProviderContactMethod",
    # Audit model and enums
    "AuditLog",
    "AuditAction",
]
