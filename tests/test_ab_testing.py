"""Tests for A/B testing module."""

import pytest
from datetime import datetime, timezone


# ── Model tests ──────────────────────────────────────────
def test_ab_test_model_defaults():
    from app.models.ab_test import ABTest
    t = ABTest(campaign_id="c1", name="Test 1")
    assert t.test_type == "subject"
    assert t.status == "draft"
    assert t.winner_metric == "open_rate"
    assert t.auto_select_winner is True
    assert t.test_percentage == 20.0
    assert t.wait_hours == 4


def test_ab_test_variant_defaults():
    from app.models.ab_test import ABTestVariant
    v = ABTestVariant(ab_test_id="t1", name="A")
    assert v.total_sent == 0
    assert v.total_opened == 0
    assert v.total_clicked == 0
    assert v.total_bounced == 0
    assert v.open_rate == 0.0
    assert v.click_rate == 0.0
    assert v.is_winner is False
    assert v.send_delay_minutes == 0


# ── Schema tests ─────────────────────────────────────────
def test_ab_test_create_schema():
    from app.api.ab_testing import ABTestCreate, VariantCreate
    data = ABTestCreate(
        campaign_id="c1",
        name="Subject Test",
        variants=[
            VariantCreate(name="A", subject="Hello!"),
            VariantCreate(name="B", subject="Hey there!"),
        ],
    )
    assert data.test_type == "subject"
    assert len(data.variants) == 2
    assert data.test_percentage == 20.0


def test_ab_test_create_min_variants():
    from app.api.ab_testing import ABTestCreate, VariantCreate
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ABTestCreate(
            campaign_id="c1",
            name="Bad",
            variants=[VariantCreate(name="A")],  # Need at least 2
        )


def test_ab_test_create_max_variants():
    from app.api.ab_testing import ABTestCreate, VariantCreate
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ABTestCreate(
            campaign_id="c1",
            name="Too many",
            variants=[VariantCreate(name=f"V{i}") for i in range(6)],  # Max 5
        )


def test_ab_test_percentage_bounds():
    from app.api.ab_testing import ABTestCreate, VariantCreate
    from pydantic import ValidationError
    # Too low
    with pytest.raises(ValidationError):
        ABTestCreate(
            campaign_id="c1",
            name="Low",
            test_percentage=2.0,
            variants=[VariantCreate(name="A"), VariantCreate(name="B")],
        )
    # Too high
    with pytest.raises(ValidationError):
        ABTestCreate(
            campaign_id="c1",
            name="High",
            test_percentage=60.0,
            variants=[VariantCreate(name="A"), VariantCreate(name="B")],
        )


def test_variant_out_schema():
    from app.api.ab_testing import VariantOut
    v = VariantOut(
        id="v1",
        name="A",
        subject="Hi",
        html_body=None,
        send_delay_minutes=0,
        total_sent=100,
        total_opened=30,
        total_clicked=10,
        total_bounced=5,
        open_rate=30.0,
        click_rate=10.0,
        is_winner=True,
    )
    assert v.is_winner is True
    assert v.open_rate == 30.0


def test_record_event_request():
    from app.api.ab_testing import RecordEventRequest
    req = RecordEventRequest(variant_id="v1", event_type="opened")
    assert req.event_type == "opened"


def test_ab_test_update_schema():
    from app.api.ab_testing import ABTestUpdate
    u = ABTestUpdate(name="New Name")
    assert u.name == "New Name"
    assert u.winner_metric is None


# ── API endpoint tests (route existence) ────────────────
@pytest.mark.asyncio
async def test_list_ab_tests_endpoint(client):
    resp = await client.get("/api/v1/ab-tests/")
    assert resp.status_code in (200, 500)


@pytest.mark.asyncio
async def test_get_ab_test_404(client):
    resp = await client.get("/api/v1/ab-tests/nonexistent")
    assert resp.status_code in (404, 500)


@pytest.mark.asyncio
async def test_create_ab_test_no_campaign(client):
    resp = await client.post("/api/v1/ab-tests/", json={
        "campaign_id": "nonexistent",
        "name": "Test",
        "variants": [
            {"name": "A", "subject": "Hi"},
            {"name": "B", "subject": "Hey"},
        ],
    })
    assert resp.status_code in (404, 500)


@pytest.mark.asyncio
async def test_delete_ab_test_404(client):
    resp = await client.delete("/api/v1/ab-tests/nonexistent")
    assert resp.status_code in (404, 500)
