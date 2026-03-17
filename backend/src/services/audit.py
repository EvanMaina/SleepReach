"""
Audit logging service for HIPAA compliance.

Tracks all access to Protected Health Information (PHI).
Required for HIPAA compliance and security auditing.
"""

from typing import Optional, Any
from uuid import UUID

from sqlalchemy.orm import Session

from ..models.audit_log import AuditLog, AuditAction
from ..core.security import hash_ip_address


class AuditService:
    """
    Service for creating HIPAA-compliant audit logs.
    
    Every access to PHI must be logged through this service.
    Logs are immutable and retained for compliance purposes.
    
    Example usage:
        audit = AuditService(db)
        audit.log_create("leads", lead.id, user_id=current_user.id)
        audit.log_read("leads", lead.id, user_id=current_user.id)
    """
    
    def __init__(self, db: Session):
        """
        Initialize audit service with database session.
        
        Args:
            db: SQLAlchemy session for database operations
        """
        self.db = db
    
    def _create_log_entry(
        self,
        table_name: str,
        record_id: UUID,
        action: AuditAction,
        user_id: Optional[UUID] = None,
        user_email: Optional[str] = None,
        ip_address: Optional[str] = None,
        endpoint: Optional[str] = None,
        request_method: Optional[str] = None,
        user_agent: Optional[str] = None,
        old_values: Optional[dict[str, Any]] = None,
        new_values: Optional[dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> AuditLog:
        """
        Create and persist an audit log entry.
        
        Args:
            table_name: Name of table being accessed
            record_id: UUID of record being accessed
            action: Type of action performed
            user_id: Optional ID of user performing action
            user_email: Optional email of user
            ip_address: Optional IP address (will be hashed)
            endpoint: Optional API endpoint
            request_method: Optional HTTP method
            user_agent: Optional user agent string
            old_values: Optional dict of previous values (NO PHI!)
            new_values: Optional dict of new values (NO PHI!)
            success: Whether action succeeded
            error_message: Optional error message if failed
            
        Returns:
            Created AuditLog instance
        """
        # Hash IP address for privacy
        ip_hash = hash_ip_address(ip_address) if ip_address else None
        
        # Create audit log entry
        audit_log = AuditLog.create_entry(
            table_name=table_name,
            record_id=record_id,
            action=action,
            user_id=user_id,
            user_email=user_email,
            user_ip_hash=ip_hash,
            endpoint=endpoint,
            request_method=request_method,
            user_agent=user_agent,
            old_values=old_values,
            new_values=new_values,
            success=success,
            error_message=error_message,
        )
        
        # Persist to database
        self.db.add(audit_log)
        self.db.commit()
        self.db.refresh(audit_log)
        
        return audit_log
    
    def log_create(
        self,
        table_name: str,
        record_id: UUID,
        user_id: Optional[UUID] = None,
        user_email: Optional[str] = None,
        ip_address: Optional[str] = None,
        endpoint: Optional[str] = None,
        request_method: Optional[str] = None,
        user_agent: Optional[str] = None,
        new_values: Optional[dict[str, Any]] = None,
    ) -> AuditLog:
        """
        Log a CREATE action (new record created).
        
        Args:
            table_name: Name of table where record was created
            record_id: UUID of new record
            user_id: Optional ID of user who created record
            user_email: Optional email of user
            ip_address: Optional IP address of request
            endpoint: Optional API endpoint
            request_method: Optional HTTP method
            user_agent: Optional user agent string
            new_values: Optional dict of field names (NO PHI values!)
            
        Returns:
            Created AuditLog instance
        """
        return self._create_log_entry(
            table_name=table_name,
            record_id=record_id,
            action=AuditAction.CREATE,
            user_id=user_id,
            user_email=user_email,
            ip_address=ip_address,
            endpoint=endpoint,
            request_method=request_method,
            user_agent=user_agent,
            new_values=new_values,
        )
    
    def log_read(
        self,
        table_name: str,
        record_id: UUID,
        user_id: Optional[UUID] = None,
        user_email: Optional[str] = None,
        ip_address: Optional[str] = None,
        endpoint: Optional[str] = None,
        request_method: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditLog:
        """
        Log a READ action (record accessed).
        
        Args:
            table_name: Name of table where record was read
            record_id: UUID of record that was read
            user_id: Optional ID of user who read record
            user_email: Optional email of user
            ip_address: Optional IP address of request
            endpoint: Optional API endpoint
            request_method: Optional HTTP method
            user_agent: Optional user agent string
            
        Returns:
            Created AuditLog instance
        """
        return self._create_log_entry(
            table_name=table_name,
            record_id=record_id,
            action=AuditAction.READ,
            user_id=user_id,
            user_email=user_email,
            ip_address=ip_address,
            endpoint=endpoint,
            request_method=request_method,
            user_agent=user_agent,
        )
    
    def log_update(
        self,
        table_name: str,
        record_id: UUID,
        user_id: Optional[UUID] = None,
        user_email: Optional[str] = None,
        ip_address: Optional[str] = None,
        endpoint: Optional[str] = None,
        request_method: Optional[str] = None,
        user_agent: Optional[str] = None,
        old_values: Optional[dict[str, Any]] = None,
        new_values: Optional[dict[str, Any]] = None,
    ) -> AuditLog:
        """
        Log an UPDATE action (record modified).
        
        IMPORTANT: old_values and new_values should contain field NAMES only,
        not actual PHI values. Use [REDACTED] for sensitive fields.
        
        Args:
            table_name: Name of table where record was updated
            record_id: UUID of record that was updated
            user_id: Optional ID of user who updated record
            user_email: Optional email of user
            ip_address: Optional IP address of request
            endpoint: Optional API endpoint
            request_method: Optional HTTP method
            user_agent: Optional user agent string
            old_values: Optional dict of changed field names (NO PHI!)
            new_values: Optional dict of changed field names (NO PHI!)
            
        Returns:
            Created AuditLog instance
        """
        return self._create_log_entry(
            table_name=table_name,
            record_id=record_id,
            action=AuditAction.UPDATE,
            user_id=user_id,
            user_email=user_email,
            ip_address=ip_address,
            endpoint=endpoint,
            request_method=request_method,
            user_agent=user_agent,
            old_values=old_values,
            new_values=new_values,
        )
    
    def log_delete(
        self,
        table_name: str,
        record_id: UUID,
        user_id: Optional[UUID] = None,
        user_email: Optional[str] = None,
        ip_address: Optional[str] = None,
        endpoint: Optional[str] = None,
        request_method: Optional[str] = None,
        user_agent: Optional[str] = None,
        new_values: Optional[dict[str, Any]] = None,
        deleted_data: Optional[dict[str, Any]] = None,
    ) -> AuditLog:
        """
        Log a DELETE action (record removed).

        Args:
            table_name: Name of table where record was deleted
            record_id: UUID of record that was deleted
            user_id: Optional ID of user who deleted record
            user_email: Optional email of user
            ip_address: Optional IP address of request
            endpoint: Optional API endpoint
            request_method: Optional HTTP method
            user_agent: Optional user agent string
            new_values: Optional dict of deletion metadata (NO PHI!)
            deleted_data: Alias for new_values (backward compat — callers may pass either)

        Returns:
            Created AuditLog instance
        """
        # Accept either `new_values` or the legacy `deleted_data` kwarg so
        # existing callers don't need to be changed simultaneously.
        _new_values = new_values or deleted_data
        return self._create_log_entry(
            table_name=table_name,
            record_id=record_id,
            action=AuditAction.DELETE,
            user_id=user_id,
            user_email=user_email,
            ip_address=ip_address,
            endpoint=endpoint,
            request_method=request_method,
            user_agent=user_agent,
            new_values=_new_values,
        )
    
    def log_export(
        self,
        table_name: str,
        record_id: UUID,
        user_id: Optional[UUID] = None,
        user_email: Optional[str] = None,
        ip_address: Optional[str] = None,
        endpoint: Optional[str] = None,
        request_method: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditLog:
        """
        Log an EXPORT action (data exported).
        
        Args:
            table_name: Name of table from which data was exported
            record_id: UUID of record that was exported
            user_id: Optional ID of user who exported data
            user_email: Optional email of user
            ip_address: Optional IP address of request
            endpoint: Optional API endpoint
            request_method: Optional HTTP method
            user_agent: Optional user agent string
            
        Returns:
            Created AuditLog instance
        """
        return self._create_log_entry(
            table_name=table_name,
            record_id=record_id,
            action=AuditAction.EXPORT,
            user_id=user_id,
            user_email=user_email,
            ip_address=ip_address,
            endpoint=endpoint,
            request_method=request_method,
            user_agent=user_agent,
        )
    
    def log_error(
        self,
        table_name: str,
        record_id: UUID,
        action: AuditAction,
        error_message: str,
        user_id: Optional[UUID] = None,
        user_email: Optional[str] = None,
        ip_address: Optional[str] = None,
        endpoint: Optional[str] = None,
        request_method: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditLog:
        """
        Log a failed action attempt.
        
        Args:
            table_name: Name of table that was being accessed
            record_id: UUID of record that was being accessed
            action: Type of action that was attempted
            error_message: Description of the error (NO PHI!)
            user_id: Optional ID of user who attempted action
            user_email: Optional email of user
            ip_address: Optional IP address of request
            endpoint: Optional API endpoint
            request_method: Optional HTTP method
            user_agent: Optional user agent string
            
        Returns:
            Created AuditLog instance
        """
        return self._create_log_entry(
            table_name=table_name,
            record_id=record_id,
            action=action,
            user_id=user_id,
            user_email=user_email,
            ip_address=ip_address,
            endpoint=endpoint,
            request_method=request_method,
            user_agent=user_agent,
            success=False,
            error_message=error_message,
        )


def create_audit_service(db: Session) -> AuditService:
    """
    Factory function to create audit service.
    
    Args:
        db: SQLAlchemy session
        
    Returns:
        AuditService instance
    """
    return AuditService(db)
