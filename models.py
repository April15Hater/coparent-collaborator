"""SQLAlchemy ORM models for Co-Parenting Board."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    JSON,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.types import TypeDecorator, CHAR


class UUIDType(TypeDecorator):
    """Platform-agnostic UUID type. Uses CHAR(36) on all backends."""
    impl = CHAR(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            return str(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return uuid.UUID(value)
        return value


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(UUIDType, primary_key=True, default=new_uuid)
    email = Column(Text, unique=True, nullable=False)
    display_name = Column(Text, nullable=False)
    role = Column(Text, nullable=False)  # parent_a or parent_b
    created_at = Column(DateTime(timezone=True), default=utcnow)

    issues_created = relationship(
        "Issue", back_populates="creator", foreign_keys="Issue.created_by"
    )
    issues_assigned = relationship(
        "Issue", back_populates="assignee", foreign_keys="Issue.assigned_to"
    )
    comments = relationship("Comment", back_populates="author")
    emails = relationship("UserEmail", back_populates="user")


class Issue(Base):
    __tablename__ = "issues"

    id = Column(UUIDType, primary_key=True, default=new_uuid)
    title = Column(Text, nullable=False)
    description = Column(Text)
    status = Column(Text, nullable=False, default="open")
    priority = Column(Text, default="normal")
    category = Column(Text, nullable=False)
    created_by = Column(UUIDType, ForeignKey("users.id"), nullable=False)
    assigned_to = Column(UUIDType, ForeignKey("users.id"), nullable=True)
    due_date = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    creator = relationship("User", back_populates="issues_created", foreign_keys=[created_by])
    assignee = relationship("User", back_populates="issues_assigned", foreign_keys=[assigned_to])
    comments = relationship("Comment", back_populates="issue", order_by="Comment.created_at")
    status_logs = relationship("IssueStatusLog", back_populates="issue", order_by="IssueStatusLog.created_at")
    tags = relationship("Tag", secondary="issue_tags", back_populates="issues")


class Tag(Base):
    __tablename__ = "tags"

    id = Column(UUIDType, primary_key=True, default=new_uuid)
    name = Column(Text, unique=True, nullable=False)
    color = Column(Text)

    issues = relationship("Issue", secondary="issue_tags", back_populates="tags")


class IssueTag(Base):
    __tablename__ = "issue_tags"

    issue_id = Column(UUIDType, ForeignKey("issues.id"), primary_key=True)
    tag_id = Column(UUIDType, ForeignKey("tags.id"), primary_key=True)


class Comment(Base):
    __tablename__ = "comments"

    id = Column(UUIDType, primary_key=True, default=new_uuid)
    issue_id = Column(UUIDType, ForeignKey("issues.id"), nullable=False)
    author_id = Column(UUIDType, ForeignKey("users.id"), nullable=False)
    body = Column(Text, nullable=False)
    content_hash = Column(Text, nullable=False)
    prev_hash = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    issue = relationship("Issue", back_populates="comments")
    author = relationship("User", back_populates="comments")


class IssueStatusLog(Base):
    __tablename__ = "issue_status_log"

    id = Column(UUIDType, primary_key=True, default=new_uuid)
    issue_id = Column(UUIDType, ForeignKey("issues.id"), nullable=False)
    old_status = Column(Text, nullable=True)
    new_status = Column(Text, nullable=False)
    changed_by = Column(UUIDType, ForeignKey("users.id"), nullable=False)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    issue = relationship("Issue", back_populates="status_logs")
    changer = relationship("User")


class UserEmail(Base):
    """Multiple email addresses can map to the same user account."""
    __tablename__ = "user_emails"

    id = Column(UUIDType, primary_key=True, default=new_uuid)
    user_id = Column(UUIDType, ForeignKey("users.id"), nullable=False)
    email = Column(Text, unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", back_populates="emails")


class NotificationPrefs(Base):
    """Per-user notification preferences."""
    __tablename__ = "notification_prefs"

    id = Column(UUIDType, primary_key=True, default=new_uuid)
    user_id = Column(UUIDType, ForeignKey("users.id"), nullable=False, unique=True)
    enabled = Column(Boolean, default=False)  # master switch — False until user opts in
    instant_comments = Column(Boolean, default=True)  # notify on new comments
    instant_status = Column(Boolean, default=True)  # notify on status changes
    daily_digest = Column(Boolean, default=False)  # daily summary email
    due_date_reminders = Column(Boolean, default=True)  # 7d, 3d, 1d before due
    digest_hour = Column(Text, default="08:00")  # time for daily digest (HH:MM)
    notify_email = Column(Text, nullable=True)  # override email (default: user.email)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user = relationship("User")


class TopicMute(Base):
    """Per-user, per-topic mute. Muted topics skip notifications."""
    __tablename__ = "topic_mutes"

    user_id = Column(UUIDType, ForeignKey("users.id"), primary_key=True)
    issue_id = Column(UUIDType, ForeignKey("issues.id"), primary_key=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class NotificationLog(Base):
    """Track sent notifications to avoid duplicates."""
    __tablename__ = "notification_log"

    id = Column(UUIDType, primary_key=True, default=new_uuid)
    user_id = Column(UUIDType, ForeignKey("users.id"), nullable=False)
    notification_type = Column(Text, nullable=False)  # instant_comment, instant_status, digest, due_date
    reference_id = Column(UUIDType, nullable=True)  # comment_id or issue_id
    sent_at = Column(DateTime(timezone=True), default=utcnow)

    user = relationship("User")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(UUIDType, primary_key=True, default=new_uuid)
    table_name = Column(Text, nullable=False)
    record_id = Column(UUIDType, nullable=False)
    action = Column(Text, nullable=False)
    actor_id = Column(UUIDType, ForeignKey("users.id"), nullable=True)
    old_values = Column(JSON, nullable=True)
    new_values = Column(JSON, nullable=True)
    content_hash = Column(Text, nullable=False)
    prev_hash = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    actor = relationship("User")
