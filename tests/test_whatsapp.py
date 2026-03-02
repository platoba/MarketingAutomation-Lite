"""Tests for WhatsApp campaign functionality."""
import pytest
from datetime import datetime, timedelta
from app.models.whatsapp_campaign import WhatsAppCampaign, WhatsAppLog, WhatsAppStatus, WhatsAppProvider
from app.models import Contact
from app.models import Segment
from app.whatsapp_service import WhatsAppService


def test_create_whatsapp_campaign(client, auth_headers, db_session):
    """Test creating a WhatsApp campaign."""
    response = client.post(
        "/api/v1/whatsapp/campaigns",
        json={
            "name": "Product Launch WhatsApp",
            "message": "🎉 New product launching tomorrow! Check it out: https://example.com",
            "provider": "twilio"
        },
        headers=auth_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Product Launch WhatsApp"
    assert data["status"] == "draft"
    assert data["provider"] == "twilio"


def test_list_whatsapp_campaigns(client, auth_headers, db_session):
    """Test listing WhatsApp campaigns."""
    # Create test campaigns
    campaign1 = WhatsAppCampaign(name="Campaign 1", message="Test 1", provider=WhatsAppProvider.TWILIO)
    campaign2 = WhatsAppCampaign(name="Campaign 2", message="Test 2", provider=WhatsAppProvider.TWILIO)
    db_session.add_all([campaign1, campaign2])
    db_session.commit()

    response = client.get("/api/v1/whatsapp/campaigns", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2


def test_get_whatsapp_campaign(client, auth_headers, db_session):
    """Test getting a specific WhatsApp campaign."""
    campaign = WhatsAppCampaign(name="Test Campaign", message="Hello World", provider=WhatsAppProvider.TWILIO)
    db_session.add(campaign)
    db_session.commit()

    response = client.get(f"/api/v1/whatsapp/campaigns/{campaign.id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Campaign"
    assert data["message"] == "Hello World"


def test_update_whatsapp_campaign(client, auth_headers, db_session):
    """Test updating a WhatsApp campaign."""
    campaign = WhatsAppCampaign(name="Old Name", message="Old Message", provider=WhatsAppProvider.TWILIO)
    db_session.add(campaign)
    db_session.commit()

    response = client.patch(
        f"/api/v1/whatsapp/campaigns/{campaign.id}",
        json={"name": "New Name", "message": "New Message"},
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "New Name"
    assert data["message"] == "New Message"


def test_delete_whatsapp_campaign(client, auth_headers, db_session):
    """Test deleting a WhatsApp campaign."""
    campaign = WhatsAppCampaign(name="To Delete", message="Bye", provider=WhatsAppProvider.TWILIO)
    db_session.add(campaign)
    db_session.commit()
    campaign_id = campaign.id

    response = client.delete(f"/api/v1/whatsapp/campaigns/{campaign_id}", headers=auth_headers)
    assert response.status_code == 204

    # Verify deletion
    deleted = db_session.query(WhatsAppCampaign).filter(WhatsAppCampaign.id == campaign_id).first()
    assert deleted is None


def test_whatsapp_campaign_with_segment(client, auth_headers, db_session):
    """Test creating a WhatsApp campaign with segment targeting."""
    # Create segment
    segment = Segment(name="VIP Customers", description="High-value customers")
    db_session.add(segment)
    db_session.commit()

    response = client.post(
        "/api/v1/whatsapp/campaigns",
        json={
            "name": "VIP Exclusive",
            "message": "Exclusive offer for our VIP customers!",
            "segment_id": segment.id,
            "provider": "twilio"
        },
        headers=auth_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert data["segment_id"] == segment.id


def test_whatsapp_campaign_with_media(client, auth_headers, db_session):
    """Test creating a WhatsApp campaign with media attachment."""
    response = client.post(
        "/api/v1/whatsapp/campaigns",
        json={
            "name": "Product Image",
            "message": "Check out our new product!",
            "media_url": "https://example.com/product.jpg",
            "provider": "twilio"
        },
        headers=auth_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert data["media_url"] == "https://example.com/product.jpg"


def test_get_campaign_analytics(client, auth_headers, db_session):
    """Test getting WhatsApp campaign analytics."""
    campaign = WhatsAppCampaign(
        name="Analytics Test",
        message="Test",
        provider=WhatsAppProvider.TWILIO,
        status=WhatsAppStatus.SENT,
        total_recipients=100,
        delivered_count=95,
        failed_count=5,
        read_count=80,
        replied_count=20
    )
    db_session.add(campaign)
    db_session.commit()

    response = client.get(f"/api/v1/whatsapp/campaigns/{campaign.id}/analytics", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total_recipients"] == 100
    assert data["delivered_count"] == 95
    assert data["delivery_rate"] == 95.0
    assert data["read_rate"] == pytest.approx(84.21, 0.01)
    assert data["reply_rate"] == pytest.approx(21.05, 0.01)


def test_get_campaign_logs(client, auth_headers, db_session):
    """Test getting WhatsApp campaign delivery logs."""
    campaign = WhatsAppCampaign(name="Log Test", message="Test", provider=WhatsAppProvider.TWILIO)
    contact = Contact(email="test@example.com", phone="+1234567890")
    db_session.add_all([campaign, contact])
    db_session.commit()

    log = WhatsAppLog(
        campaign_id=campaign.id,
        contact_id=contact.id,
        phone_number=contact.phone,
        status="delivered",
        provider_message_id="SM123456",
        sent_at=datetime.utcnow()
    )
    db_session.add(log)
    db_session.commit()

    response = client.get(f"/api/v1/whatsapp/campaigns/{campaign.id}/logs", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["status"] == "delivered"
    assert data[0]["provider_message_id"] == "SM123456"


def test_filter_campaigns_by_status(client, auth_headers, db_session):
    """Test filtering WhatsApp campaigns by status."""
    draft = WhatsAppCampaign(name="Draft", message="Test", status=WhatsAppStatus.DRAFT, provider=WhatsAppProvider.TWILIO)
    sent = WhatsAppCampaign(name="Sent", message="Test", status=WhatsAppStatus.SENT, provider=WhatsAppProvider.TWILIO)
    db_session.add_all([draft, sent])
    db_session.commit()

    response = client.get("/api/v1/whatsapp/campaigns?status=draft", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert all(c["status"] == "draft" for c in data)


def test_scheduled_whatsapp_campaign(client, auth_headers, db_session):
    """Test creating a scheduled WhatsApp campaign."""
    scheduled_time = datetime.utcnow() + timedelta(hours=2)
    response = client.post(
        "/api/v1/whatsapp/campaigns",
        json={
            "name": "Scheduled Campaign",
            "message": "This will be sent later",
            "scheduled_at": scheduled_time.isoformat(),
            "provider": "twilio"
        },
        headers=auth_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "draft"
    assert data["scheduled_at"] is not None
