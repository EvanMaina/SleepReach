"""
Database transaction management utilities.

Provides context managers and decorators for safe database transactions
with automatic rollback on error.

Usage:
    with transaction(db):
        # Multiple database operations
        # All succeed or all roll back
        db.add(obj1)
        db.add(obj2)
        # Automatically commits on success, rolls back on error
"""

import logging
from contextlib import contextmanager
from typing import Generator
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError


logger = logging.getLogger(__name__)


@contextmanager
def transaction(db: Session) -> Generator[Session, None, None]:
    """
    Context manager for database transactions with automatic rollback.
    
    Ensures that all database operations within the context succeed together
    or all fail together. Automatically commits on success, rolls back on error.
    
    Args:
        db: SQLAlchemy database session
        
    Yields:
        The same database session
        
    Raises:
        Any exception raised within the context
        
    Example:
        ```python
        with transaction(db):
            db.add(lead)
            db.add(schedule)
            # Both succeed or both roll back
        ```
    """
    try:
        yield db
        db.commit()
        logger.debug("✅ Transaction committed successfully")
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Transaction rolled back due to error: {e}")
        raise


@contextmanager
def nested_transaction(db: Session) -> Generator[Session, None, None]:
    """
    Context manager for nested transactions (savepoints).
    
    Creates a savepoint that can be rolled back independently of the outer transaction.
    Useful for partial rollbacks in complex operations.
    
    Args:
        db: SQLAlchemy database session
        
    Yields:
        The same database session
        
    Example:
        ```python
        with transaction(db):
            db.add(lead)
            try:
                with nested_transaction(db):
                    db.add(risky_operation)
                    # This might fail
            except Exception:
                # Risky operation rolled back, but lead is still queued
                pass
            # Lead is still committed
        ```
    """
    savepoint = db.begin_nested()
    try:
        yield db
        savepoint.commit()
        logger.debug("✅ Nested transaction committed successfully")
    except Exception as e:
        savepoint.rollback()
        logger.error(f"❌ Nested transaction rolled back due to error: {e}")
        raise


def safe_commit(db: Session) -> bool:
    """
    Safely commit a database session with error handling.
    
    Returns True on success, False on error (with automatic rollback).
    Useful for non-critical operations where you want to continue on error.
    
    Args:
        db: SQLAlchemy database session
        
    Returns:
        True if commit succeeded, False if it failed
        
    Example:
        ```python
        db.add(log_entry)
        if not safe_commit(db):
            # Log to file instead
            pass
        ```
    """
    try:
        db.commit()
        return True
    except SQLAlchemyError as e:
        logger.error(f"❌ Commit failed: {e}")
        db.rollback()
        return False


def safe_rollback(db: Session) -> None:
    """
    Safely roll back a database session with error handling.
    
    Catches and logs any errors during rollback to prevent
    double-exception scenarios.
    
    Args:
        db: SQLAlchemy database session
    """
    try:
        db.rollback()
    except Exception as e:
        logger.error(f"❌ Rollback failed: {e}")


class TransactionError(Exception):
    """Custom exception for transaction-related errors."""
    pass
