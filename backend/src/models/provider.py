"""
Referring Provider database model.

Represents healthcare providers who refer patients for TMS therapy.
Tracks provider information, referral metrics, and relationship status.
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
    DateTime,
    Enum as SQLEnum,
    ARRAY,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from ..core.database import Base


# =============================================================================
# Enum Definitions
# =============================================================================

class ProviderNoteType(str, enum.Enum):
    """Types of provider notes/interactions."""
    GENERAL = "general"
    CALL = "call"
    MEETING = "meeting"
    EMAIL = "email"
    FOLLOWUP = "followup"


# DEPRECATED - Specialty is now free-text, not enum
# Kept for backward compatibility with any code that imports it
class ProviderSpecialty(str, enum.Enum):
    """DEPRECATED - Use free-text specialty field instead."""
    PSYCHIATRIST = "PSYCHIATRIST"
    PSYCHOLOGIST = "PSYCHOLOGIST"
    THERAPIST = "THERAPIST"
    PRIMARY_CARE = "PRIMARY_CARE"
    NEUROLOGIST = "NEUROLOGIST"
    SOCIAL_WORKER = "SOCIAL_WORKER"
    NURSE_PRACTITIONER = "NURSE_PRACTITIONER"
    OTHER = "OTHER"


class ProviderStatus(str, enum.Enum):
    """Provider relationship status."""
    ACTIVE = "ACTIVE"      # Verified, actively referring
    PENDING = "PENDING"    # Auto-created, awaiting verification
    INACTIVE = "INACTIVE"  # No referrals in 12+ months
    ARCHIVED = "ARCHIVED"  # Historical data only


class ProviderContactMethod(str, enum.Enum):
    """Preferred contact method for provider communications."""
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    FAX = "FAX"
    PORTAL = "PORTAL"


# =============================================================================
# Referring Provider Model
# =============================================================================

class ReferringProvider(Base):
    """
    Healthcare provider who refers patients.
    
    Tracks provider identity, practice information, metrics,
    and relationship status for referral management.
    
    Attributes:
        id: UUID primary key
        name: Provider's full name
        email: Primary contact email (unique identifier)
        phone: Contact phone number
        npi_number: National Provider Identifier (10 digits)
        practice_name: Name of the clinic/practice
        specialty: Provider's medical specialty
        status: Relationship status (Active/Pending/Inactive/Archived)
        total_referrals: Count of all referrals (denormalized)
        converted_referrals: Count of converted referrals (denormalized)
    """
    
    __tablename__ = "referring_providers"
    
    # Primary key
    id = Column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
        nullable=False,
    )
    
    # Provider Identity
    name = Column(String(255), nullable=False, index=True)
    email = Column(String(255), nullable=True, unique=True)
    phone = Column(String(20), nullable=True)
    fax = Column(String(20), nullable=True)
    npi_number = Column(String(20), nullable=True, unique=True)
    
    # Practice Information
    practice_name = Column(String(255), nullable=True, index=True)
    practice_address = Column(Text, nullable=True)
    practice_city = Column(String(100), nullable=True)
    practice_state = Column(String(2), nullable=True)
    practice_zip = Column(String(10), nullable=True)
    
    # Professional Details - FREE TEXT (stores exactly what user types)
    specialty = Column(String(255), nullable=True)  # e.g., "Neurology", "Family Medicine", any text
    credentials = Column(String(50), nullable=True)  # e.g., "MD", "PhD", "LCSW"
    
    # Status & Preferences
    status = Column(
        SQLEnum(ProviderStatus, name="provider_status", create_type=False),
        nullable=False,
        default=ProviderStatus.PENDING,
    )
    preferred_contact = Column(
        SQLEnum(ProviderContactMethod, name="provider_contact_method", create_type=False),
        nullable=True,
        default=ProviderContactMethod.EMAIL,
    )
    send_referral_updates = Column(Boolean, nullable=False, default=True)
    
    # Metrics (denormalized for dashboard performance)
    total_referrals = Column(Integer, nullable=False, default=0)
    converted_referrals = Column(Integer, nullable=False, default=0)
    last_referral_at = Column(DateTime(timezone=True), nullable=True)
    
    # Notes & Metadata
    notes = Column(Text, nullable=True)
    tags = Column(ARRAY(Text), nullable=True, default=[])
    
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
    verified_at = Column(DateTime(timezone=True), nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships (will be set up when Lead model is updated)
    # referrals = relationship("Lead", back_populates="referring_provider")
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<ReferringProvider(id={self.id}, "
            f"name='{self.name}', "
            f"practice='{self.practice_name}', "
            f"status={self.status.value})>"
        )
    
    @property
    def conversion_rate(self) -> float:
        """
        Calculate conversion rate for this provider.
        
        Returns:
            Percentage of referrals that converted (0-100)
        """
        if self.total_referrals == 0:
            return 0.0
        return round((self.converted_referrals / self.total_referrals) * 100, 1)
    
    @property
    def display_name(self) -> str:
        """
        Get display name including credentials if available.
        
        Returns:
            Formatted name like "Dr. Sarah Johnson, MD"
        """
        if self.credentials:
            return f"{self.name}, {self.credentials}"
        return self.name
    
    @property
    def full_address(self) -> Optional[str]:
        """
        Get full formatted address.
        
        Returns:
            Formatted address string or None
        """
        parts = []
        if self.practice_address:
            parts.append(self.practice_address)
        
        city_state_zip = []
        if self.practice_city:
            city_state_zip.append(self.practice_city)
        if self.practice_state:
            city_state_zip.append(self.practice_state)
        if self.practice_zip:
            city_state_zip.append(self.practice_zip)
        
        if city_state_zip:
            parts.append(", ".join(city_state_zip))
        
        return "\n".join(parts) if parts else None
    
    def to_dict(self) -> dict:
        """
        Convert to dictionary for API responses.
        
        Returns:
            Dictionary with all provider fields
        """
        return {
            "id": str(self.id),
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "fax": self.fax,
            "npi_number": self.npi_number,
            "practice_name": self.practice_name,
            "practice_address": self.practice_address,
            "practice_city": self.practice_city,
            "practice_state": self.practice_state,
            "practice_zip": self.practice_zip,
            "specialty": self.specialty,  # Free text - stored and returned as-is
            "credentials": self.credentials,
            "status": self.status.value if self.status else None,
            "preferred_contact": self.preferred_contact.value if self.preferred_contact else None,
            "send_referral_updates": self.send_referral_updates,
            "total_referrals": self.total_referrals,
            "converted_referrals": self.converted_referrals,
            "conversion_rate": self.conversion_rate,
            "last_referral_at": self.last_referral_at.isoformat() if self.last_referral_at else None,
            "notes": self.notes,
            "tags": self.tags or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
        }
    
    def to_summary_dict(self) -> dict:
        """
        Convert to summary dictionary for list views.
        
        Returns:
            Dictionary with essential provider fields only
        """
        return {
            "id": str(self.id),
            "name": self.name,
            "practice_name": self.practice_name,
            "specialty": self.specialty,  # Free text - stored and returned as-is
            "status": self.status.value if self.status else None,
            "total_referrals": self.total_referrals,
            "converted_referrals": self.converted_referrals,
            "conversion_rate": self.conversion_rate,
            "last_referral_at": self.last_referral_at.isoformat() if self.last_referral_at else None,
        }


# =============================================================================
# Provider Notes History Model
# =============================================================================

class ProviderNotesHistory(Base):
    """
    Historical log of all notes and interactions with referring providers.
    
    This allows coordinators to track context over time and see the history
    of communications and updates for each provider.
    
    Attributes:
        id: UUID primary key
        provider_id: Foreign key to the provider
        note_text: The actual note content
        note_type: Type of note (general, call, meeting, email, followup)
        created_by: Name/email of the coordinator who created the note
        created_at: When the note was created
    """
    
    __tablename__ = "provider_notes_history"
    
    # Primary key
    id = Column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
        nullable=False,
    )
    
    # Foreign key to provider
    provider_id = Column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    
    # Note content
    note_text = Column(Text, nullable=False)
    note_type = Column(String(50), nullable=False, default="general")
    
    # Metadata
    created_by = Column(String(255), nullable=True)
    
    # Timestamp
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<ProviderNotesHistory(id={self.id}, "
            f"provider_id={self.provider_id}, "
            f"note_type='{self.note_type}')>"
        )
    
    def to_dict(self) -> dict:
        """
        Convert to dictionary for API responses.
        
        Returns:
            Dictionary with all note fields
        """
        return {
            "id": str(self.id),
            "provider_id": str(self.provider_id),
            "note_text": self.note_text,
            "note_type": self.note_type,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
