"""Tests for campaign analytics service."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.campaign_analytics import (
    CampaignMetrics,
    CohortData,
    FunnelStep,
    FunnelStage,
    TimeSeriesPoint,
    get_campaign_funnel,
    compare_campaigns,
    get_engagement_timeseries,
    get_cohort_retention,
    get_top_campaigns,
    get_dashboard_stats,
)


class TestFunnelStep:
    """Tests for FunnelStep dataclass."""

    def test_basic_creation(self):
        step = FunnelStep(stage="sent", count=1000, rate=100.0, drop_off_rate=0.0)
        assert step.stage == "sent"
        assert step.count == 1000

    def test_to_dict(self):
        step = FunnelStep(stage="opened", count=500, rate=50.0, drop_off_rate=50.0)
        d = step.to_dict()
        assert d["stage"] == "opened"
        assert d["count"] == 500
        assert d["rate"] == 50.0
        assert d["drop_off_rate"] == 50.0

    def test_rate_rounding(self):
        step = FunnelStep(stage="clicked", count=123, rate=12.3456789)
        d = step.to_dict()
        assert d["rate"] == 12.35


class TestCampaignMetrics:
    """Tests for CampaignMetrics dataclass."""

    def test_basic_creation(self):
        m = CampaignMetrics(campaign_id="c1", campaign_name="Test")
        assert m.campaign_id == "c1"
        assert m.total_sent == 0
        assert m.open_rate == 0.0

    def test_to_dict_complete(self):
        m = CampaignMetrics(
            campaign_id="c1",
            campaign_name="Spring Sale",
            total_sent=1000,
            total_opened=400,
            total_clicked=100,
            total_bounced=20,
            total_unsubscribed=5,
            open_rate=40.82,
            click_rate=10.0,
            ctor=25.0,
            bounce_rate=2.0,
            unsubscribe_rate=0.5,
            engagement_score=78.5,
        )
        d = m.to_dict()
        assert d["campaign_name"] == "Spring Sale"
        assert d["total_sent"] == 1000
        assert d["open_rate"] == 40.82
        assert d["engagement_score"] == 78.5
        assert isinstance(d["funnel"], list)

    def test_to_dict_with_funnel(self):
        m = CampaignMetrics(
            campaign_id="c1",
            campaign_name="Test",
            funnel=[
                FunnelStep(stage="sent", count=100, rate=100.0),
                FunnelStep(stage="opened", count=50, rate=50.0, drop_off_rate=50.0),
            ],
        )
        d = m.to_dict()
        assert len(d["funnel"]) == 2
        assert d["funnel"][0]["stage"] == "sent"
        assert d["funnel"][1]["stage"] == "opened"


class TestCohortData:
    """Tests for CohortData dataclass."""

    def test_basic_creation(self):
        cd = CohortData(
            cohort_period="2026-W08",
            cohort_size=100,
            period_offset=0,
            active_count=80,
            retention_rate=80.0,
        )
        assert cd.cohort_period == "2026-W08"
        assert cd.retention_rate == 80.0

    def test_to_dict(self):
        cd = CohortData(
            cohort_period="2026-W08",
            cohort_size=50,
            period_offset=2,
            active_count=30,
            retention_rate=60.0,
        )
        d = cd.to_dict()
        assert d["cohort_period"] == "2026-W08"
        assert d["period_offset"] == 2
        assert d["retention_rate"] == 60.0


class TestTimeSeriesPoint:
    """Tests for TimeSeriesPoint dataclass."""

    def test_basic(self):
        p = TimeSeriesPoint(period="2026-02-28", value=42.5, label="opened")
        assert p.period == "2026-02-28"
        assert p.value == 42.5

    def test_to_dict(self):
        p = TimeSeriesPoint(period="2026-02-28", value=42.567, label="clicked")
        d = p.to_dict()
        assert d["period"] == "2026-02-28"
        assert d["value"] == 42.57  # rounded to 2 decimals
        assert d["label"] == "clicked"


class TestFunnelStage:
    """Tests for FunnelStage enum."""

    def test_stages_exist(self):
        assert FunnelStage.SENT == "sent"
        assert FunnelStage.DELIVERED == "delivered"
        assert FunnelStage.OPENED == "opened"
        assert FunnelStage.CLICKED == "clicked"
        assert FunnelStage.CONVERTED == "converted"
        assert FunnelStage.UNSUBSCRIBED == "unsubscribed"
        assert FunnelStage.BOUNCED == "bounced"

    def test_stage_values(self):
        assert len(FunnelStage) == 7


class TestMetricsCalculations:
    """Test metric calculation logic (unit-level, no DB)."""

    def test_engagement_score_formula(self):
        """Verify engagement score weighted formula."""
        open_rate = 40.0
        ctor = 25.0
        bounce_rate = 2.0
        unsub_rate = 0.5

        score = min(100, (
            open_rate * 0.3
            + ctor * 0.4
            + (100 - bounce_rate) * 0.15
            + (100 - unsub_rate) * 0.15
        ))
        assert 50 < score < 100

    def test_engagement_score_perfect(self):
        """100% open rate, 100% CTOR, 0% bounce, 0% unsub."""
        score = min(100, (
            100 * 0.3 + 100 * 0.4 + 100 * 0.15 + 100 * 0.15
        ))
        assert score == 100

    def test_engagement_score_terrible(self):
        """0% open rate, 0% CTOR, 100% bounce."""
        score = min(100, (
            0 * 0.3 + 0 * 0.4 + 0 * 0.15 + 100 * 0.15
        ))
        assert score == 15  # only unsub baseline

    def test_open_rate_calculation(self):
        sent = 1000
        bounced = 50
        opened = 300
        delivered = sent - bounced
        rate = (opened / max(delivered, 1)) * 100
        assert abs(rate - 31.58) < 0.1

    def test_ctor_calculation(self):
        """Click-to-open rate."""
        opened = 400
        clicked = 100
        ctor = (clicked / max(opened, 1)) * 100
        assert ctor == 25.0

    def test_ctor_zero_opens(self):
        """CTOR should be 0 when no opens."""
        opened = 0
        clicked = 0
        ctor = (clicked / max(opened, 1)) * 100 if opened > 0 else 0
        assert ctor == 0

    def test_drop_off_rate(self):
        prev = 1000
        current = 400
        drop = ((prev - current) / max(prev, 1)) * 100
        assert drop == 60.0

    def test_funnel_steps_decreasing(self):
        """Verify funnel counts should generally decrease."""
        sent, delivered, opened, clicked = 1000, 950, 400, 100
        assert sent >= delivered >= opened >= clicked

    def test_bounce_rate(self):
        sent = 1000
        bounced = 30
        rate = (bounced / max(sent, 1)) * 100
        assert rate == 3.0


class TestCampaignMetricsEdgeCases:
    """Edge case tests for metrics."""

    def test_zero_sent(self):
        m = CampaignMetrics(campaign_id="x", campaign_name="Empty", total_sent=0)
        assert m.open_rate == 0.0

    def test_all_bounced(self):
        m = CampaignMetrics(
            campaign_id="x", campaign_name="Bad",
            total_sent=100, total_bounced=100,
            bounce_rate=100.0,
        )
        assert m.bounce_rate == 100.0

    def test_high_engagement(self):
        m = CampaignMetrics(
            campaign_id="x", campaign_name="Great",
            total_sent=1000, total_opened=800, total_clicked=600,
            open_rate=80.0, click_rate=60.0, ctor=75.0,
            engagement_score=95.0,
        )
        assert m.engagement_score >= 90

    def test_funnel_list_initially_empty(self):
        m = CampaignMetrics(campaign_id="x", campaign_name="T")
        assert m.funnel == []
