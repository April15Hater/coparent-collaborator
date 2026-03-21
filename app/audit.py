"""SHA-256 hash chain for comments and audit log."""

import hashlib
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Comment


def compute_hash(prev_hash: Optional[str], content: str, timestamp: datetime) -> str:
    """Compute SHA-256 for a chain link."""
    payload = f"{prev_hash or 'GENESIS'}|{content}|{timestamp.isoformat()}"
    return hashlib.sha256(payload.encode()).hexdigest()


async def get_last_comment_hash(db: AsyncSession, issue_id: UUID) -> Optional[str]:
    """Get the content_hash of the most recent comment on an issue."""
    result = await db.execute(
        select(Comment.content_hash)
        .where(Comment.issue_id == issue_id)
        .order_by(Comment.created_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return row


async def get_last_audit_hash(db: AsyncSession) -> Optional[str]:
    """Get the content_hash of the most recent audit log entry."""
    result = await db.execute(
        select(AuditLog.content_hash)
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return row


async def create_audit_entry(
    db: AsyncSession,
    table_name: str,
    record_id: UUID,
    action: str,
    actor_id: Optional[UUID],
    old_values: Optional[dict] = None,
    new_values: Optional[dict] = None,
) -> AuditLog:
    """Create a new audit log entry with hash chain."""
    now = datetime.now(timezone.utc)
    prev_hash = await get_last_audit_hash(db)

    content = f"{table_name}|{record_id}|{action}|{str(new_values)}"
    content_hash = compute_hash(prev_hash, content, now)

    entry = AuditLog(
        table_name=table_name,
        record_id=record_id,
        action=action,
        actor_id=actor_id,
        old_values=old_values,
        new_values=new_values,
        content_hash=content_hash,
        prev_hash=prev_hash,
        created_at=now,
    )
    db.add(entry)
    return entry


async def verify_comment_chain(db: AsyncSession, issue_id: UUID) -> tuple[bool, int]:
    """Walk the comment chain for an issue and verify integrity.

    Returns (is_valid, comment_count).
    """
    result = await db.execute(
        select(Comment)
        .where(Comment.issue_id == issue_id)
        .order_by(Comment.created_at.asc())
    )
    comments = result.scalars().all()

    prev_hash = None
    for c in comments:
        if c.prev_hash != prev_hash:
            return False, len(comments)
        expected = compute_hash(prev_hash, c.body, c.created_at)
        if c.content_hash != expected:
            return False, len(comments)
        prev_hash = c.content_hash

    return True, len(comments)


async def verify_audit_chain(db: AsyncSession, limit: int = 1000) -> tuple[bool, int]:
    """Walk the global audit chain and verify integrity.

    Returns (is_valid, entry_count).
    """
    result = await db.execute(
        select(AuditLog).order_by(AuditLog.created_at.asc()).limit(limit)
    )
    entries = result.scalars().all()

    prev_hash = None
    for e in entries:
        if e.prev_hash != prev_hash:
            return False, len(entries)
        content = f"{e.table_name}|{e.record_id}|{e.action}|{str(e.new_values)}"
        expected = compute_hash(prev_hash, content, e.created_at)
        if e.content_hash != expected:
            return False, len(entries)
        prev_hash = e.content_hash

    return True, len(entries)
