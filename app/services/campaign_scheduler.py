"""Campaign scheduler — timezone-aware send scheduling with throttling and AB auto-winner."""

import json
import math
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, Boolean
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import Base
from app.models import new_uuid, utcnow


# ── Models ───────────────────────────────────────────────

class ScheduleStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CampaignSchedule(Base):
    """Scheduled campaign send with timezone and throttle support."""

    __tablename__ = "campaign_schedules"

    id = Column(String(36), primary_key=True, default=new_uuid)
    campaign_id = Column(String(36), nullable=False, index=True)
    schedule_type = Column(String(20), default="one_time")  # one_time|recurring|drip
    status = Column(String(20), default="pending")
    # Timezone-aware scheduling
    send_at = Column(DateTime, nullable=True)  # UTC
    timezone_name = Column(String(50), default="UTC")
    # Recurring settings
    recurrence_rule = Column(Text, default="{}")  # {"interval": "daily"|"weekly"|"monthly", "days": [1,3,5]}
    next_run_at = Column(DateTime, nullable=True)
    runs_completed = Column(Integer, default=0)
    max_runs = Column(Integer, default=0)  # 0 = unlimited
    # Throttling
    max_per_hour = Column(Integer, default=0)  # 0 = unlimited
    max_per_day = Column(Integer, default=0)  # 0 = unlimited
    sent_this_hour = Column(Integer, default=0)
    sent_today = Column(Integer, default=0)
    last_hour_reset = Column(DateTime, nullable=True)
    last_day_reset = Column(DateTime, nullable=True)
    # AB test auto-winner
    ab_test_id = Column(String(36), nullable=True)
    auto_pick_winner = Column(Boolean, default=False)
    winner_wait_hours = Column(Integer, default=4)
    # Metadata
    error_message = Column(Text, default="")
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class SendLog(Base):
    """Individual send event log for throttle tracking."""

    __tablename__ = "send_logs"

    id = Column(String(36), primary_key=True, default=new_uuid)
    schedule_id = Column(String(36), nullable=False, index=True)
    campaign_id = Column(String(36), nullable=False)
    contact_id = Column(String(36), nullable=False)
    status = Column(String(20), default="sent")  # sent|failed|skipped|throttled
    error = Column(Text, default="")
    sent_at = Column(DateTime, default=utcnow)


# ── Scheduler Service ───────────────────────────────────

class CampaignScheduler:
    """Manages campaign scheduling, throttling, and execution."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_schedule(
        self,
        campaign_id: str,
        send_at: datetime,
        schedule_type: str = "one_time",
        timezone_name: str = "UTC",
        max_per_hour: int = 0,
        max_per_day: int = 0,
        recurrence_rule: Optional[dict] = None,
        max_runs: int = 0,
        ab_test_id: Optional[str] = None,
        auto_pick_winner: bool = False,
        winner_wait_hours: int = 4,
    ) -> CampaignSchedule:
        schedule = CampaignSchedule(
            campaign_id=campaign_id,
            schedule_type=schedule_type,
            send_at=send_at,
            timezone_name=timezone_name,
            max_per_hour=max_per_hour,
            max_per_day=max_per_day,
            recurrence_rule=json.dumps(recurrence_rule or {}),
            max_runs=max_runs,
            next_run_at=send_at,
            ab_test_id=ab_test_id,
            auto_pick_winner=auto_pick_winner,
            winner_wait_hours=winner_wait_hours,
        )
        self.db.add(schedule)
        await self.db.commit()
        await self.db.refresh(schedule)
        return schedule

    async def get_due_schedules(self, now: Optional[datetime] = None) -> list[CampaignSchedule]:
        """Find all schedules that are due to run."""
        now = now or datetime.now(timezone.utc)
        result = await self.db.execute(
            select(CampaignSchedule).where(
                CampaignSchedule.status == "pending",
                CampaignSchedule.next_run_at <= now,
            )
        )
        return list(result.scalars().all())

    async def pause_schedule(self, schedule_id: str) -> Optional[CampaignSchedule]:
        result = await self.db.execute(
            select(CampaignSchedule).where(CampaignSchedule.id == schedule_id)
        )
        schedule = result.scalar_one_or_none()
        if schedule and schedule.status == "pending":
            schedule.status = "paused"
            await self.db.commit()
        return schedule

    async def resume_schedule(self, schedule_id: str) -> Optional[CampaignSchedule]:
        result = await self.db.execute(
            select(CampaignSchedule).where(CampaignSchedule.id == schedule_id)
        )
        schedule = result.scalar_one_or_none()
        if schedule and schedule.status == "paused":
            schedule.status = "pending"
            await self.db.commit()
        return schedule

    async def cancel_schedule(self, schedule_id: str) -> Optional[CampaignSchedule]:
        result = await self.db.execute(
            select(CampaignSchedule).where(CampaignSchedule.id == schedule_id)
        )
        schedule = result.scalar_one_or_none()
        if schedule and schedule.status in ("pending", "paused"):
            schedule.status = "cancelled"
            await self.db.commit()
        return schedule

    def check_throttle(self, schedule: CampaignSchedule, now: Optional[datetime] = None) -> bool:
        """Check if we can send (not throttled). Returns True if OK to send."""
        now = now or datetime.now(timezone.utc)

        # Reset hourly counter
        if schedule.last_hour_reset:
            if (now - schedule.last_hour_reset).total_seconds() >= 3600:
                schedule.sent_this_hour = 0
                schedule.last_hour_reset = now
        else:
            schedule.last_hour_reset = now

        # Reset daily counter
        if schedule.last_day_reset:
            if (now - schedule.last_day_reset).total_seconds() >= 86400:
                schedule.sent_today = 0
                schedule.last_day_reset = now
        else:
            schedule.last_day_reset = now

        # Check limits
        if schedule.max_per_hour > 0 and schedule.sent_this_hour >= schedule.max_per_hour:
            return False
        if schedule.max_per_day > 0 and schedule.sent_today >= schedule.max_per_day:
            return False
        return True

    def increment_counters(self, schedule: CampaignSchedule):
        """Increment send counters after a successful send."""
        schedule.sent_this_hour = (schedule.sent_this_hour or 0) + 1
        schedule.sent_today = (schedule.sent_today or 0) + 1

    async def log_send(
        self,
        schedule_id: str,
        campaign_id: str,
        contact_id: str,
        status: str = "sent",
        error: str = "",
    ) -> SendLog:
        log = SendLog(
            schedule_id=schedule_id,
            campaign_id=campaign_id,
            contact_id=contact_id,
            status=status,
            error=error,
        )
        self.db.add(log)
        await self.db.commit()
        return log

    async def complete_run(self, schedule: CampaignSchedule):
        """Mark a run as completed, schedule next run if recurring."""
        schedule.runs_completed = (schedule.runs_completed or 0) + 1

        if schedule.schedule_type == "recurring":
            if schedule.max_runs > 0 and schedule.runs_completed >= schedule.max_runs:
                schedule.status = "completed"
            else:
                schedule.next_run_at = self._calc_next_run(schedule)
                schedule.status = "pending"
        else:
            schedule.status = "completed"

        await self.db.commit()

    def _calc_next_run(self, schedule: CampaignSchedule) -> Optional[datetime]:
        """Calculate next run time from recurrence rule."""
        try:
            rule = json.loads(schedule.recurrence_rule) if isinstance(schedule.recurrence_rule, str) else schedule.recurrence_rule
        except (json.JSONDecodeError, TypeError):
            rule = {}

        interval = rule.get("interval", "daily")
        base = schedule.next_run_at or datetime.now(timezone.utc)

        if interval == "hourly":
            return base + timedelta(hours=1)
        elif interval == "daily":
            return base + timedelta(days=1)
        elif interval == "weekly":
            return base + timedelta(weeks=1)
        elif interval == "monthly":
            return base + timedelta(days=30)
        return base + timedelta(days=1)

    async def get_send_stats(self, schedule_id: str) -> dict:
        """Get send statistics for a schedule."""
        total = (await self.db.execute(
            select(func.count(SendLog.id)).where(SendLog.schedule_id == schedule_id)
        )).scalar() or 0
        sent = (await self.db.execute(
            select(func.count(SendLog.id)).where(
                SendLog.schedule_id == schedule_id,
                SendLog.status == "sent",
            )
        )).scalar() or 0
        failed = (await self.db.execute(
            select(func.count(SendLog.id)).where(
                SendLog.schedule_id == schedule_id,
                SendLog.status == "failed",
            )
        )).scalar() or 0
        throttled = (await self.db.execute(
            select(func.count(SendLog.id)).where(
                SendLog.schedule_id == schedule_id,
                SendLog.status == "throttled",
            )
        )).scalar() or 0

        return {
            "schedule_id": schedule_id,
            "total": total,
            "sent": sent,
            "failed": failed,
            "throttled": throttled,
            "success_rate": round(sent / total * 100, 2) if total > 0 else 0.0,
        }
