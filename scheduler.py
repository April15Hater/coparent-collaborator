"""APScheduler jobs for notifications — daily digest and due date reminders."""

import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from database import async_session

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

    now = datetime.now(ZoneInfo("America/New_York"))
    hour_str = f"{now.hour:02d}:00"
    log.info("Running daily digest for hour %s", hour_str)
    async with async_session() as db:
        try:
            await send_daily_digest(db, target_hour=hour_str)
        except Exception:
            log.exception("Daily digest job failed")


def start_scheduler():
    """Start the notification scheduler."""
    # Due date reminders — run daily at 9 AM ET
    scheduler.add_job(
        _run_due_date_reminders,
        CronTrigger(hour=9, minute=0, timezone="America/New_York"),
        id="due_date_reminders",
        replace_existing=True,
    )

    # Daily digest — run every hour to catch different user preferences
    # Each user sets their preferred digest_hour; the job checks at each hour
    scheduler.add_job(
        _run_daily_digest,
        CronTrigger(minute=0, timezone="America/New_York"),
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
