"""WhatsApp campaign API endpoints."""
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from app.database import get_db
from app.models.whatsapp_campaign import WhatsAppCampaign, WhatsAppLog, WhatsAppStatus, WhatsAppProvider
from app.whatsapp_service import WhatsAppService
from app.api.auth import get_current_user

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])


class WhatsAppCampaignCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    message: str = Field(..., min_length=1)
    media_url: Optional[str] = None
    provider: WhatsAppProvider = WhatsAppProvider.TWILIO
    segment_id: Optional[int] = None
    scheduled_at: Optional[datetime] = None


class WhatsAppCampaignUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    message: Optional[str] = Field(None, min_length=1)
    media_url: Optional[str] = None
    provider: Optional[WhatsAppProvider] = None
    segment_id: Optional[int] = None
    scheduled_at: Optional[datetime] = None
    status: Optional[WhatsAppStatus] = None


class WhatsAppCampaignResponse(BaseModel):
    id: int
    name: str
    message: str
    media_url: Optional[str]
    provider: WhatsAppProvider
    status: WhatsAppStatus
    segment_id: Optional[int]
    scheduled_at: Optional[datetime]
    sent_at: Optional[datetime]
    total_recipients: int
    delivered_count: int
    failed_count: int
    read_count: int
    replied_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WhatsAppLogResponse(BaseModel):
    id: int
    campaign_id: int
    contact_id: int
    phone_number: str
    status: str
    provider_message_id: Optional[str]
    error_message: Optional[str]
    sent_at: Optional[datetime]
    delivered_at: Optional[datetime]
    read_at: Optional[datetime]
    replied_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


@router.post("/campaigns", response_model=WhatsAppCampaignResponse, status_code=status.HTTP_201_CREATED)
def create_campaign(
    campaign: WhatsAppCampaignCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Create a new WhatsApp campaign."""
    db_campaign = WhatsAppCampaign(**campaign.dict())
    db.add(db_campaign)
    db.commit()
    db.refresh(db_campaign)
    return db_campaign


@router.get("/campaigns", response_model=List[WhatsAppCampaignResponse])
def list_campaigns(
    skip: int = 0,
    limit: int = 100,
    status: Optional[WhatsAppStatus] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """List all WhatsApp campaigns."""
    query = db.query(WhatsAppCampaign)
    if status:
        query = query.filter(WhatsAppCampaign.status == status)
    campaigns = query.offset(skip).limit(limit).all()
    return campaigns


@router.get("/campaigns/{campaign_id}", response_model=WhatsAppCampaignResponse)
def get_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get a specific WhatsApp campaign."""
    campaign = db.query(WhatsAppCampaign).filter(WhatsAppCampaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.patch("/campaigns/{campaign_id}", response_model=WhatsAppCampaignResponse)
def update_campaign(
    campaign_id: int,
    campaign_update: WhatsAppCampaignUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Update a WhatsApp campaign."""
    campaign = db.query(WhatsAppCampaign).filter(WhatsAppCampaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    for field, value in campaign_update.dict(exclude_unset=True).items():
        setattr(campaign, field, value)

    db.commit()
    db.refresh(campaign)
    return campaign


@router.delete("/campaigns/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Delete a WhatsApp campaign."""
    campaign = db.query(WhatsAppCampaign).filter(WhatsAppCampaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    db.delete(campaign)
    db.commit()


@router.post("/campaigns/{campaign_id}/send")
def send_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Send a WhatsApp campaign immediately."""
    service = WhatsAppService(db)
    try:
        result = service.send_campaign(campaign_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send campaign: {str(e)}")


@router.get("/campaigns/{campaign_id}/logs", response_model=List[WhatsAppLogResponse])
def get_campaign_logs(
    campaign_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get delivery logs for a WhatsApp campaign."""
    logs = db.query(WhatsAppLog).filter(
        WhatsAppLog.campaign_id == campaign_id
    ).offset(skip).limit(limit).all()
    return logs


@router.get("/campaigns/{campaign_id}/analytics")
def get_campaign_analytics(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get analytics for a WhatsApp campaign."""
    campaign = db.query(WhatsAppCampaign).filter(WhatsAppCampaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    logs = db.query(WhatsAppLog).filter(WhatsAppLog.campaign_id == campaign_id).all()

    return {
        "campaign_id": campaign.id,
        "name": campaign.name,
        "status": campaign.status,
        "total_recipients": campaign.total_recipients,
        "delivered_count": campaign.delivered_count,
        "failed_count": campaign.failed_count,
        "read_count": campaign.read_count,
        "replied_count": campaign.replied_count,
        "delivery_rate": round(campaign.delivered_count / campaign.total_recipients * 100, 2) if campaign.total_recipients > 0 else 0,
        "read_rate": round(campaign.read_count / campaign.delivered_count * 100, 2) if campaign.delivered_count > 0 else 0,
        "reply_rate": round(campaign.replied_count / campaign.delivered_count * 100, 2) if campaign.delivered_count > 0 else 0,
        "sent_at": campaign.sent_at,
        "logs_count": len(logs)
    }
