"""Tests for SMS Service"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from app.services.sms_service import SMSService, TwilioProvider, AliyunSMSProvider
from app.models.sms_campaign import SMSCampaign, SMSStatus, SMSLog
from app.models import Contact


@pytest.fixture
def mock_db():
    """Mock database session"""
    return MagicMock()


@pytest.fixture
def sms_service(mock_db):
    """SMS service instance"""
    return SMSService(mock_db)


class TestTwilioProvider:
    """Test Twilio SMS Provider"""
    
    @pytest.mark.asyncio
    @patch.dict('os.environ', {
        'TWILIO_ACCOUNT_SID': 'test_sid',
        'TWILIO_AUTH_TOKEN': 'test_token',
        'TWILIO_FROM_NUMBER': '+1234567890'
    })
    async def test_send_sms_success(self):
        """Test successful SMS send via Twilio"""
        provider = TwilioProvider()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {
                "sid": "SM123456",
                "status": "sent"
            }
            
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            result = await provider.send_sms(
                to="+1987654321",
                message="Test SMS"
            )
            
            assert result["success"] is True
            assert result["message_id"] == "SM123456"
            assert result["status"] == "sent"


class TestSMSService:
    """Test SMS Service"""
    
    def test_get_provider_twilio(self, sms_service):
        """Test getting Twilio provider"""
        provider = sms_service.get_provider("twilio")
        assert isinstance(provider, TwilioProvider)
    
    def test_get_provider_aliyun(self, sms_service):
        """Test getting Aliyun provider"""
        provider = sms_service.get_provider("aliyun")
        assert isinstance(provider, AliyunSMSProvider)
    
    def test_get_provider_invalid(self, sms_service):
        """Test invalid provider raises error"""
        with pytest.raises(ValueError, match="Unknown SMS provider"):
            sms_service.get_provider("invalid_provider")
    
    @pytest.mark.asyncio
    async def test_send_campaign(self, sms_service, mock_db):
        """Test sending SMS campaign"""
        # Mock campaign
        campaign = SMSCampaign(
            id=1,
            name="Test Campaign",
            message="Hello World",
            provider="twilio",
            status=SMSStatus.DRAFT
        )
        
        # Mock contacts
        contacts = [
            Contact(id=1, phone_number="+1111111111"),
            Contact(id=2, phone_number="+2222222222"),
        ]
        
        mock_db.query.return_value.filter.return_value.first.return_value = campaign
        mock_db.query.return_value.filter.return_value.all.return_value = contacts
        
        # Mock provider
        with patch.object(sms_service, 'get_provider') as mock_get_provider:
            mock_provider = AsyncMock()
            mock_provider.send_sms.return_value = {
                "success": True,
                "message_id": "SM123"
            }
            mock_get_provider.return_value = mock_provider
            
            result = await sms_service.send_campaign(1)
            
            assert result["campaign_id"] == 1
            assert result["total"] == 2
            assert result["delivered"] == 2
            assert result["failed"] == 0
            assert campaign.status == SMSStatus.SENT
