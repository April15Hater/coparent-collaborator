"""Notification preferences and topic mute management."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from models import NotificationPrefs, TopicMute, User

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class PrefsUpdate(BaseModel):
    enabled: bool | None = None
    instant_comments: bool | None = None
    instant_status: bool | None = None
    daily_digest: bool | None = None
    due_date_reminders: bool | None = None
    digest_hour: str | None = None
    notify_email: str | None = None


class PrefsResponse(BaseModel):
    enabled: bool
    instant_comments: bool
    instant_status: bool
    daily_digest: bool
    due_date_reminders: bool
    digest_hour: str
    notify_email: str | None

    model_config = {"from_attributes": True}


@router.get("/preferences", response_model=PrefsResponse)
async def get_preferences(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current user's notification preferences."""
    result = await db.execute(
        select(NotificationPrefs).where(NotificationPrefs.user_id == user.id)
    )
    prefs = result.scalar_one_or_none()
    if not prefs:
        # Create default prefs (disabled by default)
        prefs = NotificationPrefs(user_id=user.id, enabled=False)
        db.add(prefs)
        await db.flush()
        await db.refresh(prefs)
    return prefs


@router.patch("/preferences", response_model=PrefsResponse)
async def update_preferences(
    body: PrefsUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the current user's notification preferences."""
    result = await db.execute(
        select(NotificationPrefs).where(NotificationPrefs.user_id == user.id)
    )
    prefs = result.scalar_one_or_none()
    if not prefs:
        prefs = NotificationPrefs(user_id=user.id)
        db.add(prefs)
        await db.flush()

    for field in ("enabled", "instant_comments", "instant_status",
                  "daily_digest", "due_date_reminders", "digest_hour", "notify_email"):
        val = getattr(body, field, None)
        if val is not None:
            setattr(prefs, field, val)

    await db.flush()
    await db.refresh(prefs)
    return prefs


@router.get("/muted", response_model=list[str])
async def list_muted_topics(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List topic IDs the current user has muted."""
    result = await db.execute(
        select(TopicMute.issue_id).where(TopicMute.user_id == user.id)
    )
    return [str(row) for row in result.scalars().all()]


@router.post("/mute/{issue_id}")
async def mute_topic(
    issue_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mute notifications for a specific topic."""
    existing = await db.execute(
        select(TopicMute).where(
            TopicMute.user_id == user.id,
            TopicMute.issue_id == issue_id,
        )
    )
    if existing.scalar_one_or_none():
        return {"detail": "Already muted"}

    mute = TopicMute(user_id=user.id, issue_id=issue_id)
    db.add(mute)
    return {"detail": "Topic muted"}


@router.delete("/mute/{issue_id}")
async def unmute_topic(
    issue_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unmute notifications for a specific topic."""
    result = await db.execute(
        select(TopicMute).where(
            TopicMute.user_id == user.id,
            TopicMute.issue_id == issue_id,
        )
    )
    mute = result.scalar_one_or_none()
    if not mute:
        return {"detail": "Not muted"}

    await db.delete(mute)
    return {"detail": "Topic unmuted"}
