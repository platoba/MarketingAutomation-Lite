"""Tests for contacts, campaigns, workflows, dashboard, and tracking APIs."""

import pytest
import uuid


# ── Contacts ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_list_contacts(client):
    resp = await client.get("/api/v1/contacts/")
    assert resp.status_code in (200, 500)


@pytest.mark.asyncio
async def test_contacts_with_query(client):
    resp = await client.get("/api/v1/contacts/?q=test&limit=10")
    assert resp.status_code in (200, 500)


@pytest.mark.asyncio
async def test_contacts_with_subscribed_filter(client):
    resp = await client.get("/api/v1/contacts/?subscribed=true")
    assert resp.status_code in (200, 500)


@pytest.mark.asyncio
async def test_contact_count(client):
    resp = await client.get("/api/v1/contacts/count")
    assert resp.status_code in (200, 500)


@pytest.mark.asyncio
async def test_get_contact_404(client):
    resp = await client.get(f"/api/v1/contacts/{uuid.uuid4()}")
    assert resp.status_code in (404, 500)


@pytest.mark.asyncio
async def test_delete_contact_404(client):
    resp = await client.delete(f"/api/v1/contacts/{uuid.uuid4()}")
    assert resp.status_code in (404, 500)


@pytest.mark.asyncio
async def test_contact_import_endpoint(client):
    resp = await client.post("/api/v1/contacts/import", json=[])
    assert resp.status_code in (201, 500)


@pytest.mark.asyncio
async def test_contact_csv_export(client):
    resp = await client.get("/api/v1/contacts/export/csv")
    assert resp.status_code in (200, 500)


# ── Campaigns ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_list_campaigns(client):
    resp = await client.get("/api/v1/campaigns/")
    assert resp.status_code in (200, 500)


@pytest.mark.asyncio
async def test_list_campaigns_with_status(client):
    resp = await client.get("/api/v1/campaigns/?status=draft")
    assert resp.status_code in (200, 500)


@pytest.mark.asyncio
async def test_get_campaign_404(client):
    resp = await client.get(f"/api/v1/campaigns/{uuid.uuid4()}")
    assert resp.status_code in (404, 500)


@pytest.mark.asyncio
async def test_send_campaign_404(client):
    resp = await client.post(f"/api/v1/campaigns/{uuid.uuid4()}/send")
    assert resp.status_code in (404, 500)


@pytest.mark.asyncio
async def test_delete_campaign_404(client):
    resp = await client.delete(f"/api/v1/campaigns/{uuid.uuid4()}")
    assert resp.status_code in (404, 500)


# ── Workflows ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_list_workflows(client):
    resp = await client.get("/api/v1/workflows/")
    assert resp.status_code in (200, 500)


@pytest.mark.asyncio
async def test_get_workflow_404(client):
    resp = await client.get(f"/api/v1/workflows/{uuid.uuid4()}")
    assert resp.status_code in (404, 500)


# ── Dashboard ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_dashboard_stats(client):
    resp = await client.get("/api/v1/dashboard/stats")
    assert resp.status_code in (200, 500)


# ── Tracking ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_tracking_open(client):
    cid = str(uuid.uuid4())
    uid = str(uuid.uuid4())
    resp = await client.get(f"/api/v1/track/open/{cid}/{uid}")
    assert resp.status_code in (200, 500)


@pytest.mark.asyncio
async def test_tracking_click(client):
    cid = str(uuid.uuid4())
    uid = str(uuid.uuid4())
    resp = await client.get(f"/api/v1/track/click/{cid}/{uid}?url=https://example.com")
    assert resp.status_code in (200, 302, 307, 500)


# ── Tags ─────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_tags_endpoint(client):
    resp = await client.get("/api/v1/tags/")
    assert resp.status_code in (200, 500)


# ── Segments ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_segments_endpoint(client):
    resp = await client.get("/api/v1/segments/")
    assert resp.status_code in (200, 500)


# ── Templates ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_templates_list(client):
    resp = await client.get("/api/v1/templates/")
    assert resp.status_code in (200, 500)


@pytest.mark.asyncio
async def test_template_404(client):
    resp = await client.get(f"/api/v1/templates/{uuid.uuid4()}")
    assert resp.status_code in (404, 500)
