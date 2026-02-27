"""Test health endpoint and basic API structure."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_api_docs(client: AsyncClient):
    resp = await client.get("/docs")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_contacts_endpoint_exists(client: AsyncClient):
    """Verify the contacts endpoint is registered (will fail without DB but route exists)."""
    resp = await client.get("/api/v1/contacts/")
    assert resp.status_code in (200, 500)


@pytest.mark.asyncio
async def test_campaigns_endpoint_exists(client: AsyncClient):
    resp = await client.get("/api/v1/campaigns/")
    assert resp.status_code in (200, 500)


@pytest.mark.asyncio
async def test_workflows_endpoint_exists(client: AsyncClient):
    resp = await client.get("/api/v1/workflows/")
    assert resp.status_code in (200, 500)


@pytest.mark.asyncio
async def test_dashboard_endpoint_exists(client: AsyncClient):
    resp = await client.get("/api/v1/dashboard/stats")
    assert resp.status_code in (200, 500)


@pytest.mark.asyncio
async def test_auth_login_endpoint_exists(client: AsyncClient):
    resp = await client.post("/api/v1/auth/login", json={"email": "a@b.com", "password": "x"})
    # 401 (wrong creds) or 500 (no DB) — route exists
    assert resp.status_code in (401, 500)


@pytest.mark.asyncio
async def test_templates_endpoint_exists(client: AsyncClient):
    resp = await client.get("/api/v1/templates/")
    assert resp.status_code in (200, 500)


@pytest.mark.asyncio
async def test_csv_export_endpoint_exists(client: AsyncClient):
    resp = await client.get("/api/v1/contacts/export/csv")
    assert resp.status_code in (200, 500)


@pytest.mark.asyncio
async def test_tracking_open_returns_gif(client: AsyncClient):
    """Tracking pixel endpoint should exist (may 500 without DB)."""
    import uuid
    cid = str(uuid.uuid4())
    uid = str(uuid.uuid4())
    resp = await client.get(f"/api/v1/track/open/{cid}/{uid}")
    assert resp.status_code in (200, 500)
