"""Email notifications for Ace's Co-Parenting Board.

Sends via SMTP relay () . This module handles:
- Instant notifications (new comment, status change)
- Daily digest emails
- Due date reminders (7d, 3d, 1d)
"""

import logging
from datetime import datetime, date, timedelta, timezone
from email.message import EmailMessage
from typing import Optional
from uuid import UUID

import aiosmtplib
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import APP_URL, SMTP_FROM, SMTP_HOST, SMTP_PORT
from app.models import (
    Comment, Issue, NotificationLog, NotificationPrefs,
    TopicMute, User,
)

log = logging.getLogger(__name__)


# ── SMTP sending ─────────────────────────────────────────────────────────────

async def _send_email(to: str, subject: str, html_body: str) -> bool:
    """Send an email via SMTP relay."""
    if not SMTP_HOST:
        log.warning("SMTP_HOST not configured, skipping email to %s", to)
        return False

    msg = EmailMessage()
    msg["From"] = SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(html_body, subtype="html")

    try:
        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            start_tls=False,  # LAN relay, no TLS needed
        )
        log.info("Email sent to %s: %s", to, subject)
        return True
    except Exception:
        log.exception("SMTP send failed to %s", to)
        return False


# ── Notification checks ──────────────────────────────────────────────────────

async def _get_prefs(db: AsyncSession, user_id: UUID) -> Optional[NotificationPrefs]:
    """Get notification preferences for a user."""
    result = await db.execute(
        select(NotificationPrefs).where(NotificationPrefs.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def _is_muted(db: AsyncSession, user_id: UUID, issue_id: UUID) -> bool:
    """Check if a user has muted a specific topic."""
    result = await db.execute(
        select(TopicMute).where(
            TopicMute.user_id == user_id,
            TopicMute.issue_id == issue_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def _already_sent(
    db: AsyncSession, user_id: UUID, notification_type: str, reference_id: UUID,
) -> bool:
    """Check if this notification was already sent."""
    result = await db.execute(
        select(NotificationLog).where(
            NotificationLog.user_id == user_id,
            NotificationLog.notification_type == notification_type,
            NotificationLog.reference_id == reference_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def _recently_notified(
    db: AsyncSession, user_id: UUID, notification_type: str,
    cooldown_minutes: int = 10,
) -> bool:
    """Check if we sent this type of notification recently (cooldown).

    After the first instant email, subsequent updates within the cooldown
    window are batched. The scheduler sends a mini-digest after 10 min
    of inactivity (see scheduler._run_cooldown_digest).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=cooldown_minutes)
    result = await db.execute(
        select(NotificationLog).where(
            NotificationLog.user_id == user_id,
            NotificationLog.notification_type == notification_type,
            NotificationLog.sent_at >= cutoff,
        )
    )
    return result.scalar_one_or_none() is not None


async def _log_sent(
    db: AsyncSession, user_id: UUID, notification_type: str, reference_id: UUID,
):
    """Record that a notification was sent."""
    entry = NotificationLog(
        user_id=user_id,
        notification_type=notification_type,
        reference_id=reference_id,
    )
    db.add(entry)


# ── Instant notifications ────────────────────────────────────────────────────

async def notify_new_comment(
    db: AsyncSession,
    comment: Comment,
    issue: Issue,
    author: User,
):
    """Send instant notification to the other parent when a comment is posted."""
    # Get all users except the author
    result = await db.execute(select(User).where(User.id != author.id))
    recipients = result.scalars().all()

    for recipient in recipients:
        prefs = await _get_prefs(db, recipient.id)
        if not prefs or not prefs.enabled or not prefs.instant_comments:
            continue
        if await _is_muted(db, recipient.id, issue.id):
            continue
        if await _already_sent(db, recipient.id, "instant_comment", comment.id):
            continue
        if await _recently_notified(db, recipient.id, "instant_comment"):
            log.info("Skipping instant notification to %s — cooldown (10 min), will batch", recipient.email)
            continue

        email_to = prefs.notify_email or recipient.email
        subject = f"New update on: {issue.title}"
        html = _comment_email_html(
            recipient.display_name, author.display_name,
            issue.title, str(issue.id), comment.body,
        )

        sent = await _send_email(email_to, subject, html)
        if sent:
            await _log_sent(db, recipient.id, "instant_comment", comment.id)


async def notify_status_change(
    db: AsyncSession,
    issue: Issue,
    changer: User,
    old_status: str,
    new_status: str,
):
    """Send instant notification when a topic's status changes."""
    result = await db.execute(select(User).where(User.id != changer.id))
    recipients = result.scalars().all()

    from schemas import friendly_status

    for recipient in recipients:
        prefs = await _get_prefs(db, recipient.id)
        if not prefs or not prefs.enabled or not prefs.instant_status:
            continue
        if await _is_muted(db, recipient.id, issue.id):
            continue

        email_to = prefs.notify_email or recipient.email
        subject = f"Status update: {issue.title}"
        html = _status_change_email_html(
            recipient.display_name, changer.display_name,
            issue.title, str(issue.id),
            friendly_status(old_status), friendly_status(new_status),
        )

        sent = await _send_email(email_to, subject, html)
        if sent:
            await _log_sent(db, recipient.id, "instant_status", issue.id)


# ── Due date reminders ───────────────────────────────────────────────────────

async def send_due_date_reminders(db: AsyncSession):
    """Check for upcoming due dates and send reminders (7d, 3d, 1d)."""
    today = date.today()
    reminder_days = [7, 3, 1]

    for days_before in reminder_days:
        target_date = today + timedelta(days=days_before)
        result = await db.execute(
            select(Issue)
            .where(
                Issue.due_date == target_date,
                Issue.status.notin_(["closed", "resolved"]),
            )
        )
        issues = result.scalars().all()

        for issue in issues:
            users_result = await db.execute(select(User))
            users = users_result.scalars().all()

            for user in users:
                prefs = await _get_prefs(db, user.id)
                if not prefs or not prefs.enabled or not prefs.due_date_reminders:
                    continue
                if await _is_muted(db, user.id, issue.id):
                    continue

                # Use issue.id as reference but check with type to avoid dups
                log_type = f"due_date_{days_before}d"
                if await _already_sent(db, user.id, log_type, issue.id):
                    continue

                email_to = prefs.notify_email or user.email
                subject = f"Due in {days_before} day{'s' if days_before > 1 else ''}: {issue.title}"
                html = _due_date_email_html(
                    user.display_name, issue.title, str(issue.id),
                    target_date.isoformat(), days_before,
                )

                sent = await _send_email(email_to, subject, html)
                if sent:
                    await _log_sent(db, user.id, log_type, issue.id)

    await db.commit()


# ── Daily digest ─────────────────────────────────────────────────────────────

async def send_daily_digest(db: AsyncSession, target_hour: str = "08:00"):
    """Send a daily digest to users who have it enabled."""
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)

    # Get users with digest enabled at this hour
    result = await db.execute(
        select(NotificationPrefs).where(
            NotificationPrefs.enabled == True,
            NotificationPrefs.daily_digest == True,
            NotificationPrefs.digest_hour == target_hour,
        )
    )
    prefs_list = result.scalars().all()

    for prefs in prefs_list:
        user_result = await db.execute(select(User).where(User.id == prefs.user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            continue

        # Get recent comments (last 24h)
        comments_result = await db.execute(
            select(Comment)
            .options(selectinload(Comment.author), selectinload(Comment.issue))
            .where(Comment.created_at >= yesterday)
            .order_by(Comment.created_at.desc())
        )
        recent_comments = comments_result.scalars().all()

        # Filter out muted topics
        filtered = []
        for c in recent_comments:
            if not await _is_muted(db, user.id, c.issue_id):
                filtered.append(c)

        if not filtered:
            continue

        # Get open issues with due dates in next 7 days
        upcoming_result = await db.execute(
            select(Issue).where(
                Issue.due_date != None,
                Issue.due_date <= date.today() + timedelta(days=7),
                Issue.due_date >= date.today(),
                Issue.status.notin_(["closed", "resolved"]),
            )
        )
        upcoming_issues = upcoming_result.scalars().all()

        email_to = prefs.notify_email or user.email
        subject = "Daily Update — Ace's Co-Parenting Board"
        html = _digest_email_html(user.display_name, filtered, upcoming_issues)

        await _send_email(email_to, subject, html)

    await db.commit()


# ── Cooldown digest (batched updates after 10 min of no activity) ────────────

async def send_cooldown_digest(db: AsyncSession):
    """Check for updates that were throttled during cooldown and send a digest.

    Called every 2 minutes by the scheduler. If the most recent instant
    notification for a user was 10+ minutes ago AND there are un-notified
    comments since then, send a mini-digest.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)

    users_result = await db.execute(select(User))
    users = users_result.scalars().all()

    for user in users:
        prefs = await _get_prefs(db, user.id)
        if not prefs or not prefs.enabled or not prefs.instant_comments:
            continue

        # Find their most recent instant notification
        last_notif = await db.execute(
            select(NotificationLog)
            .where(
                NotificationLog.user_id == user.id,
                NotificationLog.notification_type == "instant_comment",
            )
            .order_by(NotificationLog.sent_at.desc())
            .limit(1)
        )
        last = last_notif.scalar_one_or_none()
        if not last:
            continue

        # Only act if the last notification was 10+ minutes ago (cooldown expired)
        if last.sent_at.replace(tzinfo=timezone.utc) > cutoff:
            continue

        # Find comments by OTHER users since last notification that haven't been notified
        comments_result = await db.execute(
            select(Comment)
            .options(selectinload(Comment.author), selectinload(Comment.issue))
            .where(
                Comment.created_at > last.sent_at,
                Comment.author_id != user.id,
            )
            .order_by(Comment.created_at.asc())
        )
        pending_comments = comments_result.scalars().all()

        # Filter already-sent and muted
        unsent = []
        for c in pending_comments:
            if await _already_sent(db, user.id, "instant_comment", c.id):
                continue
            if await _is_muted(db, user.id, c.issue_id):
                continue
            unsent.append(c)

        if not unsent:
            continue

        # Send a mini-digest
        email_to = prefs.notify_email or user.email
        subject = f"{len(unsent)} new update{'s' if len(unsent) > 1 else ''} on Ace's Co-Parenting Board"
        html = _cooldown_digest_html(user.display_name, unsent)

        sent = await _send_email(email_to, subject, html)
        if sent:
            for c in unsent:
                await _log_sent(db, user.id, "instant_comment", c.id)
            log.info("Sent cooldown digest to %s (%d updates)", email_to, len(unsent))

    await db.commit()


# ── Email templates ──────────────────────────────────────────────────────────

def _email_wrapper(content: str) -> str:
    """Wrap content in a styled email container."""
    return f"""\
<div style="font-family: -apple-system, sans-serif; max-width: 560px; margin: 0 auto; padding: 24px 16px;">
  <div style="border-bottom: 2px solid #e5e7eb; padding-bottom: 12px; margin-bottom: 20px;">
    <h2 style="color: #1f2937; font-size: 18px; margin: 0;">Ace's Co-Parenting Board</h2>
  </div>
  {content}
  <div style="border-top: 1px solid #e5e7eb; padding-top: 12px; margin-top: 24px;">
    <p style="color: #9ca3af; font-size: 12px; margin: 0;">
      <a href="{APP_URL}/topics" style="color: #6b7280;">Open the board</a> ·
      <a href="{APP_URL}/topics" style="color: #6b7280;">Manage notifications</a>
    </p>
  </div>
</div>"""


def _comment_email_html(
    recipient_name: str, author_name: str,
    issue_title: str, issue_id: str, body: str,
) -> str:
    import html
    body_escaped = html.escape(body)
    return _email_wrapper(f"""\
  <p style="color: #4b5563; line-height: 1.6; margin: 0 0 16px;">
    Hi {html.escape(recipient_name)}, <strong>{html.escape(author_name)}</strong> posted an update:
  </p>
  <div style="background: #f9fafb; border-left: 3px solid #3b82f6; padding: 12px 16px; margin: 0 0 16px; border-radius: 0 6px 6px 0;">
    <p style="color: #6b7280; font-size: 13px; margin: 0 0 4px; font-weight: 600;">
      {html.escape(issue_title)}
    </p>
    <p style="color: #374151; font-size: 14px; margin: 0; white-space: pre-wrap;">{body_escaped}</p>
  </div>
  <p style="margin: 0;">
    <a href="{APP_URL}/topics/{issue_id}"
       style="color: #2563eb; font-size: 14px; text-decoration: none;">
      View topic &rarr;
    </a>
  </p>""")


def _status_change_email_html(
    recipient_name: str, changer_name: str,
    issue_title: str, issue_id: str,
    old_display: str, new_display: str,
) -> str:
    import html
    return _email_wrapper(f"""\
  <p style="color: #4b5563; line-height: 1.6; margin: 0 0 16px;">
    Hi {html.escape(recipient_name)}, <strong>{html.escape(changer_name)}</strong> updated the status of a topic:
  </p>
  <div style="background: #f9fafb; padding: 12px 16px; margin: 0 0 16px; border-radius: 6px;">
    <p style="color: #374151; font-size: 14px; margin: 0;">
      <strong>{html.escape(issue_title)}</strong><br>
      <span style="color: #9ca3af;">{html.escape(old_display)}</span> →
      <span style="color: #059669; font-weight: 600;">{html.escape(new_display)}</span>
    </p>
  </div>
  <p style="margin: 0;">
    <a href="{APP_URL}/topics/{issue_id}"
       style="color: #2563eb; font-size: 14px; text-decoration: none;">
      View topic &rarr;
    </a>
  </p>""")


def _due_date_email_html(
    recipient_name: str, issue_title: str, issue_id: str,
    due_date: str, days_before: int,
) -> str:
    import html
    urgency = "tomorrow" if days_before == 1 else f"in {days_before} days"
    color = "#dc2626" if days_before == 1 else "#f59e0b" if days_before == 3 else "#3b82f6"
    return _email_wrapper(f"""\
  <p style="color: #4b5563; line-height: 1.6; margin: 0 0 16px;">
    Hi {html.escape(recipient_name)}, a topic has a deadline coming up <strong>{urgency}</strong>:
  </p>
  <div style="background: #f9fafb; border-left: 3px solid {color}; padding: 12px 16px; margin: 0 0 16px; border-radius: 0 6px 6px 0;">
    <p style="color: #374151; font-size: 14px; margin: 0;">
      <strong>{html.escape(issue_title)}</strong><br>
      <span style="color: {color}; font-size: 13px;">Due: {due_date}</span>
    </p>
  </div>
  <p style="margin: 0;">
    <a href="{APP_URL}/topics/{issue_id}"
       style="color: #2563eb; font-size: 14px; text-decoration: none;">
      View topic &rarr;
    </a>
  </p>""")


def _cooldown_digest_html(recipient_name: str, comments: list) -> str:
    """Mini-digest for batched updates after cooldown."""
    import html
    items = ""
    for c in comments[:10]:
        issue_title = c.issue.title if c.issue else "Unknown"
        author = c.author.display_name if c.author else "Unknown"
        items += f"""\
    <div style="padding: 8px 0; border-bottom: 1px solid #f3f4f6;">
      <p style="color: #6b7280; font-size: 12px; margin: 0;">{html.escape(author)} on <strong>{html.escape(issue_title)}</strong></p>
      <p style="color: #374151; font-size: 13px; margin: 2px 0 0;">{html.escape(c.body[:150])}{'...' if len(c.body) > 150 else ''}</p>
    </div>"""

    return _email_wrapper(f"""\
  <p style="color: #4b5563; line-height: 1.6; margin: 0 0 16px;">
    Hi {html.escape(recipient_name)}, here are the updates you missed:
  </p>
  <div style="background: #f9fafb; padding: 4px 12px; border-radius: 6px; margin: 0 0 16px;">
    {items}
  </div>
  <p style="margin: 0;">
    <a href="{APP_URL}/topics" style="color: #2563eb; font-size: 14px; text-decoration: none;">
      Open the board &rarr;
    </a>
  </p>""")


def _digest_email_html(
    recipient_name: str,
    recent_comments: list,
    upcoming_issues: list,
) -> str:
    import html

    comments_html = ""
    for c in recent_comments[:10]:
        issue_title = c.issue.title if c.issue else "Unknown"
        author = c.author.display_name if c.author else "Unknown"
        time_str = c.created_at.strftime("%I:%M %p") if c.created_at else ""
        comments_html += f"""\
    <div style="padding: 8px 0; border-bottom: 1px solid #f3f4f6;">
      <p style="color: #6b7280; font-size: 12px; margin: 0;">{html.escape(author)} · {time_str}</p>
      <p style="color: #374151; font-size: 13px; margin: 2px 0 0;">
        <strong>{html.escape(issue_title)}</strong>: {html.escape(c.body[:120])}{'...' if len(c.body) > 120 else ''}
      </p>
    </div>"""

    upcoming_html = ""
    if upcoming_issues:
        upcoming_html = '<h3 style="color: #1f2937; font-size: 14px; margin: 20px 0 8px;">Upcoming Deadlines</h3>'
        for issue in upcoming_issues:
            days = (issue.due_date - date.today()).days
            label = "Today!" if days == 0 else f"in {days} day{'s' if days > 1 else ''}"
            upcoming_html += f"""\
    <p style="color: #374151; font-size: 13px; margin: 4px 0;">
      · <strong>{html.escape(issue.title)}</strong> — due {label} ({issue.due_date.isoformat()})
    </p>"""

    return _email_wrapper(f"""\
  <p style="color: #4b5563; line-height: 1.6; margin: 0 0 16px;">
    Hi {html.escape(recipient_name)}, here's what happened in the last 24 hours:
  </p>
  <h3 style="color: #1f2937; font-size: 14px; margin: 0 0 8px;">Recent Updates ({len(recent_comments)})</h3>
  <div style="background: #f9fafb; padding: 4px 12px; border-radius: 6px; margin: 0 0 8px;">
    {comments_html or '<p style="color: #9ca3af; font-size: 13px;">No updates.</p>'}
  </div>
  {upcoming_html}
  <p style="margin: 20px 0 0;">
    <a href="{APP_URL}/topics"
       style="color: #2563eb; font-size: 14px; text-decoration: none;">
      Open the board &rarr;
    </a>
  </p>""")
