"""APScheduler jobs for notifications — daily digest and due date reminders."""

import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import TIMEZONE
from app.database import async_session

log = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _run_due_date_reminders():
    """Check for upcoming due dates and send reminders."""
    from notifications import send_due_date_reminders

    log.info("Running due date reminder check")
    async with async_session() as db:
        try:
            await send_due_date_reminders(db)
        except Exception:
            log.exception("Due date reminder job failed")


async def _run_daily_digest():
    """Send daily digest emails."""
    from zoneinfo import ZoneInfo
    from notifications import send_daily_digest

    now = datetime.now(ZoneInfo(TIMEZONE))
    hour_str = f"{now.hour:02d}:00"
    log.info("Running daily digest for hour %s", hour_str)
    async with async_session() as db:
        try:
            await send_daily_digest(db, target_hour=hour_str)
        except Exception:
            log.exception("Daily digest job failed")


async def _clear_practice_topic():
    """Auto-clear comments from the practice topic every 10 minutes."""
    from sqlalchemy import delete, select
    from models import Issue, Comment, IssueStatusLog

    async with async_session() as db:
        try:
            result = await db.execute(
                select(Issue).where(Issue.title.ilike("%Practice Topic%"))
            )
            practice = result.scalar_one_or_none()
            if not practice:
                return

            del_c = await db.execute(
                delete(Comment).where(Comment.issue_id == practice.id)
            )
            del_s = await db.execute(
                delete(IssueStatusLog).where(IssueStatusLog.issue_id == practice.id)
            )
            practice.status = "open"
            practice.priority = "low"

            total = del_c.rowcount + del_s.rowcount
            if total > 0:
                log.info("Cleared %d entries from practice topic", total)
            await db.commit()
        except Exception:
            log.exception("Practice topic clear failed")
            await db.rollback()


async def _run_cooldown_digest():
    """Send batched notifications after cooldown expires (10 min no activity)."""
    from notifications import send_cooldown_digest

    async with async_session() as db:
        try:
            await send_cooldown_digest(db)
        except Exception:
            log.exception("Cooldown digest job failed")


def start_scheduler():
    """Start the notification scheduler."""
    # Cooldown digest — check every 2 minutes for batched updates
    scheduler.add_job(
        _run_cooldown_digest,
        CronTrigger(minute="*/2", timezone=TIMEZONE),
        id="cooldown_digest",
        replace_existing=True,
    )

    # Clear practice topic every 10 minutes
    scheduler.add_job(
        _clear_practice_topic,
        CronTrigger(minute="*/10", timezone=TIMEZONE),
        id="clear_practice",
        replace_existing=True,
    )

    # Due date reminders — run daily at 9 AM ET
    scheduler.add_job(
        _run_due_date_reminders,
        CronTrigger(hour=9, minute=0, timezone=TIMEZONE),
        id="due_date_reminders",
        replace_existing=True,
    )

    # Daily digest — run every hour to catch different user preferences
    # Each user sets their preferred digest_hour; the job checks at each hour
    scheduler.add_job(
        _run_daily_digest,
        CronTrigger(minute=0, timezone=TIMEZONE),
        id="daily_digest",
        replace_existing=True,
    )

    scheduler.start()
    log.info("Notification scheduler started (due dates @ 9am ET, digest hourly)")


def stop_scheduler():
    """Shutdown the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        log.info("Notification scheduler stopped")
