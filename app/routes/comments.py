"""Append-only comment routes with SHA-256 hash chain."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit import compute_hash, create_audit_entry, get_last_comment_hash, verify_comment_chain
from app.auth import get_current_user
from app.database import get_db
from app.models import Comment, Issue, User
from app.notifications import notify_new_comment
from app.schemas import CommentCreate, CommentResponse, UserResponse

router = APIRouter(prefix="/api/issues/{issue_id}/comments", tags=["comments"])


@router.get("", response_model=list[CommentResponse])
async def list_comments(
    issue_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Comment)
        .options(selectinload(Comment.author))
        .where(Comment.issue_id == issue_id)
        .order_by(Comment.created_at.asc())
    )
    comments = result.scalars().all()
    return [CommentResponse.model_validate(c) for c in comments]


@router.post("", response_model=CommentResponse, status_code=201)
async def create_comment(
    issue_id: UUID,
    body: CommentCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify issue exists
    issue_result = await db.execute(select(Issue).where(Issue.id == issue_id))
    issue = issue_result.scalar_one_or_none()
    if not issue:
        raise HTTPException(status_code=404, detail="Topic not found")

    now = datetime.now(timezone.utc)
    prev_hash = await get_last_comment_hash(db, issue_id)
    content_hash = compute_hash(prev_hash, body.body, now)

    comment = Comment(
        issue_id=issue_id,
        author_id=user.id,
        body=body.body,
        content_hash=content_hash,
        prev_hash=prev_hash,
        created_at=now,
    )
    db.add(comment)
    await db.flush()  # Generates comment.id

    await create_audit_entry(
        db, "comments", comment.id, "create", user.id,
        new_values={"issue_id": str(issue_id), "body_preview": body.body[:100]},
    )

    await db.flush()
    await db.refresh(comment, ["author"])

    # Send instant notification to other parent (non-blocking)
    try:
        await notify_new_comment(db, comment, issue, user)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Notification failed: %s", exc)

    return CommentResponse.model_validate(comment)


@router.get("/verify")
async def verify_chain(
    issue_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify the integrity of the comment hash chain for an issue."""
    is_valid, count = await verify_comment_chain(db, issue_id)
    return {
        "issue_id": str(issue_id),
        "is_valid": is_valid,
        "comment_count": count,
    }
