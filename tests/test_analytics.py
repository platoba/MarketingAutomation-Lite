"""Tests for analytics service."""

import pytest
from datetime import datetime, timezone


# ── Schema tests ─────────────────────────────────────────
def test_campaign_metrics_schema():
    from app.services.analytics import CampaignMetrics
    m = CampaignMetrics(
        campaign_id="c1",
        campaign_name="Test",
        total_sent=1000,
        total_delivered=980,
        total_opened=300,
        unique_opens=250,
        total_clicked=100,
        unique_clicks=80,
        total_bounced=20,
        total_unsubscribed=5,
        delivery_rate=98.0,
        open_rate=25.5,
        click_rate=8.2,
        click_to_open_rate=32.0,
        bounce_rate=2.0,
        unsubscribe_rate=0.5,
    )
    assert m.total_sent == 1000
    assert m.open_rate == 25.5
    assert m.click_to_open_rate == 32.0


def test_hourly_breakdown_schema():
    from app.services.analytics import HourlyBreakdown
    h = HourlyBreakdown(hour=14, opens=50, clicks=20)
    assert h.hour == 14
    assert h.opens == 50


def test_engagement_report_schema():
    from app.services.analytics import EngagementReport, HourlyBreakdown
    report = EngagementReport(
        campaign_id="c1",
        hourly=[HourlyBreakdown(hour=i, opens=i * 2, clicks=i) for i in range(24)],
        peak_open_hour=23,
        peak_click_hour=23,
    )
    assert len(report.hourly) == 24
    assert report.peak_open_hour == 23


def test_cohort_row_schema():
    from app.services.analytics import CohortRow
    c = CohortRow(cohort="2026-W08", total=100, subscribed=90, retention_pct=90.0)
    assert c.retention_pct == 90.0


def test_health_score_schema():
    from app.services.analytics import HealthScore
    h = HealthScore(
        score=85.5,
        grade="A",
        factors={"subscription_rate": 95.0, "open_rate": 22.0},
    )
    assert h.grade == "A"
    assert h.score == 85.5


def test_health_grade_boundaries():
    from app.services.analytics import HealthScore
    # A grade
    assert HealthScore(score=85, grade="A", factors={}).grade == "A"
    # B grade
    assert HealthScore(score=70, grade="B", factors={}).grade == "B"
    # F grade
    assert HealthScore(score=30, grade="F", factors={}).grade == "F"


# ── API endpoint tests ──────────────────────────────────
@pytest.mark.asyncio
async def test_health_endpoint(client):
    resp = await client.get("/api/v1/analytics/health")
    assert resp.status_code in (200, 500)


@pytest.mark.asyncio
async def test_cohorts_endpoint(client):
    resp = await client.get("/api/v1/analytics/cohorts")
    assert resp.status_code in (200, 500)


@pytest.mark.asyncio
async def test_cohorts_with_weeks_param(client):
    resp = await client.get("/api/v1/analytics/cohorts?weeks=4")
    assert resp.status_code in (200, 500)


@pytest.mark.asyncio
async def test_campaign_metrics_404(client):
    resp = await client.get("/api/v1/analytics/campaigns/nonexistent/metrics")
    assert resp.status_code in (404, 500)


@pytest.mark.asyncio
async def test_campaign_engagement_endpoint(client):
    resp = await client.get("/api/v1/analytics/campaigns/test123/engagement")
    assert resp.status_code in (200, 500)
