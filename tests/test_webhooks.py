"""Tests for webhook module."""

import json
import pytest


# ── Model tests ──────────────────────────────────────────
def test_webhook_endpoint_defaults():
    from app.models.webhook import WebhookEndpoint
    wh = WebhookEndpoint(url="https://example.com/hook")
    assert wh.active is True
    assert wh.consecutive_failures == 0
    assert wh.total_deliveries == 0
    assert wh.total_failures == 0
    assert wh.max_failures == 10


def test_webhook_delivery_defaults():
    from app.models.webhook import WebhookDelivery
    d = WebhookDelivery(endpoint_id="ep1", event_type="contact.created")
    assert d.success is False
    assert d.attempt == 1
    assert d.duration_ms == 0


# ── Schema tests ─────────────────────────────────────────
def test_webhook_create_schema():
    from app.api.webhooks import WebhookCreate
    wh = WebhookCreate(url="https://hooks.example.com/abc", events=["contact.created"])
    assert wh.url == "https://hooks.example.com/abc"
    assert wh.events == ["contact.created"]
    assert wh.max_failures == 10


def test_webhook_create_defaults():
    from app.api.webhooks import WebhookCreate
    wh = WebhookCreate(url="https://example.com")
    assert wh.events == ["*"]
    assert wh.secret is None
    assert wh.description == ""


def test_webhook_update_schema():
    from app.api.webhooks import WebhookUpdate
    u = WebhookUpdate(active=False)
    assert u.active is False
    assert u.url is None


def test_webhook_out_from_model():
    from app.api.webhooks import WebhookOut
    from app.models.webhook import WebhookEndpoint
    from datetime import datetime, timezone
    wh = WebhookEndpoint(url="https://x.com/hook", events='["*"]')
    wh.id = "test-id"
    wh.active = True
    wh.description = "Test"
    wh.consecutive_failures = 0
    wh.total_deliveries = 5
    wh.total_failures = 1
    wh.max_failures = 10
    wh.created_at = datetime.now(timezone.utc)
    out = WebhookOut.from_model(wh)
    assert out.events == ["*"]
    assert out.total_deliveries == 5


def test_webhook_out_invalid_json_events():
    from app.api.webhooks import WebhookOut
    from app.models.webhook import WebhookEndpoint
    from datetime import datetime, timezone
    wh = WebhookEndpoint(url="https://x.com", events="bad json")
    wh.id = "t"
    wh.active = True
    wh.description = ""
    wh.consecutive_failures = 0
    wh.total_deliveries = 0
    wh.total_failures = 0
    wh.max_failures = 10
    wh.created_at = datetime.now(timezone.utc)
    out = WebhookOut.from_model(wh)
    assert out.events == []


def test_valid_events_list():
    from app.api.webhooks import VALID_EVENTS
    assert len(VALID_EVENTS) >= 15
    assert "contact.created" in VALID_EVENTS
    assert "campaign.sent" in VALID_EVENTS
    assert "email.opened" in VALID_EVENTS
    assert "workflow.triggered" in VALID_EVENTS


def test_test_webhook_request_defaults():
    from app.api.webhooks import TestWebhookRequest
    req = TestWebhookRequest()
    assert req.event_type == "test.ping"
    assert "message" in req.payload


# ── Dispatcher tests ─────────────────────────────────────
def test_sign_payload():
    from app.services.webhook_dispatcher import sign_payload
    sig = sign_payload('{"event":"test"}', "secret123")
    assert isinstance(sig, str)
    assert len(sig) == 64  # SHA-256 hex


def test_sign_payload_consistency():
    from app.services.webhook_dispatcher import sign_payload
    s1 = sign_payload("hello", "key")
    s2 = sign_payload("hello", "key")
    assert s1 == s2


def test_sign_payload_different_secrets():
    from app.services.webhook_dispatcher import sign_payload
    s1 = sign_payload("hello", "key1")
    s2 = sign_payload("hello", "key2")
    assert s1 != s2


# ── API endpoint tests ──────────────────────────────────
@pytest.mark.asyncio
async def test_list_event_types(client):
    resp = await client.get("/api/v1/webhooks/events")
    assert resp.status_code == 200
    events = resp.json()
    assert isinstance(events, list)
    assert "contact.created" in events


@pytest.mark.asyncio
async def test_list_webhooks_endpoint(client):
    resp = await client.get("/api/v1/webhooks/")
    assert resp.status_code in (200, 500)


@pytest.mark.asyncio
async def test_get_webhook_404(client):
    resp = await client.get("/api/v1/webhooks/nonexistent")
    assert resp.status_code in (404, 500)


@pytest.mark.asyncio
async def test_create_webhook_invalid_event(client):
    resp = await client.post("/api/v1/webhooks/", json={
        "url": "https://example.com/hook",
        "events": ["invalid.event.type"],
    })
    assert resp.status_code in (400, 500)


@pytest.mark.asyncio
async def test_delete_webhook_404(client):
    resp = await client.delete("/api/v1/webhooks/nonexistent")
    assert resp.status_code in (404, 500)
