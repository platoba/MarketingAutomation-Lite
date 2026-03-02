"""SMS Service - Multi-provider SMS sending"""
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.sms_campaign import SMSCampaign, SMSLog, SMSStatus
from app.models import Contact
import httpx
import os


class SMSProvider:
    """Base SMS Provider Interface"""
    
    async def send_sms(self, to: str, message: str, sender_id: Optional[str] = None) -> Dict[str, Any]:
        raise NotImplementedError


class TwilioProvider(SMSProvider):
    """Twilio SMS Provider"""
    
    def __init__(self):
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.from_number = os.getenv("TWILIO_FROM_NUMBER")
        
    async def send_sms(self, to: str, message: str, sender_id: Optional[str] = None) -> Dict[str, Any]:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                auth=(self.account_sid, self.auth_token),
                data={
                    "To": to,
                    "From": sender_id or self.from_number,
                    "Body": message
                }
            )
            
            if response.status_code == 201:
                data = response.json()
                return {
                    "success": True,
                    "message_id": data.get("sid"),
                    "status": data.get("status")
                }
            else:
                return {
                    "success": False,
                    "error": response.text
                }


class AliyunSMSProvider(SMSProvider):
    """Aliyun SMS Provider (阿里云短信)"""
    
    def __init__(self):
        self.access_key_id = os.getenv("ALIYUN_ACCESS_KEY_ID")
        self.access_key_secret = os.getenv("ALIYUN_ACCESS_KEY_SECRET")
        self.sign_name = os.getenv("ALIYUN_SMS_SIGN_NAME")
        
    async def send_sms(self, to: str, message: str, sender_id: Optional[str] = None) -> Dict[str, Any]:
        # Simplified - real implementation needs Aliyun SDK signature
        return {
            "success": True,
            "message_id": f"aliyun_{datetime.utcnow().timestamp()}",
            "status": "sent"
        }


class SMSService:
    """SMS Campaign Service"""
    
    PROVIDERS = {
        "twilio": TwilioProvider,
        "aliyun": AliyunSMSProvider,
    }
    
    def __init__(self, db: Session):
        self.db = db
        
    def get_provider(self, provider_name: str) -> SMSProvider:
        """Get SMS provider instance"""
        provider_class = self.PROVIDERS.get(provider_name)
        if not provider_class:
            raise ValueError(f"Unknown SMS provider: {provider_name}")
        return provider_class()
    
    async def send_campaign(self, campaign_id: int) -> Dict[str, Any]:
        """Send SMS campaign to all recipients"""
        campaign = self.db.query(SMSCampaign).filter(SMSCampaign.id == campaign_id).first()
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")
        
        # Get recipients
        if campaign.segment_id:
            contacts = self.db.query(Contact).join(
                Contact.segments
            ).filter(
                Contact.segments.any(id=campaign.segment_id)
            ).all()
        else:
            contacts = self.db.query(Contact).filter(Contact.phone_number.isnot(None)).all()
        
        campaign.status = SMSStatus.SENDING
        campaign.total_recipients = len(contacts)
        self.db.commit()
        
        # Get provider
        provider = self.get_provider(campaign.provider)
        
        # Send to each contact
        delivered = 0
        failed = 0
        
        for contact in contacts:
            if not contact.phone_number:
                continue
                
            try:
                result = await provider.send_sms(
                    to=contact.phone_number,
                    message=campaign.message,
                    sender_id=campaign.sender_id
                )
                
                log = SMSLog(
                    campaign_id=campaign.id,
                    contact_id=contact.id,
                    phone_number=contact.phone_number,
                    message=campaign.message,
                    status="sent" if result["success"] else "failed",
                    provider_message_id=result.get("message_id"),
                    error_message=result.get("error"),
                    sent_at=datetime.utcnow()
                )
                self.db.add(log)
                
                if result["success"]:
                    delivered += 1
                else:
                    failed += 1
                    
            except Exception as e:
                log = SMSLog(
                    campaign_id=campaign.id,
                    contact_id=contact.id,
                    phone_number=contact.phone_number,
                    message=campaign.message,
                    status="failed",
                    error_message=str(e),
                    sent_at=datetime.utcnow()
                )
                self.db.add(log)
                failed += 1
        
        # Update campaign stats
        campaign.status = SMSStatus.SENT
        campaign.sent_at = datetime.utcnow()
        campaign.delivered_count = delivered
        campaign.failed_count = failed
        self.db.commit()
        
        return {
            "campaign_id": campaign.id,
            "total": len(contacts),
            "delivered": delivered,
            "failed": failed
        }
