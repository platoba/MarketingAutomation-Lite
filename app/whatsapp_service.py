"""WhatsApp service with multi-provider support."""
import logging
from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session

try:
    from twilio.rest import Client as TwilioClient
except ImportError:
    TwilioClient = None

from app.models.whatsapp_campaign import WhatsAppCampaign, WhatsAppLog, WhatsAppStatus, WhatsAppProvider
from app.models import Contact
from app.config import get_settings
settings = get_settings()

logger = logging.getLogger(__name__)


class WhatsAppService:
    """WhatsApp campaign service."""

    def __init__(self, db: Session):
        self.db = db

    def send_campaign(self, campaign_id: int) -> dict:
        """Send WhatsApp campaign to all recipients."""
        campaign = self.db.query(WhatsAppCampaign).filter(WhatsAppCampaign.id == campaign_id).first()
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")

        if campaign.status not in [WhatsAppStatus.DRAFT, WhatsAppStatus.SCHEDULED]:
            raise ValueError(f"Campaign {campaign_id} is not in sendable state")

        # Get recipients
        if campaign.segment_id:
            contacts = self.db.query(Contact).join(
                Contact.segments
            ).filter(Contact.segments.any(id=campaign.segment_id)).all()
        else:
            contacts = self.db.query(Contact).all()

        # Filter contacts with phone numbers
        recipients = [c for c in contacts if c.phone]
        campaign.total_recipients = len(recipients)
        campaign.status = WhatsAppStatus.SENDING
        self.db.commit()

        # Send messages
        sent_count = 0
        failed_count = 0

        for contact in recipients:
            try:
                result = self._send_message(
                    provider=campaign.provider,
                    to_phone=contact.phone,
                    message=campaign.message,
                    media_url=campaign.media_url
                )

                log = WhatsAppLog(
                    campaign_id=campaign.id,
                    contact_id=contact.id,
                    phone_number=contact.phone,
                    status="sent",
                    provider_message_id=result.get("message_id"),
                    sent_at=datetime.utcnow()
                )
                self.db.add(log)
                sent_count += 1

            except Exception as e:
                logger.error(f"Failed to send WhatsApp to {contact.phone}: {e}")
                log = WhatsAppLog(
                    campaign_id=campaign.id,
                    contact_id=contact.id,
                    phone_number=contact.phone,
                    status="failed",
                    error_message=str(e)
                )
                self.db.add(log)
                failed_count += 1

        campaign.status = WhatsAppStatus.SENT
        campaign.sent_at = datetime.utcnow()
        campaign.delivered_count = sent_count
        campaign.failed_count = failed_count
        self.db.commit()

        return {
            "campaign_id": campaign.id,
            "total_recipients": campaign.total_recipients,
            "sent": sent_count,
            "failed": failed_count
        }

    def _send_message(self, provider: WhatsAppProvider, to_phone: str, message: str, media_url: Optional[str] = None) -> dict:
        """Send WhatsApp message via provider."""
        if provider == WhatsAppProvider.TWILIO:
            return self._send_twilio(to_phone, message, media_url)
        elif provider == WhatsAppProvider.MESSAGEBIRD:
            return self._send_messagebird(to_phone, message, media_url)
        elif provider == WhatsAppProvider.VONAGE:
            return self._send_vonage(to_phone, message, media_url)
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    def _send_twilio(self, to_phone: str, message: str, media_url: Optional[str] = None) -> dict:
        """Send via Twilio WhatsApp API."""
        if TwilioClient is None:
            raise ImportError("Twilio SDK not installed. Install with: pip install twilio")
        
        client = TwilioClient(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        
        msg_params = {
            "from_": f"whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}",
            "to": f"whatsapp:{to_phone}",
            "body": message
        }
        
        if media_url:
            msg_params["media_url"] = [media_url]

        msg = client.messages.create(**msg_params)
        return {"message_id": msg.sid, "status": msg.status}

    def _send_messagebird(self, to_phone: str, message: str, media_url: Optional[str] = None) -> dict:
        """Send via MessageBird WhatsApp API."""
        # Placeholder for MessageBird implementation
        raise NotImplementedError("MessageBird provider not yet implemented")

    def _send_vonage(self, to_phone: str, message: str, media_url: Optional[str] = None) -> dict:
        """Send via Vonage WhatsApp API."""
        # Placeholder for Vonage implementation
        raise NotImplementedError("Vonage provider not yet implemented")
