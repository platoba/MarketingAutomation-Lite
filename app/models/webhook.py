"""Webhook models for event dispatch."""

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from app.database import Base
from app.models import new_uuid, utcnow


class WebhookEndpoint(Base):
    """Registered webhook endpoint to receive event notifications."""

    __tablename__ = "webhook_endpoints"

    id = Column(String(36), primary_key=True, default=new_uuid)
    url = Column(String(2048), nullable=False)
    secret = Column(String(200), nullable=True)  # HMAC signing secret
    events = Column(Text, default="[]")  # JSON list of event types to subscribe
    active = Column(Boolean, default=True)
    description = Column(String(500), default="")
    # Failure tracking
    consecutive_failures = Column(Integer, default=0)
    last_failure_at = Column(DateTime, nullable=True)
    last_success_at = Column(DateTime, nullable=True)
    total_deliveries = Column(Integer, default=0)
    total_failures = Column(Integer, default=0)
    # Auto-disable after N consecutive failures
    max_failures = Column(Integer, default=10)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class WebhookDelivery(Base):
    """Log of individual webhook delivery attempts."""

    __tablename__ = "webhook_deliveries"

    id = Column(String(36), primary_key=True, default=new_uuid)
    endpoint_id = Column(String(36), nullable=False, index=True)
    event_type = Column(String(100), nullable=False)
    payload = Column(Text, default="{}")
    response_status = Column(Integer, nullable=True)
    response_body = Column(Text, default="")
    success = Column(Boolean, default=False)
    duration_ms = Column(Integer, default=0)
    attempt = Column(Integer, default=1)
    created_at = Column(DateTime, default=utcnow)
