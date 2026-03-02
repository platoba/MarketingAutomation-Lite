"""Simplified WhatsApp tests without auth."""
import pytest
from app.models.whatsapp_campaign import WhatsAppCampaign, WhatsAppStatus, WhatsAppProvider


@pytest.mark.asyncio
async def test_whatsapp_campaign_model():
    """Test WhatsApp campaign model creation."""
    campaign = WhatsAppCampaign(
        name="Test Campaign",
        message="Hello World",
        provider=WhatsAppProvider.TWILIO,
        status=WhatsAppStatus.DRAFT
    )
    assert campaign.name == "Test Campaign"
    assert campaign.message == "Hello World"
    assert campaign.provider == WhatsAppProvider.TWILIO
    assert campaign.status == WhatsAppStatus.DRAFT


@pytest.mark.asyncio
async def test_whatsapp_status_enum():
    """Test WhatsApp status enum values."""
    assert WhatsAppStatus.DRAFT == "draft"
    assert WhatsAppStatus.SCHEDULED == "scheduled"
    assert WhatsAppStatus.SENDING == "sending"
    assert WhatsAppStatus.SENT == "sent"
    assert WhatsAppStatus.FAILED == "failed"
    assert WhatsAppStatus.CANCELLED == "cancelled"


@pytest.mark.asyncio
async def test_whatsapp_provider_enum():
    """Test WhatsApp provider enum values."""
    assert WhatsAppProvider.TWILIO == "twilio"
    assert WhatsAppProvider.MESSAGEBIRD == "messagebird"
    assert WhatsAppProvider.VONAGE == "vonage"
    assert WhatsAppProvider.WHATSAPP_BUSINESS_API == "whatsapp_business_api"
