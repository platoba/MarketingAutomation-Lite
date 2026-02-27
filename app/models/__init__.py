"""SQLAlchemy models."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text, Table,
    JSON, Float,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


# Many-to-many: contacts <-> tags
contact_tags = Table(
    "contact_tags",
    Base.metadata,
    Column("contact_id", UUID(as_uuid=True), ForeignKey("contacts.id"), primary_key=True),
    Column("tag_id", UUID(as_uuid=True), ForeignKey("tags.id"), primary_key=True),
)

# Many-to-many: contacts <-> segments
contact_segments = Table(
    "contact_segments",
    Base.metadata,
    Column("contact_id", UUID(as_uuid=True), ForeignKey("contacts.id"), primary_key=True),
    Column("segment_id", UUID(as_uuid=True), ForeignKey("segments.id"), primary_key=True),
)


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(320), unique=True, nullable=False, index=True)
    first_name = Column(String(100), default="")
    last_name = Column(String(100), default="")
    phone = Column(String(30), default="")
    country = Column(String(3), default="")
    language = Column(String(10), default="en")
    custom_fields = Column(JSON, default=dict)
    subscribed = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    tags = relationship("Tag", secondary=contact_tags, back_populates="contacts")
    segments = relationship("Segment", secondary=contact_segments, back_populates="contacts")


class Tag(Base):
    __tablename__ = "tags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), unique=True, nullable=False)
    color = Column(String(7), default="#3B82F6")
    created_at = Column(DateTime(timezone=True), default=utcnow)

    contacts = relationship("Contact", secondary=contact_tags, back_populates="tags")


class Segment(Base):
    __tablename__ = "segments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    rules = Column(JSON, default=list)  # filter rules for dynamic segments
    created_at = Column(DateTime(timezone=True), default=utcnow)

    contacts = relationship("Contact", secondary=contact_segments, back_populates="segments")


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(300), nullable=False)
    subject = Column(String(500), nullable=False)
    from_name = Column(String(200), default="")
    from_email = Column(String(320), default="")
    html_body = Column(Text, default="")
    text_body = Column(Text, default="")
    status = Column(
        Enum("draft", "scheduled", "sending", "sent", "paused", name="campaign_status"),
        default="draft",
    )
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    segment_id = Column(UUID(as_uuid=True), ForeignKey("segments.id"), nullable=True)
    total_sent = Column(Integer, default=0)
    total_opened = Column(Integer, default=0)
    total_clicked = Column(Integer, default=0)
    total_bounced = Column(Integer, default=0)
    total_unsubscribed = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class EmailEvent(Base):
    """Tracks individual email delivery events."""
    __tablename__ = "email_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id"), nullable=False)
    event_type = Column(
        Enum("sent", "delivered", "opened", "clicked", "bounced", "unsubscribed", name="event_type"),
        nullable=False,
    )
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class Workflow(Base):
    """Automation workflow (e.g., welcome series, abandoned cart)."""
    __tablename__ = "workflows"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(300), nullable=False)
    trigger_type = Column(
        Enum("signup", "tag_added", "segment_entered", "manual", "webhook", name="trigger_type"),
        default="manual",
    )
    trigger_config = Column(JSON, default=dict)
    steps = Column(JSON, default=list)  # [{type: "email"|"delay"|"condition", ...}]
    active = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class EmailTemplate(Base):
    """Reusable email template with Jinja2 variables."""
    __tablename__ = "email_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(300), nullable=False, unique=True)
    subject = Column(String(500), nullable=False)
    html_body = Column(Text, default="")
    text_body = Column(Text, default="")
    variables = Column(JSON, default=list)  # expected variable names
    category = Column(String(100), default="general")
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class User(Base):
    """Admin user for the dashboard."""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(320), unique=True, nullable=False)
    hashed_password = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)
