"""
Lead Notes model for coordinator-specialist handoff.

Each note is an immutable log entry tied to a lead.
Notes are never overwritten — they form a chronological conversation history.
"""

from datetime import datetime

from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from ..core.database import Base


class LeadNote(Base):
    """
    Individual note entry for a lead.
    
    Supports:
    - Manual notes added by coordinators in Lead Details
    - Outcome notes captured during quick action / consultation panels
    - System-generated notes for audit trail
    """
    
    __tablename__ = "lead_notes"
    
    id = Column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
        nullable=False,
    )
    
    lead_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    note_text = Column(Text, nullable=False)
    
    # Who wrote it (FK to users table, nullable for system-generated notes)
    created_by = Column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Denormalized name for display without joining users table
    created_by_name = Column(String(200), nullable=False, default="System")
    
    # Note context type: manual, outcome, schedule, system
    note_type = Column(String(50), nullable=False, default="manual")
    
    # Optional: which outcome triggered this note (e.g., "NO_ANSWER", "NOT_INTERESTED")
    related_outcome = Column(String(50), nullable=True)
    
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )
    
    # Relationships
    lead = relationship("Lead", backref="lead_notes", foreign_keys=[lead_id])
    author = relationship("User", foreign_keys=[created_by], lazy="joined")
    
    def __repr__(self) -> str:
        return (
            f"<LeadNote(id={self.id}, lead_id={self.lead_id}, "
            f"type={self.note_type}, by={self.created_by_name})>"
        )
