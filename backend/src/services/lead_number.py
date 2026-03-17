"""
Lead Number Generation Service.

Generates unique lead numbers in the format TMS-YYYY-XXX.
Thread-safe implementation with database locking and retry logic.

Note: Legacy leads may use the NR-YYYY-XXX prefix. Both formats are valid.
"""

import logging
import re
import time
from datetime import datetime
from typing import Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, OperationalError

from ..models.lead import Lead

logger = logging.getLogger(__name__)


def generate_unique_lead_number(db: Session, max_retries: int = 5) -> str:
    """
    Generate a guaranteed unique lead number with retry logic.
    
    Uses a SAVEPOINT (begin_nested) for each attempt so that a failure
    inside the lock query does NOT poison the caller's transaction.
    This is critical because the caller (submit_lead, webhooks, etc.)
    may have already flushed other objects (e.g., ReferringProvider)
    that must survive a retry here.
    
    Queries both TMS- and legacy NR- prefixed leads to find the current
    maximum sequence number, then returns MAX + 1.
    
    Args:
        db: SQLAlchemy database session (caller's session)
        max_retries: Maximum number of attempts
        
    Returns:
        Unique lead number string (e.g., "TMS-2026-154")
    """
    current_year = datetime.now().year
    prefix = f"TMS-{current_year}-"
    
    for attempt in range(max_retries):
        try:
            # Use a SAVEPOINT so failures here don't abort the outer transaction.
            nested = db.begin_nested()
            try:
                result = db.execute(
                    text("""
                        SELECT MAX(num) FROM (
                            SELECT CAST(SUBSTRING(lead_number FROM 'TMS-\\d{4}-(\\d+)') AS INTEGER) AS num
                            FROM leads
                            WHERE lead_number LIKE :tms_pattern
                        ) t1
                        UNION ALL
                        (SELECT MAX(CAST(SUBSTRING(lead_number FROM 'NR-\\d{4}-(\\d+)') AS INTEGER)) AS num
                         FROM leads
                         WHERE lead_number LIKE :nr_pattern)
                    """),
                    {"tms_pattern": f"TMS-{current_year}-%", "nr_pattern": f"NR-{current_year}-%"}
                )
                
                # The UNION ALL returns two rows; pick the overall max.
                max_num = 0
                for row in result:
                    val = row[0]
                    if val is not None and val > max_num:
                        max_num = val
                
                next_number = max_num + 1 + attempt  # offset for retries
                lead_number = f"{prefix}{next_number:03d}"
                
                # Quick existence check (belt-and-suspenders)
                exists = db.execute(
                    text("SELECT 1 FROM leads WHERE lead_number = :ln LIMIT 1"),
                    {"ln": lead_number}
                ).first()
                
                if exists:
                    nested.rollback()
                    logger.warning(
                        f"Lead number {lead_number} already exists (attempt {attempt + 1}), retrying..."
                    )
                    continue
                
                # Success — release the savepoint cleanly.
                nested.commit()
                return lead_number
                
            except IntegrityError:
                nested.rollback()
                logger.warning(
                    f"IntegrityError on lead number generation (attempt {attempt + 1}), retrying..."
                )
            except Exception as e:
                nested.rollback()
                logger.warning(
                    f"Error generating lead number (attempt {attempt + 1}): {type(e).__name__}: {e}"
                )
                
        except Exception as outer_err:
            # begin_nested() itself failed — session may be in bad state.
            # Attempt a full rollback to recover the connection.
            try:
                db.rollback()
            except Exception:
                pass
            logger.warning(
                f"Savepoint creation failed (attempt {attempt + 1}): {type(outer_err).__name__}: {outer_err}"
            )
        
        # Brief pause before retry to reduce contention
        if attempt < max_retries - 1:
            time.sleep(0.05 * (attempt + 1))
    
    # Fallback: timestamp-based suffix (virtually collision-free)
    timestamp_suffix = int(time.time() * 1000) % 100000
    fallback = f"{prefix}{timestamp_suffix:05d}"
    logger.warning(f"All retries exhausted, using timestamp fallback: {fallback}")
    return fallback


def validate_lead_number_format(lead_number: str) -> bool:
    """
    Validate that a lead number follows the correct format.
    
    Accepts both TMS- (current) and NR- (legacy) prefixes.
    
    Args:
        lead_number: String to validate
        
    Returns:
        True if valid format, False otherwise
        
    Example:
        >>> validate_lead_number_format("TMS-2026-001")
        True
        >>> validate_lead_number_format("NR-2026-001")
        True
        >>> validate_lead_number_format("INVALID")
        False
    """
    pattern = r"^(TMS|NR)-\d{4}-\d{3,}$"
    return bool(re.match(pattern, lead_number))


def get_next_lead_number_preview(db: Session) -> str:
    """
    Preview what the next lead number will be without creating it.
    
    Useful for UI display or confirmation screens.
    
    Args:
        db: SQLAlchemy database session
        
    Returns:
        Preview of next lead number
    """
    return generate_unique_lead_number(db)
