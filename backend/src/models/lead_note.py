"""
Lead notes model.

The live SleepReach database still uses the original `lead_notes` table shape
(`content`, `user_id`, `user_name`, `is_system`). This model maps to that
schema while exposing compatibility properties used by the newer API and UI.
"""

import re

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..core.database import Base


class LeadNote(Base):
    """Immutable note entry tied to a lead."""

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

    content = Column(Text, nullable=False)
    user_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_name = Column(String(200), nullable=False, default="System")
    is_system = Column(Boolean, nullable=False, default=False)

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

    lead = relationship("Lead", backref="lead_notes", foreign_keys=[lead_id])
    author = relationship("User", foreign_keys=[user_id], lazy="joined")

    _OUTCOME_PATTERN = re.compile(
        r"^(?:Outcome recorded|Consultation outcome):\s*([A-Za-z_ ]+)"
    )

    @property
    def note_text(self) -> str:
        return self.content

    @note_text.setter
    def note_text(self, value: str) -> None:
        self.content = value

    @property
    def created_by(self):
        return self.user_id

    @created_by.setter
    def created_by(self, value) -> None:
        self.user_id = value

    @property
    def created_by_name(self) -> str:
        return self.user_name or "System"

    @created_by_name.setter
    def created_by_name(self, value: str) -> None:
        self.user_name = value or "System"

    @property
    def note_type(self) -> str:
        if self.is_system:
            return "system"
        if self.related_outcome:
            return "outcome"
        return "manual"

    @note_type.setter
    def note_type(self, value: str) -> None:
        self.is_system = (value or "").lower() == "system"

    @property
    def related_outcome(self):
        match = self._OUTCOME_PATTERN.match((self.content or "").strip())
        if not match:
            return None
        return match.group(1).strip().upper().replace(" ", "_")

    @related_outcome.setter
    def related_outcome(self, value) -> None:
        # Compatibility no-op: outcome context is embedded in `content`.
        return None

    def __repr__(self) -> str:
        return (
            f"<LeadNote(id={self.id}, lead_id={self.lead_id}, "
            f"type={self.note_type}, by={self.created_by_name})>"
        )
