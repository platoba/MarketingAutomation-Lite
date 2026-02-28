"""Lead scoring models — rule-based + engagement-driven contact scoring."""

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base
from app.models import new_uuid, utcnow


class ScoringRule(Base):
    """Configurable scoring rule: award points for specific engagement events."""

    __tablename__ = "scoring_rules"

    id = Column(String(36), primary_key=True, default=new_uuid)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    event_type = Column(String(50), nullable=False)  # email_opened|email_clicked|form_submitted|page_visited|tag_added|unsubscribed|bounced
    condition = Column(Text, default="{}")  # JSON: optional filter (e.g., {"campaign_id": "..."})
    points = Column(Integer, nullable=False, default=1)  # can be negative for penalties
    max_per_contact = Column(Integer, default=0)  # 0 = unlimited
    decay_days = Column(Integer, default=0)  # 0 = no decay; N = points halve after N days
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class ContactScore(Base):
    """Materialized lead score per contact."""

    __tablename__ = "contact_scores"

    id = Column(String(36), primary_key=True, default=new_uuid)
    contact_id = Column(String(36), ForeignKey("contacts.id"), unique=True, nullable=False, index=True)
    total_score = Column(Float, default=0.0)
    engagement_score = Column(Float, default=0.0)  # from email opens/clicks
    profile_score = Column(Float, default=0.0)  # from completeness of profile data
    recency_score = Column(Float, default=0.0)  # time-decay component
    grade = Column(String(2), default="C")  # A+/A/B+/B/C/D/F
    lifecycle_stage = Column(String(30), default="subscriber")  # subscriber|lead|mql|sql|customer|evangelist|churned
    last_activity_at = Column(DateTime, nullable=True)
    score_updated_at = Column(DateTime, default=utcnow)
    created_at = Column(DateTime, default=utcnow)


class ScoreEvent(Base):
    """Individual scoring event log — audit trail of every point awarded/deducted."""

    __tablename__ = "score_events"

    id = Column(String(36), primary_key=True, default=new_uuid)
    contact_id = Column(String(36), ForeignKey("contacts.id"), nullable=False, index=True)
    rule_id = Column(String(36), ForeignKey("scoring_rules.id"), nullable=True)
    event_type = Column(String(50), nullable=False)
    points = Column(Float, nullable=False)
    reason = Column(String(500), default="")
    metadata_ = Column("metadata", Text, default="{}")
    created_at = Column(DateTime, default=utcnow)


class SuppressionList(Base):
    """Global suppression list — emails that should never be contacted."""

    __tablename__ = "suppression_list"

    id = Column(String(36), primary_key=True, default=new_uuid)
    email = Column(String(320), unique=True, nullable=False, index=True)
    reason = Column(String(50), nullable=False)  # bounce|complaint|unsubscribe|manual|compliance
    source = Column(String(100), default="")  # campaign_id, import, manual
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=utcnow)
