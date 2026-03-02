"""SMS Campaign API Endpoints"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

from app.database import get_db
from app.models.sms_campaign import SMSCampaign, SMSStatus, SMSLog
from app.services.sms_service import SMSService
from pydantic import BaseModel, Field


router = APIRouter(prefix="/sms", tags=["SMS Campaigns"])


class SMSCampaignCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    message: str = Field(..., min_length=1, max_length=1600)
    segment_id: int | None = None
    scheduled_at: datetime | None = None
    provider: str = Field(default="twilio", pattern="^(twilio|aliyun)$")
    sender_id: str | None = Field(None, max_length=20)


class SMSCampaignResponse(BaseModel):
    id: int
    name: str
    message: str
    status: SMSStatus
    total_recipients: int
    delivered_count: int
    failed_count: int
    created_at: datetime
    sent_at: datetime | None
    
    class Config:
        from_attributes = True


@router.post("/campaigns", response_model=SMSCampaignResponse, status_code=status.HTTP_201_CREATED)
def create_sms_campaign(
    campaign: SMSCampaignCreate,
    db: Session = Depends(get_db)
):
    """Create a new SMS campaign"""
    db_campaign = SMSCampaign(
        name=campaign.name,
        message=campaign.message,
        segment_id=campaign.segment_id,
        scheduled_at=campaign.scheduled_at,
        provider=campaign.provider,
        sender_id=campaign.sender_id,
        status=SMSStatus.DRAFT
    )
    db.add(db_campaign)
    db.commit()
    db.refresh(db_campaign)
    return db_campaign


@router.get("/campaigns", response_model=List[SMSCampaignResponse])
def list_sms_campaigns(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List all SMS campaigns"""
    campaigns = db.query(SMSCampaign).offset(skip).limit(limit).all()
    return campaigns


@router.get("/campaigns/{campaign_id}", response_model=SMSCampaignResponse)
def get_sms_campaign(
    campaign_id: int,
    db: Session = Depends(get_db)
):
    """Get SMS campaign by ID"""
    campaign = db.query(SMSCampaign).filter(SMSCampaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.post("/campaigns/{campaign_id}/send")
async def send_sms_campaign(
    campaign_id: int,
    db: Session = Depends(get_db)
):
    """Send SMS campaign immediately"""
    campaign = db.query(SMSCampaign).filter(SMSCampaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    if campaign.status not in [SMSStatus.DRAFT, SMSStatus.SCHEDULED]:
        raise HTTPException(status_code=400, detail="Campaign already sent or in progress")
    
    sms_service = SMSService(db)
    result = await sms_service.send_campaign(campaign_id)
    
    return {
        "message": "SMS campaign sent successfully",
        "stats": result
    }


@router.get("/campaigns/{campaign_id}/logs")
def get_sms_logs(
    campaign_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get SMS delivery logs for a campaign"""
    logs = db.query(SMSLog).filter(
        SMSLog.campaign_id == campaign_id
    ).offset(skip).limit(limit).all()
    
    return logs


@router.delete("/campaigns/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sms_campaign(
    campaign_id: int,
    db: Session = Depends(get_db)
):
    """Delete SMS campaign"""
    campaign = db.query(SMSCampaign).filter(SMSCampaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    db.delete(campaign)
    db.commit()
    return None
