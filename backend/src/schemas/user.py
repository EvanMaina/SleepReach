"""
Pydantic schemas for user management and authentication.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


# =============================================================================
# User CRUD (defined first — referenced by auth responses below)
# =============================================================================


class UserCreate(BaseModel):
    """Admin-only: create a new user.  Password is generated server-side."""
    email: EmailStr
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    role: str = Field(..., pattern="^(primary_admin|administrator|coordinator|specialist)$")


class UserUpdate(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    role: Optional[str] = Field(None, pattern="^(primary_admin|administrator|coordinator|specialist)$")
    status: Optional[str] = Field(None, pattern="^(active|inactive|pending)$")


class UserResponse(BaseModel):
    id: UUID
    email: str
    first_name: str
    last_name: str
    role: str
    status: str
    must_change_password: bool
    last_login: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    items: List[UserResponse]
    total: int


# =============================================================================
# Auth Request / Response
# =============================================================================


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse
    must_change_password: bool


class ChangePasswordRequest(BaseModel):
    current_password: Optional[str] = None  # None allowed on forced first-login change
    new_password: str = Field(..., min_length=8)


class ChangePasswordResponse(BaseModel):
    success: bool
    message: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    success: bool
    message: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)


class ResetPasswordResponse(BaseModel):
    success: bool
    message: str


class ValidateResetTokenResponse(BaseModel):
    valid: bool
    message: str


class MeResponse(BaseModel):
    user: UserResponse
    permissions: List[str]


# =============================================================================
# Preferences
# =============================================================================


class PreferencesResponse(BaseModel):
    notify_new_lead: bool
    notify_hot_lead: bool
    notify_daily_summary: bool


class PreferencesUpdate(BaseModel):
    notify_new_lead: Optional[bool] = None
    notify_hot_lead: Optional[bool] = None
    notify_daily_summary: Optional[bool] = None


# =============================================================================
# Clinic Settings
# =============================================================================


class ClinicSettingsResponse(BaseModel):
    clinic_name: str
    clinic_address: str
    clinic_phone: str
    clinic_email: str


class ClinicSettingsUpdate(BaseModel):
    clinic_name: Optional[str] = None
    clinic_address: Optional[str] = None
    clinic_phone: Optional[str] = None
    clinic_email: Optional[str] = None
