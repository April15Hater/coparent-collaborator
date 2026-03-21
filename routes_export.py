"""Export routes — CSV download and printable HTML view."""

import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth import get_current_user
from database import get_db
from models import Comment, Issue, IssueStatusLog, User
from schemas import friendly_status

router = APIRouter(prefix="/export", tags=["export"])


async def _get_all_data(db: AsyncSession):
    """Fetch all issues with comments and status logs (batch-loaded)."""
    result = await db.execute(
        select(Issue)
        .options(
            selectinload(Issue.creator),
            selectinload(Issue.tags),
            selectinload(Issue.comments).selectinload(Comment.author),
            selectinload(Issue.status_logs),
        )
        .order_by(Issue.created_at.asc())
    )
    issues = result.scalars().unique().all()

    data = []
    for issue in issues:
        comments = sorted(issue.comments, key=lambda c: c.created_at)
        status_logs = sorted(issue.status_logs, key=lambda s: s.created_at)

        data.append({
            "issue": issue,
            "comments": comments,
            "status_logs": status_logs,
        })

    return data


def _fmt(dt) -> str:
    """Format datetime for display."""
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%m/%d/%Y %I:%M %p")


@router.get("/csv")
async def export_csv(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export all topics and updates as CSV."""
    data = await _get_all_data(db)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Topic", "Category", "Priority", "Status", "Due Date",
        "Created", "Update Type", "Author", "Date", "Content",
    ])

    for item in data:
        issue = item["issue"]
        status = friendly_status(issue.status, "parent_a")

        # Issue row
        writer.writerow([
            issue.title, issue.category, issue.priority, status,
            str(issue.due_date) if issue.due_date else "",
            _fmt(issue.created_at), "Topic Created",
            issue.creator.display_name if issue.creator else "",
            _fmt(issue.created_at), issue.description or "",
        ])

        # Merge comments and status changes chronologically
        timeline = []
        for c in item["comments"]:
            timeline.append(("comment", c.created_at, c))
        for s in item["status_logs"]:
            if s.old_status:  # skip initial creation log
                timeline.append(("status", s.created_at, s))
        timeline.sort(key=lambda x: x[1])

        for entry_type, ts, entry in timeline:
            if entry_type == "comment":
                writer.writerow([
                    issue.title, "", "", "", "", "",
                    "Comment", entry.author.display_name if entry.author else "",
                    _fmt(ts), entry.body,
                ])
            else:
                writer.writerow([
                    issue.title, "", "", "", "", "",
                    "Status Change", "",
                    _fmt(ts),
                    f"{friendly_status(entry.old_status, 'parent_a')} → {friendly_status(entry.new_status, 'parent_a')}",
                ])

    output.seek(0)
    now = datetime.now().strftime("%Y-%m-%d")
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=coparenting-board-{now}.csv"},
    )


@router.get("/print", response_class=HTMLResponse)
async def export_print(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Printable HTML view of all topics and updates."""
    data = await _get_all_data(db)
    now = datetime.now().strftime("%B %d, %Y at %I:%M %p")

    html_parts = [f"""<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<title>Ace's Co-Parenting Board — Full Export</title>
<style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 0 auto; padding: 32px 16px; color: #1e293b; font-size: 14px; }}
    h1 {{ font-size: 20px; margin-bottom: 4px; }}
    .subtitle {{ color: #64748b; font-size: 13px; margin-bottom: 32px; }}
    .topic {{ border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 24px; page-break-inside: avoid; }}
    .topic-title {{ font-size: 16px; font-weight: 600; margin-bottom: 8px; }}
    .topic-meta {{ font-size: 12px; color: #64748b; margin-bottom: 12px; display: flex; gap: 12px; flex-wrap: wrap; }}
    .topic-meta span {{ display: inline-flex; align-items: center; gap: 4px; }}
    .topic-desc {{ font-size: 13px; color: #475569; margin-bottom: 12px; line-height: 1.5; border-left: 3px solid #e2e8f0; padding-left: 12px; }}
    .comment {{ padding: 10px 0; border-top: 1px solid #f1f5f9; }}
    .comment-meta {{ font-size: 12px; color: #64748b; margin-bottom: 4px; }}
    .comment-meta strong {{ color: #1e293b; }}
    .comment-text {{ font-size: 13px; line-height: 1.5; white-space: pre-wrap; }}
    .status-entry {{ font-size: 12px; color: #94a3b8; padding: 6px 0; border-top: 1px solid #f1f5f9; font-style: italic; }}
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
    .badge-education {{ background: #eff6ff; color: #1d4ed8; }}
    .badge-medical {{ background: #ecfdf5; color: #047857; }}
    .badge-behavioral {{ background: #fffbeb; color: #b45309; }}
    .badge-legal {{ background: #fef2f2; color: #b91c1c; }}
    .badge-scheduling {{ background: #f5f3ff; color: #6d28d9; }}
    .badge-financial {{ background: #fefce8; color: #a16207; }}
    .badge-other {{ background: #f8fafc; color: #475569; }}
    .priority-urgent {{ color: #dc2626; font-weight: 600; }}
    .priority-high {{ color: #ea580c; font-weight: 600; }}
    @media print {{ body {{ padding: 0; }} .topic {{ border: 1px solid #ccc; }} }}
</style>
</head><body>
<h1>Ace's Co-Parenting Board</h1>
<p class="subtitle">Exported {now}</p>
"""]

    for item in data:
        issue = item["issue"]
        status = friendly_status(issue.status, "parent_a")
        priority_class = f"priority-{issue.priority}" if issue.priority in ("urgent", "high") else ""
        due = f" &middot; Due {issue.due_date}" if issue.due_date else ""

        html_parts.append(f"""
<div class="topic">
    <div class="topic-title">{_esc(issue.title)}</div>
    <div class="topic-meta">
        <span class="badge badge-{issue.category}">{issue.category}</span>
        <span>{status}</span>
        <span class="{priority_class}">{issue.priority}</span>
        <span>Created {_fmt(issue.created_at)}</span>
        {f'<span style="color:#ea580c">Due {issue.due_date}</span>' if issue.due_date else ''}
    </div>
""")
        if issue.description:
            html_parts.append(f'    <div class="topic-desc">{_esc(issue.description)}</div>\n')

        # Merge timeline
        timeline = []
        for c in item["comments"]:
            timeline.append(("comment", c.created_at, c))
        for s in item["status_logs"]:
            if s.old_status:
                timeline.append(("status", s.created_at, s))
        timeline.sort(key=lambda x: x[1])

        for entry_type, ts, entry in timeline:
            if entry_type == "comment":
                author = entry.author.display_name if entry.author else "Unknown"
                html_parts.append(f"""
    <div class="comment">
        <div class="comment-meta"><strong>{_esc(author)}</strong> &middot; {_fmt(ts)}</div>
        <div class="comment-text">{_esc(entry.body)}</div>
    </div>
""")
            else:
                old_s = friendly_status(entry.old_status, "parent_a")
                new_s = friendly_status(entry.new_status, "parent_a")
                html_parts.append(f"""
    <div class="status-entry">Status changed: {old_s} → {new_s} &middot; {_fmt(ts)}</div>
""")

        html_parts.append("</div>\n")

    html_parts.append("</body></html>")
    return HTMLResponse("".join(html_parts))


def _esc(s: str) -> str:
    """HTML-escape a string."""
    if not s:
        return ""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
