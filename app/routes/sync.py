"""Sync API for Tier 2 (private vault) to pull data."""

import hmac
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import SYNC_API_KEY
from database import get_db
from models import Attachment, Comment, Issue, IssueStatusLog

router = APIRouter(prefix="/api/sync", tags=["sync"])


async def verify_sync_key(x_sync_key: str = Header(...)):
    """Verify the sync API key from Tier 2."""
    if not SYNC_API_KEY or not hmac.compare_digest(x_sync_key, SYNC_API_KEY):
        raise HTTPException(status_code=403, detail="Invalid sync key")


@router.get("/issues", dependencies=[Depends(verify_sync_key)])
async def sync_issues(
    since: Optional[str] = Query(None, description="ISO timestamp to fetch changes since"),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Issue)
        .options(
            selectinload(Issue.creator),
            selectinload(Issue.assignee),
            selectinload(Issue.tags),
        )
        .order_by(Issue.updated_at.desc())
    )
    if since:
        since_dt = datetime.fromisoformat(since)
        query = query.where(Issue.updated_at >= since_dt)

    result = await db.execute(query)
    issues = result.scalars().unique().all()

    return [
        {
            "id": str(i.id),
            "title": i.title,
            "description": i.description,
            "status": i.status,
            "priority": i.priority,
            "category": i.category,
            "created_by": str(i.created_by),
            "assigned_to": str(i.assigned_to) if i.assigned_to else None,
            "due_date": i.due_date.isoformat() if i.due_date else None,
            "created_at": i.created_at.isoformat(),
            "updated_at": i.updated_at.isoformat(),
            "creator_name": i.creator.display_name if i.creator else None,
            "assignee_name": i.assignee.display_name if i.assignee else None,
            "tags": [{"name": t.name, "color": t.color} for t in (i.tags or [])],
        }
        for i in issues
    ]


@router.get("/comments", dependencies=[Depends(verify_sync_key)])
async def sync_comments(
    since: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Comment)
        .options(selectinload(Comment.author))
        .order_by(Comment.created_at.asc())
    )
    if since:
        since_dt = datetime.fromisoformat(since)
        query = query.where(Comment.created_at >= since_dt)

    result = await db.execute(query)
    comments = result.scalars().all()

    return [
        {
            "id": str(c.id),
            "issue_id": str(c.issue_id),
            "author_id": str(c.author_id),
            "author_name": c.author.display_name if c.author else None,
            "body": c.body,
            "content_hash": c.content_hash,
            "created_at": c.created_at.isoformat(),
        }
        for c in comments
    ]


@router.get("/issues/{issue_id}", dependencies=[Depends(verify_sync_key)])
async def sync_issue_detail(
    issue_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Full issue detail with comments and status log, for AI context building."""
    result = await db.execute(
        select(Issue)
        .options(
            selectinload(Issue.creator),
            selectinload(Issue.assignee),
            selectinload(Issue.tags),
            selectinload(Issue.comments).selectinload(Comment.author),
            selectinload(Issue.status_logs).selectinload(IssueStatusLog.changer),
        )
        .where(Issue.id == issue_id)
    )
    issue = result.scalar_one_or_none()
    if not issue:
        raise HTTPException(status_code=404, detail="Not found")

    return {
        "id": str(issue.id),
        "title": issue.title,
        "description": issue.description,
        "status": issue.status,
        "priority": issue.priority,
        "category": issue.category,
        "due_date": issue.due_date.isoformat() if issue.due_date else None,
        "created_at": issue.created_at.isoformat(),
        "updated_at": issue.updated_at.isoformat(),
        "creator_name": issue.creator.display_name if issue.creator else None,
        "comments": [
            {
                "author": c.author.display_name if c.author else "Unknown",
                "body": c.body,
                "created_at": c.created_at.isoformat(),
            }
            for c in sorted(issue.comments, key=lambda x: x.created_at)
        ],
        "status_log": [
            {
                "from": sl.old_status,
                "to": sl.new_status,
                "by": sl.changer.display_name if sl.changer else "Unknown",
                "reason": sl.reason,
                "at": sl.created_at.isoformat(),
            }
            for sl in sorted(issue.status_logs, key=lambda x: x.created_at)
        ],
    }


@router.get("/full", dependencies=[Depends(verify_sync_key)])
async def sync_full_dump(db: AsyncSession = Depends(get_db)):
    """Full data dump for initial Tier 2 sync."""
    issues = await sync_issues(since=None, db=db)
    comments = await sync_comments(since=None, db=db)
    return {"issues": issues, "comments": comments}


@router.get("/attachments", dependencies=[Depends(verify_sync_key)])
async def sync_attachments(
    since: Optional[str] = Query(None),
    uploader_role: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """List attachments, optionally filtered by uploader role and time."""
    from sqlalchemy.orm import selectinload as sil

    query = (
        select(Attachment)
        .options(sil(Attachment.uploader))
        .order_by(Attachment.created_at.asc())
    )
    if since:
        since_dt = datetime.fromisoformat(since)
        query = query.where(Attachment.created_at >= since_dt)

    result = await db.execute(query)
    atts = result.scalars().all()

    # Filter by uploader role if requested
    if uploader_role:
        atts = [a for a in atts if a.uploader and a.uploader.role == uploader_role]

    return [
        {
            "id": str(a.id),
            "issue_id": str(a.issue_id),
            "comment_id": str(a.comment_id) if a.comment_id else None,
            "filename": a.filename,
            "content_type": a.content_type,
            "size": a.size,
            "file_path": a.file_path,
            "uploader_role": a.uploader.role if a.uploader else None,
            "uploader_name": a.uploader.display_name if a.uploader else None,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in atts
    ]


@router.get("/attachments/{attachment_id}/download", dependencies=[Depends(verify_sync_key)])
async def sync_download_attachment(
    attachment_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Download attachment file (for vault to pull and send to Paperless)."""
    from fastapi.responses import FileResponse
    from config import ATTACHMENTS_DIR

    result = await db.execute(select(Attachment).where(Attachment.id == attachment_id))
    att = result.scalar_one_or_none()
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found")

    full_path = ATTACHMENTS_DIR / att.file_path
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(path=str(full_path), filename=att.filename, media_type=att.content_type)
