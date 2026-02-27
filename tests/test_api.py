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
    # 200 if DB is up, 500 if not — either way the route exists
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
