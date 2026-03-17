"""
Lead Notes API endpoints.

Provides CRUD operations for coordinator notes on leads.
Notes form a chronological log for coordinator-specialist handoff.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc

from ..core.database import get_db
from ..core.auth import get_current_user, require_role
from ..models.lead import Lead
from ..models.lead_note import LeadNote
from ..models.user import User


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/leads", tags=["Lead Notes"])


# =============================================================================
# Schemas
# =============================================================================

class CreateNoteRequest(BaseModel):
    """Request body for creating a new note."""
    note_text: str = Field(..., min_length=1, max_length=5000, description="Note content")
    note_type: str = Field(default="manual", description="Note type: manual, outcome, schedule, system")
    related_outcome: Optional[str] = Field(default=None, description="Related contact outcome if applicable")


class NoteResponse(BaseModel):
    """Response schema for a single note."""
    id: str
    lead_id: str
    note_text: str
    created_by: Optional[str] = None
    created_by_name: str
    note_type: str
    related_outcome: Optional[str] = None
    created_at: str

    model_config = {"from_attributes": True}


# =============================================================================
# Endpoints
# =============================================================================

@router.get(
    "/{lead_id}/notes",
    response_model=List[NoteResponse],
    summary="Get Lead Notes",
    description="Get all notes for a lead in reverse chronological order.",
    dependencies=[Depends(get_current_user)],
)
async def get_lead_notes(
    lead_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> List[NoteResponse]:
    """
    Get all notes for a lead, newest first.
    
    Args:
        lead_id: UUID of the lead
        request: FastAPI request
        db: Database session
    
    Returns:
        List of notes in reverse chronological order
    """
    # Verify lead exists
    lead = db.query(Lead).filter(
        Lead.id == lead_id,
        Lead.deleted_at.is_(None)
    ).first()
    
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )
    
    # Fetch notes
    notes = (
        db.query(LeadNote)
        .filter(LeadNote.lead_id == lead_id)
        .order_by(desc(LeadNote.created_at))
        .all()
    )
    
    return [
        NoteResponse(
            id=str(note.id),
            lead_id=str(note.lead_id),
            note_text=note.note_text,
            created_by=str(note.created_by) if note.created_by else None,
            created_by_name=note.created_by_name or "System",
            note_type=note.note_type or "manual",
            related_outcome=note.related_outcome,
            created_at=note.created_at.isoformat() if note.created_at else datetime.now(timezone.utc).isoformat(),
        )
        for note in notes
    ]


@router.post(
    "/{lead_id}/notes",
    response_model=NoteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add Lead Note",
    description="Add a new note to a lead. Notes are append-only.",
    dependencies=[Depends(require_role("administrator", "coordinator", "specialist"))],
)
async def create_lead_note(
    lead_id: UUID,
    note_data: CreateNoteRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NoteResponse:
    """
    Create a new note for a lead.
    
    Notes are immutable once created — they can only be appended, never edited or deleted.
    This ensures a reliable audit trail for clinical handoffs.
    
    Args:
        lead_id: UUID of the lead
        note_data: Note content and metadata
        request: FastAPI request
        db: Database session
        current_user: Authenticated user
    
    Returns:
        Created note
    """
    # Verify lead exists
    lead = db.query(Lead).filter(
        Lead.id == lead_id,
        Lead.deleted_at.is_(None)
    ).first()
    
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )
    
    try:
        # Create note
        note = LeadNote(
            lead_id=lead_id,
            note_text=note_data.note_text.strip(),
            created_by=current_user.id,
            created_by_name=current_user.full_name,
            note_type=note_data.note_type or "manual",
            related_outcome=note_data.related_outcome,
        )
        
        db.add(note)
        
        # Update lead's last_updated_at timestamp
        lead.last_updated_at = datetime.now(timezone.utc)
        
        db.commit()
        db.refresh(note)
        
        return NoteResponse(
            id=str(note.id),
            lead_id=str(note.lead_id),
            note_text=note.note_text,
            created_by=str(note.created_by) if note.created_by else None,
            created_by_name=note.created_by_name,
            note_type=note.note_type,
            related_outcome=note.related_outcome,
            created_at=note.created_at.isoformat(),
        )
    
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating note for lead {lead_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create note",
        )
