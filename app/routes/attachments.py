"""File attachment routes — upload, download, list, delete."""

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user, require_parent_a
from app.config import ATTACHMENTS_DIR, MAX_ATTACHMENT_SIZE
from app.database import get_db
from app.models import Attachment, Comment, Issue, User

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/attachments", tags=["attachments"])

# Allowed file types
ALLOWED_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/heic",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain",
    "text/csv",
}

# Also allow by extension for when content_type detection fails
ALLOWED_EXTENSIONS = {
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic",
    ".doc", ".docx", ".xlsx", ".txt", ".csv",
}


def _validate_file(file: UploadFile):
    """Validate file type and size."""
    ext = Path(file.filename or "").suffix.lower()
    if file.content_type not in ALLOWED_TYPES and ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="File type not allowed. Accepted: PDF, images, Word, Excel, text/CSV.",
        )


@router.post("/upload/{issue_id}")
async def upload_attachment(
    issue_id: str,
    file: UploadFile = File(...),
    comment_id: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a file attachment to a topic (and optionally a comment)."""
    _validate_file(file)

    # Verify issue exists
    result = await db.execute(select(Issue).where(Issue.id == issue_id))
    issue = result.scalar_one_or_none()
    if not issue:
        raise HTTPException(status_code=404, detail="Topic not found")

    # Verify comment exists if provided
    if comment_id:
        c_result = await db.execute(select(Comment).where(Comment.id == comment_id))
        if not c_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Comment not found")

    # Read file content
    content = await file.read()
    if len(content) > MAX_ATTACHMENT_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {MAX_ATTACHMENT_SIZE // (1024*1024)}MB",
        )

    # Save to disk
    file_id = str(uuid.uuid4())
    ext = Path(file.filename or "file").suffix.lower()
    safe_name = f"{file_id}{ext}"
    issue_dir = ATTACHMENTS_DIR / str(issue_id)
    issue_dir.mkdir(parents=True, exist_ok=True)
    file_path = issue_dir / safe_name
    file_path.write_bytes(content)

    # Save to DB
    attachment = Attachment(
        issue_id=issue_id,
        comment_id=comment_id,
        filename=file.filename or "file",
        content_type=file.content_type or "application/octet-stream",
        size=len(content),
        file_path=f"{issue_id}/{safe_name}",
        uploaded_by=user.id,
    )
    db.add(attachment)
    await db.flush()
    await db.refresh(attachment, ["uploader"])

    log.info(
        "Attachment uploaded: %s (%d bytes) by %s on issue %s",
        file.filename, len(content), user.display_name, issue_id,
    )

    return {
        "id": str(attachment.id),
        "filename": attachment.filename,
        "content_type": attachment.content_type,
        "size": attachment.size,
        "uploaded_by": user.display_name,
        "created_at": attachment.created_at.isoformat() if attachment.created_at else None,
    }


@router.get("/download/{attachment_id}")
async def download_attachment(
    attachment_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download an attachment by ID."""
    result = await db.execute(
        select(Attachment).where(Attachment.id == attachment_id)
    )
    att = result.scalar_one_or_none()
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found")

    full_path = ATTACHMENTS_DIR / att.file_path
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        path=str(full_path),
        filename=att.filename,
        media_type=att.content_type,
    )


@router.get("/issue/{issue_id}")
async def list_attachments(
    issue_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all attachments for a topic."""
    result = await db.execute(
        select(Attachment)
        .options(selectinload(Attachment.uploader))
        .where(Attachment.issue_id == issue_id)
        .order_by(Attachment.created_at.asc())
    )
    atts = result.scalars().all()
    return [
        {
            "id": str(a.id),
            "filename": a.filename,
            "content_type": a.content_type,
            "size": a.size,
            "uploaded_by": a.uploader.display_name if a.uploader else "Unknown",
            "uploader_role": a.uploader.role if a.uploader else None,
            "comment_id": str(a.comment_id) if a.comment_id else None,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in atts
    ]


@router.delete("/{attachment_id}")
async def delete_attachment(
    attachment_id: str,
    user: User = Depends(require_parent_a),
    db: AsyncSession = Depends(get_db),
):
    """Delete an attachment (parent_a only)."""
    result = await db.execute(
        select(Attachment).where(Attachment.id == attachment_id)
    )
    att = result.scalar_one_or_none()
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found")

    # Delete file from disk
    full_path = ATTACHMENTS_DIR / att.file_path
    if full_path.exists():
        full_path.unlink()

    await db.delete(att)
    log.info("Attachment deleted: %s by %s", att.filename, user.display_name)
    return {"deleted": True}
