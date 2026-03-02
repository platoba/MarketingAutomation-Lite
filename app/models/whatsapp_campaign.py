"""WhatsApp campaign models."""
from datetime import datetime
from enum import Enum
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum as SQLEnum, JSON
from sqlalchemy.orm import relationship
from app.database import Base


class WhatsAppStatus(str, Enum):
    """WhatsApp message status."""
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WhatsAppProvider(str, Enum):
    """WhatsApp provider."""
    TWILIO = "twilio"
    MESSAGEBIRD = "messagebird"
    VONAGE = "vonage"
    WHATSAPP_BUSINESS_API = "whatsapp_business_api"


class WhatsAppCampaign(Base):
    """WhatsApp campaign model."""
    __tablename__ = "whatsapp_campaigns"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    media_url = Column(String(512), nullable=True)  # Image/video/document URL
    provider = Column(SQLEnum(WhatsAppProvider), default=WhatsAppProvider.TWILIO)
    status = Column(SQLEnum(WhatsAppStatus), default=WhatsAppStatus.DRAFT)
    segment_id = Column(Integer, ForeignKey("segments.id"), nullable=True)
    scheduled_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    total_recipients = Column(Integer, default=0)
    delivered_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    read_count = Column(Integer, default=0)
    replied_count = Column(Integer, default=0)
    extra_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    segment = relationship("Segment", back_populates="whatsapp_campaigns")
    logs = relationship("WhatsAppLog", back_populates="campaign", cascade="all, delete-orphan")


class WhatsAppLog(Base):
    """WhatsApp delivery log."""
    __tablename__ = "whatsapp_logs"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("whatsapp_campaigns.id"), nullable=False)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=False)
    phone_number = Column(String(20), nullable=False)
    status = Column(String(50), nullable=False)  # queued, sent, delivered, read, failed
    provider_message_id = Column(String(255), nullable=True)
    error_message = Column(Text, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    read_at = Column(DateTime, nullable=True)
    replied_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    campaign = relationship("WhatsAppCampaign", back_populates="logs")
    contact = relationship("Contact")
