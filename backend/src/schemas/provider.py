"""
Referring Provider Pydantic schemas for request/response validation.

Defines DTOs for provider management and referral tracking.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field, EmailStr, field_validator

from ..models.provider import ProviderStatus, ProviderContactMethod


# =============================================================================
# Provider Create/Update Schemas
# =============================================================================

class ProviderCreate(BaseModel):
    """
    Schema for creating a new referring provider manually.
    """
    
    name: str = Field(
        ...,
        min_length=2,
        max_length=255,
        description="Provider's full name"
    )
    email: Optional[EmailStr] = Field(
        default=None,
        description="Provider's email address (used for matching)"
    )
    phone: Optional[str] = Field(
        default=None,
        max_length=20,
        description="Provider's phone number"
    )
    fax: Optional[str] = Field(
        default=None,
        max_length=20,
        description="Provider's fax number"
    )
    npi_number: Optional[str] = Field(
        default=None,
        min_length=10,
        max_length=10,
        description="National Provider Identifier (10 digits)"
    )
    practice_name: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Name of the clinic/practice"
    )
    practice_address: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Practice street address"
    )
    practice_city: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Practice city"
    )
    practice_state: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=2,
        description="Practice state (2-letter code)"
    )
    practice_zip: Optional[str] = Field(
        default=None,
        max_length=10,
        description="Practice ZIP code"
    )
    specialty: str = Field(
        default="",
        max_length=255,
        description="Provider's medical specialty (free text - any value allowed)"
    )
    credentials: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Professional credentials (e.g., MD, PhD, LCSW)"
    )
    status: ProviderStatus = Field(
        default=ProviderStatus.ACTIVE,
        description="Provider relationship status"
    )
    preferred_contact: ProviderContactMethod = Field(
        default=ProviderContactMethod.EMAIL,
        description="Preferred contact method"
    )
    send_referral_updates: bool = Field(
        default=True,
        description="Whether to send automated referral status updates"
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Internal notes about the provider"
    )
    tags: Optional[List[str]] = Field(
        default=None,
        description="Tags for categorization"
    )
    
    @field_validator("npi_number")
    @classmethod
    def validate_npi(cls, v: Optional[str]) -> Optional[str]:
        """Validate NPI is 10 digits."""
        if v is None:
            return v
        if not v.isdigit() or len(v) != 10:
            raise ValueError("NPI must be exactly 10 digits")
        return v
    
    @field_validator("practice_state")
    @classmethod
    def validate_state(cls, v: Optional[str]) -> Optional[str]:
        """Validate state is 2-letter code."""
        if v is None:
            return v
        return v.upper()

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Dr. Sarah Johnson",
                "email": "sjohnson@mentalhealth.com",
                "phone": "(555) 123-4567",
                "npi_number": "1234567890",
                "practice_name": "City Mental Health Clinic",
                "practice_city": "Phoenix",
                "practice_state": "AZ",
                "practice_zip": "85001",
                "specialty": "PSYCHIATRIST",
                "credentials": "MD",
                "status": "ACTIVE",
                "preferred_contact": "EMAIL",
                "send_referral_updates": True
            }
        }
    }


class ProviderUpdate(BaseModel):
    """
    Schema for updating a referring provider.
    All fields are optional.
    """
    
    name: Optional[str] = Field(default=None, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=20)
    fax: Optional[str] = Field(default=None, max_length=20)
    npi_number: Optional[str] = Field(default=None, max_length=10)
    practice_name: Optional[str] = Field(default=None, max_length=255)
    practice_address: Optional[str] = Field(default=None, max_length=500)
    practice_city: Optional[str] = Field(default=None, max_length=100)
    practice_state: Optional[str] = Field(default=None, max_length=2)
    practice_zip: Optional[str] = Field(default=None, max_length=10)
    specialty: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Provider's medical specialty (free text)"
    )
    credentials: Optional[str] = Field(default=None, max_length=50)
    status: Optional[ProviderStatus] = None
    preferred_contact: Optional[ProviderContactMethod] = None
    send_referral_updates: Optional[bool] = None
    notes: Optional[str] = Field(default=None, max_length=2000)
    tags: Optional[List[str]] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "ACTIVE",
                "notes": "Verified provider - contacted on 2026-01-20"
            }
        }
    }


# =============================================================================
# Provider Response Schemas
# =============================================================================

class ProviderResponse(BaseModel):
    """
    Schema for provider data returned to dashboard users.
    Includes all provider details and computed metrics.
    """
    
    id: UUID
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    fax: Optional[str] = None
    npi_number: Optional[str] = None
    
    # Practice Info
    practice_name: Optional[str] = None
    practice_address: Optional[str] = None
    practice_city: Optional[str] = None
    practice_state: Optional[str] = None
    practice_zip: Optional[str] = None
    
    # Professional
    specialty: str  # Free text - any value allowed
    credentials: Optional[str] = None
    
    # Status & Preferences
    status: ProviderStatus
    preferred_contact: Optional[ProviderContactMethod] = None
    send_referral_updates: bool = True
    
    # Metrics
    total_referrals: int = 0
    converted_referrals: int = 0
    conversion_rate: float = 0.0
    last_referral_at: Optional[datetime] = None
    
    # Notes & Tags
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    verified_at: Optional[datetime] = None

    model_config = {
        "from_attributes": True
    }


class ProviderListResponse(BaseModel):
    """
    Schema for provider list items (minimal data for table display).
    Used in dashboard provider table for performance.
    """
    
    id: UUID
    name: str
    email: Optional[str] = None  # Added: Provider email for table display
    practice_name: Optional[str] = None
    specialty: str  # Free text - any value allowed
    status: ProviderStatus
    total_referrals: int = 0
    converted_referrals: int = 0
    conversion_rate: float = 0.0
    last_referral_at: Optional[datetime] = None

    model_config = {
        "from_attributes": True
    }


class ProviderSummary(BaseModel):
    """
    Minimal provider info for embedding in lead responses.
    """
    
    id: UUID
    name: str
    practice_name: Optional[str] = None
    specialty: str  # Free text - any value allowed
    status: ProviderStatus

    model_config = {
        "from_attributes": True
    }


# =============================================================================
# Provider Stats Schema
# =============================================================================

class ProviderDashboardStats(BaseModel):
    """
    Dashboard summary statistics for providers.
    """
    
    total_providers: int = Field(
        ...,
        description="Total number of providers in the system"
    )
    active_providers: int = Field(
        ...,
        description="Number of providers with ACTIVE status"
    )
    pending_providers: int = Field(
        ...,
        description="Number of providers awaiting verification"
    )
    total_referrals: int = Field(
        ...,
        description="Total number of referral leads"
    )
    converted_referrals: int = Field(
        ...,
        description="Number of referrals that converted"
    )
    overall_conversion_rate: float = Field(
        ...,
        description="Overall referral conversion rate (%)"
    )
    referrals_this_month: int = Field(
        ...,
        description="Referrals received this month"
    )
    top_providers: List[ProviderListResponse] = Field(
        default=[],
        description="Top 5 providers by referral count"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "total_providers": 25,
                "active_providers": 20,
                "pending_providers": 5,
                "total_referrals": 150,
                "converted_referrals": 75,
                "overall_conversion_rate": 50.0,
                "referrals_this_month": 12,
                "top_providers": []
            }
        }
    }


# =============================================================================
# Referral Lead Info (for provider detail view)
# =============================================================================

class ProviderReferralLeadInfo(BaseModel):
    """
    Minimal lead info for provider's referral list.
    Does NOT include PHI - only aggregated data.
    """
    
    id: UUID
    lead_number: str
    condition: str
    priority: str
    status: str
    created_at: datetime
    is_converted: bool = False

    model_config = {
        "from_attributes": True
    }


# =============================================================================
# Provider Auto-Match Result
# =============================================================================

class ProviderMatchResult(BaseModel):
    """
    Result from provider matching/lookup.
    Used when processing Jotform referrals.
    """
    
    found: bool = Field(
        ...,
        description="Whether a matching provider was found"
    )
    provider_id: Optional[UUID] = Field(
        default=None,
        description="ID of matched or created provider"
    )
    match_type: Optional[str] = Field(
        default=None,
        description="How the provider was matched (email, npi, fuzzy, created)"
    )
    confidence: float = Field(
        default=0.0,
        description="Match confidence score (0-1)"
    )
    is_new: bool = Field(
        default=False,
        description="Whether a new provider was created"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "found": True,
                "provider_id": "123e4567-e89b-12d3-a456-426614174000",
                "match_type": "email",
                "confidence": 1.0,
                "is_new": False
            }
        }
    }
