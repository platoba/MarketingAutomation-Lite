"""A/B Testing models."""

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text

from app.database import Base
from app.models import new_uuid, utcnow


class ABTest(Base):
    """A/B test for a campaign — split test subject lines, content, or send times."""

    __tablename__ = "ab_tests"

    id = Column(String(36), primary_key=True, default=new_uuid)
    campaign_id = Column(String(36), ForeignKey("campaigns.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    test_type = Column(String(30), default="subject")  # subject|content|send_time
    status = Column(String(20), default="draft")  # draft|running|completed|cancelled
    winner_variant_id = Column(String(36), nullable=True)
    winner_metric = Column(String(20), default="open_rate")  # open_rate|click_rate|conversion
    auto_select_winner = Column(Boolean, default=True)
    # Percentage of contacts for test (rest get winner variant)
    test_percentage = Column(Float, default=20.0)
    # Hours to wait before selecting winner
    wait_hours = Column(Integer, default=4)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class ABTestVariant(Base):
    """A variant within an A/B test."""

    __tablename__ = "ab_test_variants"

    id = Column(String(36), primary_key=True, default=new_uuid)
    ab_test_id = Column(String(36), ForeignKey("ab_tests.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)  # e.g., "Variant A", "Variant B"
    subject = Column(String(500), nullable=True)
    html_body = Column(Text, nullable=True)
    send_delay_minutes = Column(Integer, default=0)  # For send_time tests
    # Metrics
    total_sent = Column(Integer, default=0)
    total_opened = Column(Integer, default=0)
    total_clicked = Column(Integer, default=0)
    total_bounced = Column(Integer, default=0)
    open_rate = Column(Float, default=0.0)
    click_rate = Column(Float, default=0.0)
    is_winner = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)
