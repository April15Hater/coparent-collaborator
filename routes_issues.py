"""Issue (Topic) CRUD routes."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from audit import create_audit_entry
from sqlalchemy import delete
from auth import get_current_user, require_parent_a
from database import get_db
from models import Comment, Issue, IssueStatusLog, Tag, User
from notifications import notify_status_change
from schemas import (
    IssueCreate,
    IssueResponse,
    IssueUpdate,
    TimelineEntry,
    UserResponse,
    friendly_status,
)

router = APIRouter(prefix="/api/issues", tags=["issues"])


def _issue_to_response(issue: Issue, viewer_role: str, comment_count: int = 0) -> IssueResponse:
    resp = IssueResponse(
        id=issue.id,
        title=issue.title,
        description=issue.description,
        status=issue.status,
        display_status=friendly_status(issue.status, viewer_role),
        priority=issue.priority,
        category=issue.category,
        created_by=issue.created_by,
        assigned_to=issue.assigned_to,
        due_date=issue.due_date,
        created_at=issue.created_at,
        updated_at=issue.updated_at,
        creator=UserResponse.model_validate(issue.creator) if issue.creator else None,
        assignee=UserResponse.model_validate(issue.assignee) if issue.assignee else None,
        tags=[],
        comment_count=comment_count,
    )
    if issue.tags:
        resp.tags = [{"id": t.id, "name": t.name, "color": t.color} for t in issue.tags]
    return resp


@router.get("", response_model=list[IssueResponse])
async def list_issues(
    status_filter: Optional[str] = Query(None, alias="status"),
    category: Optional[str] = None,
    tag: Optional[str] = None,
    sort: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Priority ordering: urgent=0, high=1, normal=2, low=3
    priority_order = case(
        (Issue.priority == "urgent", 0),
        (Issue.priority == "high", 1),
        (Issue.priority == "normal", 2),
        (Issue.priority == "low", 3),
        else_=4,
    )

    sort_options = {
        "priority": [priority_order.asc(), Issue.updated_at.desc()],
        "newest": [Issue.created_at.desc()],
        "oldest": [Issue.created_at.asc()],
        "updated": [Issue.updated_at.desc()],
        "due_date": [Issue.due_date.asc().nullslast(), Issue.updated_at.desc()],
    }
    order_by = sort_options.get(sort, [priority_order.asc(), Issue.updated_at.desc()])

    query = (
        select(Issue)
        .options(selectinload(Issue.creator), selectinload(Issue.assignee), selectinload(Issue.tags))
        .order_by(*order_by)
    )

    if status_filter:
        query = query.where(Issue.status == status_filter)
    if category:
        query = query.where(Issue.category == category)

    result = await db.execute(query)
    issues = result.scalars().unique().all()

    # Get comment counts in bulk
    count_q = (
        select(Comment.issue_id, func.count(Comment.id).label("cnt"))
        .group_by(Comment.issue_id)
    )
    count_result = await db.execute(count_q)
    counts = {row.issue_id: row.cnt for row in count_result}

    return [_issue_to_response(i, user.role, counts.get(i.id, 0)) for i in issues]


@router.post("", response_model=IssueResponse, status_code=201)
async def create_issue(
    body: IssueCreate,
    user: User = Depends(require_parent_a),
    db: AsyncSession = Depends(get_db),
):
    issue = Issue(
        title=body.title,
        description=body.description,
        priority=body.priority,
        category=body.category,
        created_by=user.id,
        assigned_to=body.assigned_to,
        due_date=body.due_date,
    )
    db.add(issue)
    await db.flush()

    # Tags
    if body.tag_ids:
        tag_result = await db.execute(select(Tag).where(Tag.id.in_(body.tag_ids)))
        tags = tag_result.scalars().all()
        issue.tags = list(tags)

    # Status log
    log = IssueStatusLog(
        issue_id=issue.id,
        old_status=None,
        new_status="open",
        changed_by=user.id,
    )
    db.add(log)

    # Audit
    await create_audit_entry(
        db, "issues", issue.id, "create", user.id,
        new_values={"title": issue.title, "category": issue.category, "status": "open"},
    )

    await db.flush()
    await db.refresh(issue, ["creator", "assignee", "tags"])
    return _issue_to_response(issue, user.role, 0)


@router.get("/{issue_id}", response_model=IssueResponse)
async def get_issue(
    issue_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Issue)
        .options(selectinload(Issue.creator), selectinload(Issue.assignee), selectinload(Issue.tags))
        .where(Issue.id == issue_id)
    )
    issue = result.scalar_one_or_none()
    if not issue:
        raise HTTPException(status_code=404, detail="Topic not found")

    count_result = await db.execute(
        select(func.count(Comment.id)).where(Comment.issue_id == issue_id)
    )
    count = count_result.scalar() or 0

    return _issue_to_response(issue, user.role, count)


@router.patch("/{issue_id}", response_model=IssueResponse)
async def update_issue(
    issue_id: UUID,
    body: IssueUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Issue)
        .options(selectinload(Issue.creator), selectinload(Issue.assignee), selectinload(Issue.tags))
        .where(Issue.id == issue_id)
    )
    issue = result.scalar_one_or_none()
    if not issue:
        raise HTTPException(status_code=404, detail="Topic not found")

    old_values = {}
    new_values = {}

    # Status change
    if body.status and body.status != issue.status:
        # Only parent_a can close/resolve
        if body.status in ("closed", "resolved") and user.role != "parent_a":
            raise HTTPException(status_code=403, detail="Only Joey can close or resolve topics")

        old_values["status"] = issue.status
        new_values["status"] = body.status

        log = IssueStatusLog(
            issue_id=issue.id,
            old_status=issue.status,
            new_status=body.status,
            changed_by=user.id,
            reason=body.status_reason,
        )
        db.add(log)
        issue.status = body.status

    # Other fields — both parents can change priority; rest is parent_a only
    for field in ("title", "description", "priority", "category", "assigned_to", "due_date"):
        val = getattr(body, field, None)
        if val is not None:
            if field not in ("status", "priority") and user.role != "parent_a":
                continue
            old_val = getattr(issue, field)
            if old_val != val:
                old_values[field] = str(old_val)
                new_values[field] = str(val)
                setattr(issue, field, val)

    if new_values:
        await create_audit_entry(
            db, "issues", issue.id, "update", user.id,
            old_values=old_values, new_values=new_values,
        )

    await db.flush()
    await db.refresh(issue, ["creator", "assignee", "tags"])

    # Send status change notification
    if "status" in new_values:
        try:
            await notify_status_change(
                db, issue, user, old_values.get("status", ""), new_values["status"],
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Status notification failed: %s", exc)

    count_result = await db.execute(
        select(func.count(Comment.id)).where(Comment.issue_id == issue_id)
    )
    count = count_result.scalar() or 0

    return _issue_to_response(issue, user.role, count)


@router.get("/{issue_id}/timeline", response_model=list[TimelineEntry])
async def get_timeline(
    issue_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Fetch comments
    comment_result = await db.execute(
        select(Comment)
        .options(selectinload(Comment.author))
        .where(Comment.issue_id == issue_id)
        .order_by(Comment.created_at)
    )
    comments = comment_result.scalars().all()

    # Fetch status logs
    log_result = await db.execute(
        select(IssueStatusLog)
        .options(selectinload(IssueStatusLog.changer))
        .where(IssueStatusLog.issue_id == issue_id)
        .order_by(IssueStatusLog.created_at)
    )
    logs = log_result.scalars().all()

    entries: list[TimelineEntry] = []

    for c in comments:
        entries.append(TimelineEntry(
            type="comment",
            created_at=c.created_at,
            actor=UserResponse.model_validate(c.author) if c.author else None,
            body=c.body,
            content_hash=c.content_hash,
        ))

    for log in logs:
        entries.append(TimelineEntry(
            type="status_change",
            created_at=log.created_at,
            actor=UserResponse.model_validate(log.changer) if log.changer else None,
            old_status=log.old_status,
            new_status=log.new_status,
            old_display=friendly_status(log.old_status) if log.old_status else None,
            new_display=friendly_status(log.new_status),
            reason=log.reason,
        ))

    entries.sort(key=lambda e: e.created_at)
    return entries


@router.post("/{issue_id}/clear-comments")
async def clear_practice_comments(
    issue_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Clear all comments from the practice topic only."""
    result = await db.execute(
        select(Issue).where(Issue.id == issue_id)
    )
    issue = result.scalar_one_or_none()
    if not issue:
        raise HTTPException(status_code=404, detail="Topic not found")

    if "practice" not in issue.title.lower():
        raise HTTPException(status_code=403, detail="Can only clear the practice topic")

    del_comments = await db.execute(
        delete(Comment).where(Comment.issue_id == issue_id)
    )
    del_status = await db.execute(
        delete(IssueStatusLog).where(IssueStatusLog.issue_id == issue_id)
    )

    # Reset to default state
    issue.status = "open"
    issue.priority = "low"

    await db.commit()
    return {"cleared_comments": del_comments.rowcount, "cleared_status_logs": del_status.rowcount}
