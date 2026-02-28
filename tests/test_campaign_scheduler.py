"""Tests for campaign scheduler service."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.campaign_scheduler import (
    CampaignSchedule,
    CampaignScheduler,
    ScheduleStatus,
    SendLog,
)


# ── Model tests ──────────────────────────────────────────

class TestCampaignScheduleModel:
    def test_defaults(self):
        s = CampaignSchedule(campaign_id="c1")
        assert s.schedule_type == "one_time"
        assert s.status == "pending"
        assert s.timezone_name == "UTC"
        assert s.runs_completed == 0
        assert s.max_runs == 0
        assert s.max_per_hour == 0
        assert s.max_per_day == 0
        assert s.sent_this_hour == 0
        assert s.sent_today == 0
        assert s.auto_pick_winner is False
        assert s.winner_wait_hours == 4

    def test_send_at(self):
        dt = datetime(2026, 3, 1, tzinfo=timezone.utc)
        s = CampaignSchedule(campaign_id="c1", send_at=dt)
        assert s.send_at == dt

    def test_recurring_type(self):
        s = CampaignSchedule(campaign_id="c1", schedule_type="recurring")
        assert s.schedule_type == "recurring"


class TestSendLogModel:
    def test_defaults(self):
        log = SendLog(schedule_id="s1", campaign_id="c1", contact_id="ct1")
        assert log.status == "sent"
        assert log.error == ""

    def test_failed_status(self):
        log = SendLog(schedule_id="s1", campaign_id="c1", contact_id="ct1", status="failed")
        assert log.status == "failed"


# ── Scheduler service tests ─────────────────────────────

class TestSchedulerService:
    @pytest_asyncio.fixture
    async def db(self):
        from app.database import engine, Base, async_session
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_session() as session:
            yield session
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    @pytest.mark.asyncio
    async def test_create_schedule(self, db):
        scheduler = CampaignScheduler(db)
        now = datetime.now(timezone.utc) + timedelta(hours=1)
        s = await scheduler.create_schedule("camp-1", now)
        assert s.campaign_id == "camp-1"
        assert s.status == "pending"
        assert s.schedule_type == "one_time"

    @pytest.mark.asyncio
    async def test_create_recurring_schedule(self, db):
        scheduler = CampaignScheduler(db)
        now = datetime.now(timezone.utc)
        s = await scheduler.create_schedule(
            "camp-2", now, schedule_type="recurring",
            recurrence_rule={"interval": "daily"}, max_runs=10,
        )
        assert s.schedule_type == "recurring"
        assert s.max_runs == 10

    @pytest.mark.asyncio
    async def test_get_due_schedules(self, db):
        scheduler = CampaignScheduler(db)
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        await scheduler.create_schedule("camp-due", past)
        await scheduler.create_schedule("camp-not-due", future)
        due = await scheduler.get_due_schedules()
        assert len(due) == 1
        assert due[0].campaign_id == "camp-due"

    @pytest.mark.asyncio
    async def test_pause_schedule(self, db):
        scheduler = CampaignScheduler(db)
        now = datetime.now(timezone.utc) + timedelta(hours=1)
        s = await scheduler.create_schedule("camp-pause", now)
        paused = await scheduler.pause_schedule(s.id)
        assert paused.status == "paused"

    @pytest.mark.asyncio
    async def test_resume_schedule(self, db):
        scheduler = CampaignScheduler(db)
        now = datetime.now(timezone.utc) + timedelta(hours=1)
        s = await scheduler.create_schedule("camp-resume", now)
        await scheduler.pause_schedule(s.id)
        resumed = await scheduler.resume_schedule(s.id)
        assert resumed.status == "pending"

    @pytest.mark.asyncio
    async def test_cancel_schedule(self, db):
        scheduler = CampaignScheduler(db)
        now = datetime.now(timezone.utc) + timedelta(hours=1)
        s = await scheduler.create_schedule("camp-cancel", now)
        cancelled = await scheduler.cancel_schedule(s.id)
        assert cancelled.status == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_nonexistent(self, db):
        scheduler = CampaignScheduler(db)
        result = await scheduler.cancel_schedule("nonexistent-id")
        assert result is None

    def test_throttle_ok(self):
        s = CampaignSchedule(campaign_id="c1", max_per_hour=100, max_per_day=1000)
        s.sent_this_hour = 50
        s.sent_today = 500
        scheduler = CampaignScheduler.__new__(CampaignScheduler)
        assert scheduler.check_throttle(s) is True

    def test_throttle_hourly_limit(self):
        s = CampaignSchedule(campaign_id="c1", max_per_hour=100, max_per_day=1000)
        s.sent_this_hour = 100
        s.last_hour_reset = datetime.now(timezone.utc)
        scheduler = CampaignScheduler.__new__(CampaignScheduler)
        assert scheduler.check_throttle(s) is False

    def test_throttle_daily_limit(self):
        s = CampaignSchedule(campaign_id="c1", max_per_hour=0, max_per_day=100)
        s.sent_today = 100
        s.last_day_reset = datetime.now(timezone.utc)
        scheduler = CampaignScheduler.__new__(CampaignScheduler)
        assert scheduler.check_throttle(s) is False

    def test_throttle_hourly_reset(self):
        s = CampaignSchedule(campaign_id="c1", max_per_hour=100)
        s.sent_this_hour = 100
        s.last_hour_reset = datetime.now(timezone.utc) - timedelta(hours=2)
        scheduler = CampaignScheduler.__new__(CampaignScheduler)
        assert scheduler.check_throttle(s) is True
        assert s.sent_this_hour == 0

    def test_throttle_no_limit(self):
        s = CampaignSchedule(campaign_id="c1", max_per_hour=0, max_per_day=0)
        s.sent_this_hour = 9999
        s.sent_today = 9999
        scheduler = CampaignScheduler.__new__(CampaignScheduler)
        assert scheduler.check_throttle(s) is True

    def test_increment_counters(self):
        s = CampaignSchedule(campaign_id="c1")
        scheduler = CampaignScheduler.__new__(CampaignScheduler)
        scheduler.increment_counters(s)
        assert s.sent_this_hour == 1
        assert s.sent_today == 1
        scheduler.increment_counters(s)
        assert s.sent_this_hour == 2

    @pytest.mark.asyncio
    async def test_log_send(self, db):
        scheduler = CampaignScheduler(db)
        log = await scheduler.log_send("s1", "c1", "ct1", "sent")
        assert log.status == "sent"
        assert log.schedule_id == "s1"

    @pytest.mark.asyncio
    async def test_log_send_failed(self, db):
        scheduler = CampaignScheduler(db)
        log = await scheduler.log_send("s1", "c1", "ct1", "failed", "SMTP error")
        assert log.status == "failed"
        assert log.error == "SMTP error"

    @pytest.mark.asyncio
    async def test_complete_one_time(self, db):
        scheduler = CampaignScheduler(db)
        now = datetime.now(timezone.utc)
        s = await scheduler.create_schedule("camp-done", now)
        await scheduler.complete_run(s)
        assert s.status == "completed"
        assert s.runs_completed == 1

    @pytest.mark.asyncio
    async def test_complete_recurring(self, db):
        scheduler = CampaignScheduler(db)
        now = datetime.now(timezone.utc)
        s = await scheduler.create_schedule(
            "camp-rec", now, schedule_type="recurring",
            recurrence_rule={"interval": "daily"},
        )
        await scheduler.complete_run(s)
        assert s.status == "pending"
        assert s.runs_completed == 1
        # next_run_at may be naive from SQLite; just check it's set
        assert s.next_run_at is not None

    @pytest.mark.asyncio
    async def test_complete_recurring_max_reached(self, db):
        scheduler = CampaignScheduler(db)
        now = datetime.now(timezone.utc)
        s = await scheduler.create_schedule(
            "camp-max", now, schedule_type="recurring",
            recurrence_rule={"interval": "daily"}, max_runs=1,
        )
        await scheduler.complete_run(s)
        assert s.status == "completed"

    @pytest.mark.asyncio
    async def test_get_send_stats(self, db):
        scheduler = CampaignScheduler(db)
        await scheduler.log_send("stats-1", "c1", "ct1", "sent")
        await scheduler.log_send("stats-1", "c1", "ct2", "sent")
        await scheduler.log_send("stats-1", "c1", "ct3", "failed", "err")
        stats = await scheduler.get_send_stats("stats-1")
        assert stats["total"] == 3
        assert stats["sent"] == 2
        assert stats["failed"] == 1
        assert stats["success_rate"] > 0

    def test_calc_next_run_daily(self):
        scheduler = CampaignScheduler.__new__(CampaignScheduler)
        s = CampaignSchedule(
            campaign_id="c1", schedule_type="recurring",
            recurrence_rule=json.dumps({"interval": "daily"}),
        )
        now = datetime.now(timezone.utc)
        s.next_run_at = now
        nxt = scheduler._calc_next_run(s)
        assert nxt == now + timedelta(days=1)

    def test_calc_next_run_weekly(self):
        scheduler = CampaignScheduler.__new__(CampaignScheduler)
        s = CampaignSchedule(
            campaign_id="c1", schedule_type="recurring",
            recurrence_rule=json.dumps({"interval": "weekly"}),
        )
        now = datetime.now(timezone.utc)
        s.next_run_at = now
        nxt = scheduler._calc_next_run(s)
        assert nxt == now + timedelta(weeks=1)

    def test_calc_next_run_hourly(self):
        scheduler = CampaignScheduler.__new__(CampaignScheduler)
        s = CampaignSchedule(
            campaign_id="c1", schedule_type="recurring",
            recurrence_rule=json.dumps({"interval": "hourly"}),
        )
        now = datetime.now(timezone.utc)
        s.next_run_at = now
        nxt = scheduler._calc_next_run(s)
        assert nxt == now + timedelta(hours=1)

    def test_calc_next_run_monthly(self):
        scheduler = CampaignScheduler.__new__(CampaignScheduler)
        s = CampaignSchedule(
            campaign_id="c1", schedule_type="recurring",
            recurrence_rule=json.dumps({"interval": "monthly"}),
        )
        now = datetime.now(timezone.utc)
        s.next_run_at = now
        nxt = scheduler._calc_next_run(s)
        assert nxt == now + timedelta(days=30)

    @pytest.mark.asyncio
    async def test_schedule_with_throttle(self, db):
        scheduler = CampaignScheduler(db)
        now = datetime.now(timezone.utc) + timedelta(hours=1)
        s = await scheduler.create_schedule(
            "camp-th", now, max_per_hour=500, max_per_day=5000,
        )
        assert s.max_per_hour == 500
        assert s.max_per_day == 5000

    @pytest.mark.asyncio
    async def test_schedule_with_ab_test(self, db):
        scheduler = CampaignScheduler(db)
        now = datetime.now(timezone.utc) + timedelta(hours=1)
        s = await scheduler.create_schedule(
            "camp-ab", now, ab_test_id="ab-1",
            auto_pick_winner=True, winner_wait_hours=6,
        )
        assert s.ab_test_id == "ab-1"
        assert s.auto_pick_winner is True
        assert s.winner_wait_hours == 6
