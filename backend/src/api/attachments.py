"""
Lead attachment endpoints.

Handles upload, download, list, delete, and bulk counts for lead documents.
"""

import logging
import uuid
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..core.auth import get_current_user, require_role
from ..core.database import get_db
from ..models.attachment import LeadAttachment
from ..models.lead import Lead

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/leads", tags=["Lead Attachments"])

MAX_FILE_SIZE = 25 * 1024 * 1024
ALLOWED_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/bmp",
    "image/tiff",
}
UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "attachments"


def _ensure_upload_dir() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _get_user_info(request: Request, db: Session) -> tuple[str, UUID | None]:
    user_name = "System"
    user_id = None
    try:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            from ..core.security import decode_token
            from ..models.user import User

            token = auth_header.split(" ", 1)[1]
            payload = decode_token(token)
            if payload and "sub" in payload:
                user = db.query(User).filter(User.id == payload["sub"]).first()
                if user:
                    user_id = user.id
                    user_name = getattr(user, "full_name", "").strip() or f"{user.first_name} {user.last_name}".strip() or user.email
    except Exception:
        pass
    return user_name, user_id


@router.post(
    "/{lead_id}/attachments",
    status_code=status.HTTP_201_CREATED,
    summary="Upload Attachment",
    description="Upload a file attachment to a lead. Max 25MB. Supports PDF, Word, Excel, images.",
    dependencies=[Depends(require_role("administrator", "coordinator"))],
)
async def upload_attachment(
    lead_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    lead = db.query(Lead).filter(
        Lead.id == lead_id,
        Lead.deleted_at.is_(None),
    ).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{content_type}' is not allowed. Supported: PDF, Word, Excel, images.",
        )

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="File is empty.")
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File size ({len(content) / 1024 / 1024:.1f} MB) exceeds the 25 MB limit.",
        )

    original_filename = file.filename or "unnamed"
    extension = Path(original_filename).suffix.lower() or ""
    stored_filename = f"{uuid.uuid4().hex}{extension}"

    _ensure_upload_dir()
    file_path = UPLOAD_DIR / stored_filename
    try:
        with open(file_path, "wb") as handle:
            handle.write(content)
    except Exception as exc:
        logger.error("Failed to write attachment to disk: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save file.")

    user_name, user_id = _get_user_info(request, db)
    attachment = LeadAttachment(
        lead_id=lead_id,
        filename=original_filename,
        stored_filename=stored_filename,
        file_type=content_type,
        file_size=len(content),
        uploaded_by=user_name,
        uploaded_by_id=user_id,
    )
    db.add(attachment)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error(
            "Failed to save attachment metadata for lead %s (%s): %s",
            lead_id,
            original_filename,
            exc,
            exc_info=True,
        )
        try:
            if file_path.exists():
                file_path.unlink()
        except OSError as cleanup_exc:
            logger.warning(
                "Attachment cleanup failed for %s after DB error: %s",
                stored_filename,
                cleanup_exc,
            )
        raise HTTPException(status_code=500, detail="Failed to save attachment metadata.")

    db.refresh(attachment)
    return attachment.to_dict()


@router.get(
    "/{lead_id}/attachments",
    summary="List Attachments",
    description="Get all attachments for a lead.",
    dependencies=[Depends(get_current_user)],
)
async def list_attachments(
    lead_id: UUID,
    db: Session = Depends(get_db),
) -> list[dict]:
    lead = db.query(Lead).filter(
        Lead.id == lead_id,
        Lead.deleted_at.is_(None),
    ).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    attachments = (
        db.query(LeadAttachment)
        .filter(LeadAttachment.lead_id == lead_id)
        .order_by(LeadAttachment.created_at.desc())
        .all()
    )
    return [attachment.to_dict() for attachment in attachments]


@router.get(
    "/{lead_id}/attachments/{attachment_id}/download",
    summary="Download Attachment",
    description="Download an attachment file.",
    dependencies=[Depends(get_current_user)],
)
async def download_attachment(
    lead_id: UUID,
    attachment_id: UUID,
    db: Session = Depends(get_db),
) -> FileResponse:
    attachment = db.query(LeadAttachment).filter(
        LeadAttachment.id == attachment_id,
        LeadAttachment.lead_id == lead_id,
    ).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    file_path = UPLOAD_DIR / attachment.stored_filename
    if not file_path.exists():
        logger.error("Attachment file missing from disk: %s", attachment.stored_filename)
        raise HTTPException(status_code=404, detail="Attachment file not found on server")

    return FileResponse(
        path=str(file_path),
        filename=attachment.filename,
        media_type=attachment.file_type,
    )


@router.delete(
    "/{lead_id}/attachments/{attachment_id}",
    summary="Delete Attachment",
    description="Delete an attachment (removes file from disk and metadata from DB).",
    dependencies=[Depends(require_role("administrator", "coordinator"))],
)
async def delete_attachment(
    lead_id: UUID,
    attachment_id: UUID,
    db: Session = Depends(get_db),
) -> dict:
    attachment = db.query(LeadAttachment).filter(
        LeadAttachment.id == attachment_id,
        LeadAttachment.lead_id == lead_id,
    ).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    filename = attachment.filename
    file_path = UPLOAD_DIR / attachment.stored_filename
    try:
        if file_path.exists():
            file_path.unlink()
    except Exception as exc:
        logger.warning("Failed to delete attachment file from disk: %s", exc)

    db.delete(attachment)
    db.commit()
    return {"success": True, "message": f"Attachment '{filename}' deleted."}


@router.get(
    "/attachment-counts",
    summary="Get Attachment Counts",
    description="Get attachment counts for all leads with at least one attachment.",
    dependencies=[Depends(get_current_user)],
)
async def get_attachment_counts(
    db: Session = Depends(get_db),
) -> dict[str, int]:
    results = (
        db.query(
            LeadAttachment.lead_id,
            func.count(LeadAttachment.id).label("count"),
        )
        .group_by(LeadAttachment.lead_id)
        .all()
    )
    return {str(row.lead_id): row.count for row in results}
