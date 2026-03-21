"""Pydantic request/response schemas for Co-Parenting Board."""

from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from enum import Enum

from pydantic import BaseModel, Field


class IssueStatus(str, Enum):
    open = "open"
    in_progress = "in_progress"
    waiting_on_parent_a = "waiting_on_parent_a"
    waiting_on_parent_b = "waiting_on_parent_b"
    resolved = "resolved"
    closed = "closed"


class IssuePriority(str, Enum):
    low = "low"
    normal = "normal"
    high = "high"
    urgent = "urgent"


class IssueCategory(str, Enum):
    education = "education"
    medical = "medical"
    behavioral = "behavioral"
    legal = "legal"
    scheduling = "scheduling"
    financial = "financial"
    other = "other"


# ---------- friendly status mapping ----------

_STATUS_DISPLAY = {
    "open": "Open",
    "in_progress": "In Progress",
    "waiting_on_parent_a": "Needs Father's input",
    "waiting_on_parent_b": "Needs Mother's input",
    "resolved": "Resolved together",
    "closed": "Closed",
}


def friendly_status(status: str, viewer_role: str | None = None) -> str:
    """Return human-friendly status text."""
    return _STATUS_DISPLAY.get(status, status)


# ---------- Users ----------

class UserResponse(BaseModel):
    id: UUID
    email: str
    display_name: str
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------- Tags ----------

class TagResponse(BaseModel):
    id: UUID
    name: str
    color: Optional[str] = None

    model_config = {"from_attributes": True}


# ---------- Issues ----------

class IssueCreate(BaseModel):
    title: str
    description: Optional[str] = None
    priority: IssuePriority = IssuePriority.normal
    category: IssueCategory
    assigned_to: Optional[UUID] = None
    due_date: Optional[date] = None
    tag_ids: list[UUID] = Field(default_factory=list)


class IssueUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[IssueStatus] = None
    priority: Optional[IssuePriority] = None
    category: Optional[IssueCategory] = None
    assigned_to: Optional[UUID] = None
    due_date: Optional[date] = None
    clear_due_date: Optional[bool] = None
    status_reason: Optional[str] = None


class IssueResponse(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    status: str
    display_status: str = ""
    priority: str
    category: str
    created_by: UUID
    assigned_to: Optional[UUID] = None
    due_date: Optional[date] = None
    created_at: datetime
    updated_at: datetime
    creator: Optional[UserResponse] = None
    assignee: Optional[UserResponse] = None
    tags: list[TagResponse] = Field(default_factory=list)
    comment_count: int = 0

    model_config = {"from_attributes": True}

    def with_display_status(self, viewer_role: str | None = None) -> "IssueResponse":
        self.display_status = friendly_status(self.status, viewer_role)
        return self


# ---------- Comments ----------

class CommentCreate(BaseModel):
    body: str


class CommentResponse(BaseModel):
    id: UUID
    issue_id: UUID
    author_id: UUID
    body: str
    content_hash: str
    prev_hash: Optional[str] = None
    created_at: datetime
    author: Optional[UserResponse] = None

    model_config = {"from_attributes": True}


# ---------- Timeline ----------

class TimelineEntry(BaseModel):
    type: str  # "comment" or "status_change"
    created_at: datetime
    actor: Optional[UserResponse] = None
    # comment fields
    body: Optional[str] = None
    content_hash: Optional[str] = None
    # status change fields
    old_status: Optional[str] = None
    new_status: Optional[str] = None
    old_display: Optional[str] = None
    new_display: Optional[str] = None
    reason: Optional[str] = None


# ---------- Audit ----------

class AuditEntry(BaseModel):
    id: UUID
    table_name: str
    record_id: UUID
    action: str
    actor_id: Optional[UUID] = None
    old_values: Optional[dict[str, Any]] = None
    new_values: Optional[dict[str, Any]] = None
    content_hash: str
    prev_hash: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
