"""
User and related models for authentication and user management.
"""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, String, Boolean, DateTime, Enum as SQLEnum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from ..core.database import Base


# =============================================================================
# Enums
# =============================================================================


class UserRole(str, enum.Enum):
    PRIMARY_ADMIN = "primary_admin"
    ADMINISTRATOR = "administrator"
    COORDINATOR = "coordinator"
    SPECIALIST = "specialist"


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"


# =============================================================================
# Permission Map
# =============================================================================

# Centralised permission definitions.  Keys are action identifiers used by
# both backend route guards and (via the /api/auth/me response) the frontend.
ROLE_PERMISSIONS: dict[UserRole, set[str]] = {
    UserRole.PRIMARY_ADMIN: {
        "view_dashboard",
        "view_coordinator",
        "view_leads",
        "view_providers",
        "view_analytics",
        "view_settings",
        "edit_leads",
        "delete_leads",
        "manage_users",
        "manage_admins",
        "make_calls",
        "schedule_callbacks",
    },
    UserRole.ADMINISTRATOR: {
        "view_dashboard",
        "view_coordinator",
        "view_leads",
        "view_providers",
        "view_analytics",
        "view_settings",
        "edit_leads",
        "delete_leads",
        "manage_users",
        "make_calls",
        "schedule_callbacks",
    },
    UserRole.COORDINATOR: {
        "view_dashboard",
        "view_coordinator",
        "view_leads",
        "view_providers",
        "view_analytics",
        "edit_leads",
        "make_calls",
        "schedule_callbacks",
    },
    UserRole.SPECIALIST: {
        "view_dashboard",
        "view_coordinator",
        "view_leads",
        "view_providers",
        "make_calls",
        "schedule_callbacks",
    },
}


def get_permissions_for_role(role: UserRole) -> list[str]:
    return sorted(ROLE_PERMISSIONS.get(role, set()))


# =============================================================================
# User Model
# =============================================================================


class User(Base):
    __tablename__ = "users"

    id = Column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    role = Column(SQLEnum(UserRole, name="user_role", create_type=False, values_callable=lambda e: [x.value for x in e]), nullable=False, default=UserRole.COORDINATOR)
    status = Column(SQLEnum(UserStatus, name="user_status", create_type=False, values_callable=lambda e: [x.value for x in e]), nullable=False, default=UserStatus.PENDING)
    must_change_password = Column(Boolean, nullable=False, default=True)
    password_expires_at = Column(DateTime(timezone=True), nullable=True)
    last_login = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    # Relationship to preferences
    preferences = relationship("UserPreferences", uselist=False, back_populates="user", lazy="joined")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def permissions(self) -> list[str]:
        return get_permissions_for_role(self.role)

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, role={self.role.value})>"


# =============================================================================
# UserPreferences Model
# =============================================================================


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    notify_new_lead = Column(Boolean, nullable=False, default=True)
    notify_hot_lead = Column(Boolean, nullable=False, default=True)
    notify_daily_summary = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    user = relationship("User", back_populates="preferences")


# =============================================================================
# ClinicSettings Model
# =============================================================================


class PasswordResetToken(Base):
    """Stores hashed password reset tokens with expiry and one-time-use semantics."""
    __tablename__ = "password_reset_tokens"

    id = Column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(255), nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp())

    user = relationship("User", lazy="joined")

    @property
    def is_expired(self) -> bool:
        from datetime import datetime, timezone as tz
        return datetime.now(tz.utc) > self.expires_at

    @property
    def is_used(self) -> bool:
        return self.used_at is not None

    def __repr__(self) -> str:
        return f"<PasswordResetToken(id={self.id}, user_id={self.user_id}, expired={self.is_expired}, used={self.is_used})>"


class ClinicSettings(Base):
    __tablename__ = "clinic_settings"

    key = Column(String(100), primary_key=True)
    value = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
