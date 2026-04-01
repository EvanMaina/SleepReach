"""
Lead attachment database model.

Stores metadata for documents attached to leads while the file bytes live on
disk under backend/static/attachments/.
"""

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..core.database import Base


class LeadAttachment(Base):
    """File attachment linked to a lead."""

    __tablename__ = "lead_attachments"

    id = Column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
        nullable=False,
    )

    lead_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    filename = Column(String(500), nullable=False)
    stored_filename = Column(String(500), nullable=False)
    file_type = Column(String(100), nullable=False)
    file_size = Column(BigInteger, nullable=False, default=0)
    uploaded_by = Column(String(255), nullable=True)
    uploaded_by_id = Column(PGUUID(as_uuid=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    lead = relationship("Lead", backref="attachments", foreign_keys=[lead_id])

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "lead_id": str(self.lead_id),
            "filename": self.filename,
            "stored_filename": self.stored_filename,
            "file_type": self.file_type,
            "file_size": self.file_size,
            "uploaded_by": self.uploaded_by,
            "uploaded_by_id": str(self.uploaded_by_id) if self.uploaded_by_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
