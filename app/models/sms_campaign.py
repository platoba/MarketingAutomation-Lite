"""SMS Campaign Models"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class SMSStatus(str, enum.Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"


class SMSCampaign(Base):
    __tablename__ = "sms_campaigns"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)  # SMS content (max 160 chars recommended)
    status = Column(SQLEnum(SMSStatus), default=SMSStatus.DRAFT)
    
    # Targeting
    segment_id = Column(Integer, ForeignKey("segments.id"), nullable=True)
    
    # Scheduling
    scheduled_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    
    # Stats
    total_recipients = Column(Integer, default=0)
    delivered_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    
    # SMS Provider Config
    provider = Column(String(50), default="twilio")  # twilio, vonage, aliyun
    sender_id = Column(String(20), nullable=True)  # Sender name/number
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"))
    
    # Relationships
    segment = relationship("Segment", back_populates="sms_campaigns")
    logs = relationship("SMSLog", back_populates="campaign", cascade="all, delete-orphan")


class SMSLog(Base):
    __tablename__ = "sms_logs"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("sms_campaigns.id"), nullable=False)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=False)
    
    phone_number = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)
    
    # Delivery Status
    status = Column(String(20), default="pending")  # pending, sent, delivered, failed
    provider_message_id = Column(String(255), nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Timestamps
    sent_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    campaign = relationship("SMSCampaign", back_populates="logs")
    contact = relationship("Contact")
