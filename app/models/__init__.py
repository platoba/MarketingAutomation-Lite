"""SQLAlchemy models — portable across SQLite and PostgreSQL."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import relationship

from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


def new_uuid():
    return str(uuid.uuid4())


# ── Many-to-many association tables ─────────────────────
contact_tags = Table(
    "contact_tags",
    Base.metadata,
    Column("contact_id", String(36), ForeignKey("contacts.id"), primary_key=True),
    Column("tag_id", String(36), ForeignKey("tags.id"), primary_key=True),
)

contact_segments = Table(
    "contact_segments",
    Base.metadata,
    Column("contact_id", String(36), ForeignKey("contacts.id"), primary_key=True),
    Column("segment_id", String(36), ForeignKey("segments.id"), primary_key=True),
)


# ── Contact ─────────────────────────────────────────────
class Contact(Base):
    __tablename__ = "contacts"

    id = Column(String(36), primary_key=True, default=new_uuid)
    email = Column(String(320), unique=True, nullable=False, index=True)
    first_name = Column(String(100), default="")
    last_name = Column(String(100), default="")
    phone = Column(String(30), default="")
    country = Column(String(3), default="")
    language = Column(String(10), default="en")
    custom_fields = Column(Text, default="{}")  # JSON stored as text for portability
    subscribed = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    tags = relationship("Tag", secondary=contact_tags, back_populates="contacts", lazy="selectin")
    segments = relationship("Segment", secondary=contact_segments, back_populates="contacts", lazy="selectin")


# ── Tag ─────────────────────────────────────────────────
class Tag(Base):
    __tablename__ = "tags"

    id = Column(String(36), primary_key=True, default=new_uuid)
    name = Column(String(100), unique=True, nullable=False)
    color = Column(String(7), default="#3B82F6")
    created_at = Column(DateTime, default=utcnow)

    contacts = relationship("Contact", secondary=contact_tags, back_populates="tags", lazy="selectin")


# ── Segment ─────────────────────────────────────────────
class Segment(Base):
    __tablename__ = "segments"

    id = Column(String(36), primary_key=True, default=new_uuid)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    rules = Column(Text, default="[]")  # JSON stored as text
    created_at = Column(DateTime, default=utcnow)

    contacts = relationship("Contact", secondary=contact_segments, back_populates="segments", lazy="selectin")


# ── Campaign ────────────────────────────────────────────
class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(String(36), primary_key=True, default=new_uuid)
    name = Column(String(300), nullable=False)
    subject = Column(String(500), nullable=False)
    from_name = Column(String(200), default="")
    from_email = Column(String(320), default="")
    html_body = Column(Text, default="")
    text_body = Column(Text, default="")
    status = Column(String(20), default="draft")  # draft|scheduled|sending|sent|paused
    scheduled_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    segment_id = Column(String(36), ForeignKey("segments.id"), nullable=True)
    total_sent = Column(Integer, default=0)
    total_opened = Column(Integer, default=0)
    total_clicked = Column(Integer, default=0)
    total_bounced = Column(Integer, default=0)
    total_unsubscribed = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# ── Email Event ─────────────────────────────────────────
class EmailEvent(Base):
    """Tracks individual email delivery events."""

    __tablename__ = "email_events"

    id = Column(String(36), primary_key=True, default=new_uuid)
    campaign_id = Column(String(36), ForeignKey("campaigns.id"), nullable=False)
    contact_id = Column(String(36), ForeignKey("contacts.id"), nullable=False)
    event_type = Column(String(20), nullable=False)  # sent|delivered|opened|clicked|bounced|unsubscribed
    metadata_ = Column("metadata", Text, default="{}")
    created_at = Column(DateTime, default=utcnow)


# ── Workflow ────────────────────────────────────────────
class Workflow(Base):
    """Automation workflow (e.g., welcome series, abandoned cart)."""

    __tablename__ = "workflows"

    id = Column(String(36), primary_key=True, default=new_uuid)
    name = Column(String(300), nullable=False)
    trigger_type = Column(String(30), default="manual")  # signup|tag_added|segment_entered|manual|webhook
    trigger_config = Column(Text, default="{}")
    steps = Column(Text, default="[]")  # JSON: [{type, config}]
    active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# ── Workflow Execution Log ──────────────────────────────
class WorkflowLog(Base):
    """Tracks workflow execution history."""

    __tablename__ = "workflow_logs"

    id = Column(String(36), primary_key=True, default=new_uuid)
    workflow_id = Column(String(36), ForeignKey("workflows.id"), nullable=False)
    contact_id = Column(String(36), ForeignKey("contacts.id"), nullable=True)
    step_index = Column(Integer, default=0)
    status = Column(String(20), default="running")  # running|completed|failed|skipped
    result = Column(Text, default="{}")
    created_at = Column(DateTime, default=utcnow)


# ── Email Template ──────────────────────────────────────
class EmailTemplate(Base):
    """Reusable email template with Jinja2 variables."""

    __tablename__ = "email_templates"

    id = Column(String(36), primary_key=True, default=new_uuid)
    name = Column(String(300), nullable=False, unique=True)
    subject = Column(String(500), nullable=False)
    html_body = Column(Text, default="")
    text_body = Column(Text, default="")
    variables = Column(Text, default="[]")  # JSON list of variable names
    category = Column(String(100), default="general")
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# ── User ────────────────────────────────────────────────
class User(Base):
    """Admin user for the dashboard."""

    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=new_uuid)
    email = Column(String(320), unique=True, nullable=False)
    hashed_password = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)
