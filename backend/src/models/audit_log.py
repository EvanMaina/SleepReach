"""
Audit log database model.

Tracks all PHI access for HIPAA compliance.
Every access to patient data must be logged here.
"""

import enum
from datetime import datetime
from typing import Optional, Any
from uuid import UUID

from sqlalchemy import Column, String, Boolean, Text, DateTime, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.sql import func

from ..core.database import Base


# =============================================================================
# Enum Definitions
# =============================================================================

class AuditAction(str, enum.Enum):
    """Types of auditable actions."""
    CREATE = "CREATE"
    READ = "READ"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    EXPORT = "EXPORT"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"


# =============================================================================
# Audit Log Model
# =============================================================================

class AuditLog(Base):
    """
    HIPAA-compliant audit log model.
    
    Tracks all access to Protected Health Information (PHI).
    Required for HIPAA compliance and security auditing.
    
    Attributes:
        id: UUID primary key
        table_name: Name of table accessed
        record_id: ID of specific record accessed
        action: Type of action performed
        user_id: ID of user who performed action
        user_email: Email of user (for audit trail)
        user_ip_hash: Hashed IP address
        endpoint: API endpoint accessed
        request_method: HTTP method used
        old_values: Previous values (for updates)
        new_values: New values (for creates/updates)
        success: Whether action succeeded
        error_message: Error message if failed
        created_at: Timestamp of action
    """
    
    __tablename__ = "audit_logs"
    
    # Primary key
    id = Column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
        nullable=False,
    )
    
    # What was accessed
    table_name = Column(String(100), nullable=False, index=True)
    record_id = Column(PGUUID(as_uuid=True), nullable=False, index=True)
    action = Column(
        SQLEnum(AuditAction, name="audit_action", create_type=False),
        nullable=False,
        index=True,
    )
    
    # Who accessed it
    user_id = Column(PGUUID(as_uuid=True), nullable=True, index=True)  # Future: FK to users
    user_email = Column(String(255), nullable=True)
    user_ip_hash = Column(String(64), nullable=True)
    
    # Context
    endpoint = Column(String(255), nullable=True)
    request_method = Column(String(10), nullable=True)
    user_agent = Column(Text, nullable=True)
    
    # What changed (for UPDATE actions)
    # IMPORTANT: Never store actual PHI values here, only field names
    old_values = Column(JSONB, nullable=True)
    new_values = Column(JSONB, nullable=True)
    
    # Result
    success = Column(Boolean, nullable=False, default=True)
    error_message = Column(Text, nullable=True)
    
    # Timestamp
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        index=True,
    )
    
    def __repr__(self) -> str:
        """String representation of audit log entry."""
        return (
            f"<AuditLog(id={self.id}, "
            f"table={self.table_name}, "
            f"action={self.action.value}, "
            f"record_id={self.record_id})>"
        )
    
    @classmethod
    def create_entry(
        cls,
        table_name: str,
        record_id: UUID,
        action: AuditAction,
        user_id: Optional[UUID] = None,
        user_email: Optional[str] = None,
        user_ip_hash: Optional[str] = None,
        endpoint: Optional[str] = None,
        request_method: Optional[str] = None,
        user_agent: Optional[str] = None,
        old_values: Optional[dict[str, Any]] = None,
        new_values: Optional[dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> "AuditLog":
        """
        Factory method to create an audit log entry.
        
        Args:
            table_name: Name of table being accessed
            record_id: UUID of record being accessed
            action: Type of action (CREATE, READ, UPDATE, DELETE, etc.)
            user_id: Optional UUID of user performing action
            user_email: Optional email of user
            user_ip_hash: Optional hashed IP address
            endpoint: Optional API endpoint
            request_method: Optional HTTP method
            user_agent: Optional user agent string
            old_values: Optional dict of previous values (no PHI!)
            new_values: Optional dict of new values (no PHI!)
            success: Whether action succeeded
            error_message: Optional error message if failed
            
        Returns:
            New AuditLog instance (not saved to DB)
            
        Note:
            NEVER include actual PHI values in old_values or new_values.
            Only include field names or [REDACTED] for sensitive fields.
        """
        return cls(
            table_name=table_name,
            record_id=record_id,
            action=action,
            user_id=user_id,
            user_email=user_email,
            user_ip_hash=user_ip_hash,
            endpoint=endpoint,
            request_method=request_method,
            user_agent=user_agent,
            old_values=old_values,
            new_values=new_values,
            success=success,
            error_message=error_message,
        )
