"""Analytics service — advanced campaign metrics, cohort analysis, and performance reports."""

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Campaign, Contact, EmailEvent


# ── Response Schemas ─────────────────────────────────────
class CampaignMetrics(BaseModel):
    campaign_id: str
    campaign_name: str
    total_sent: int
    total_delivered: int
    total_opened: int
    unique_opens: int
    total_clicked: int
    unique_clicks: int
    total_bounced: int
    total_unsubscribed: int
    delivery_rate: float
    open_rate: float
    click_rate: float
    click_to_open_rate: float
    bounce_rate: float
    unsubscribe_rate: float


class HourlyBreakdown(BaseModel):
    hour: int
    opens: int
    clicks: int


class EngagementReport(BaseModel):
    campaign_id: str
    hourly: list[HourlyBreakdown]
    peak_open_hour: int
    peak_click_hour: int
    avg_time_to_open_minutes: Optional[float] = None


class CohortRow(BaseModel):
    cohort: str  # e.g., "2026-W08"
    total: int
    subscribed: int
    retention_pct: float


class HealthScore(BaseModel):
    score: float  # 0-100
    grade: str  # A/B/C/D/F
    factors: dict  # Breakdown of scoring factors


# ── Service ──────────────────────────────────────────────
async def get_campaign_metrics(db: AsyncSession, campaign_id: str) -> CampaignMetrics:
    """Calculate detailed metrics for a campaign."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise ValueError("Campaign not found")

    # Count events by type
    events_stmt = (
        select(EmailEvent.event_type, func.count(EmailEvent.id))
        .where(EmailEvent.campaign_id == campaign_id)
        .group_by(EmailEvent.event_type)
    )
    events_result = await db.execute(events_stmt)
    event_counts = dict(events_result.all())

    # Unique opens/clicks
    unique_opens_stmt = (
        select(func.count(func.distinct(EmailEvent.contact_id)))
        .where(
            EmailEvent.campaign_id == campaign_id,
            EmailEvent.event_type == "opened",
        )
    )
    unique_opens = (await db.execute(unique_opens_stmt)).scalar() or 0

    unique_clicks_stmt = (
        select(func.count(func.distinct(EmailEvent.contact_id)))
        .where(
            EmailEvent.campaign_id == campaign_id,
            EmailEvent.event_type == "clicked",
        )
    )
    unique_clicks = (await db.execute(unique_clicks_stmt)).scalar() or 0

    total_sent = event_counts.get("sent", 0) or campaign.total_sent or 0
    total_delivered = total_sent - event_counts.get("bounced", 0)
    total_opened = event_counts.get("opened", 0) or campaign.total_opened or 0
    total_clicked = event_counts.get("clicked", 0) or campaign.total_clicked or 0
    total_bounced = event_counts.get("bounced", 0) or campaign.total_bounced or 0
    total_unsub = event_counts.get("unsubscribed", 0) or campaign.total_unsubscribed or 0

    delivery_rate = (total_delivered / total_sent * 100) if total_sent > 0 else 0.0
    open_rate = (unique_opens / total_delivered * 100) if total_delivered > 0 else 0.0
    click_rate = (unique_clicks / total_delivered * 100) if total_delivered > 0 else 0.0
    cto_rate = (unique_clicks / unique_opens * 100) if unique_opens > 0 else 0.0
    bounce_rate = (total_bounced / total_sent * 100) if total_sent > 0 else 0.0
    unsub_rate = (total_unsub / total_delivered * 100) if total_delivered > 0 else 0.0

    return CampaignMetrics(
        campaign_id=campaign_id,
        campaign_name=campaign.name,
        total_sent=total_sent,
        total_delivered=total_delivered,
        total_opened=total_opened,
        unique_opens=unique_opens,
        total_clicked=total_clicked,
        unique_clicks=unique_clicks,
        total_bounced=total_bounced,
        total_unsubscribed=total_unsub,
        delivery_rate=round(delivery_rate, 2),
        open_rate=round(open_rate, 2),
        click_rate=round(click_rate, 2),
        click_to_open_rate=round(cto_rate, 2),
        bounce_rate=round(bounce_rate, 2),
        unsubscribe_rate=round(unsub_rate, 2),
    )


async def get_engagement_report(db: AsyncSession, campaign_id: str) -> EngagementReport:
    """Get hourly engagement breakdown for a campaign."""
    # Get open events with timestamps
    opens_stmt = (
        select(EmailEvent.created_at)
        .where(
            EmailEvent.campaign_id == campaign_id,
            EmailEvent.event_type == "opened",
        )
    )
    opens_result = await db.execute(opens_stmt)
    open_times = [row[0] for row in opens_result.all()]

    clicks_stmt = (
        select(EmailEvent.created_at)
        .where(
            EmailEvent.campaign_id == campaign_id,
            EmailEvent.event_type == "clicked",
        )
    )
    clicks_result = await db.execute(clicks_stmt)
    click_times = [row[0] for row in clicks_result.all()]

    hourly = defaultdict(lambda: {"opens": 0, "clicks": 0})
    for t in open_times:
        if t:
            hourly[t.hour]["opens"] += 1
    for t in click_times:
        if t:
            hourly[t.hour]["clicks"] += 1

    breakdown = []
    for h in range(24):
        breakdown.append(HourlyBreakdown(
            hour=h,
            opens=hourly[h]["opens"],
            clicks=hourly[h]["clicks"],
        ))

    peak_open = max(breakdown, key=lambda x: x.opens).hour if open_times else 0
    peak_click = max(breakdown, key=lambda x: x.clicks).hour if click_times else 0

    return EngagementReport(
        campaign_id=campaign_id,
        hourly=breakdown,
        peak_open_hour=peak_open,
        peak_click_hour=peak_click,
    )


async def get_contact_cohorts(db: AsyncSession, weeks: int = 12) -> list[CohortRow]:
    """Weekly contact cohort analysis — retention over time."""
    now = datetime.now(timezone.utc)
    cohorts = []

    for w in range(weeks):
        week_start = now - timedelta(weeks=w + 1)
        week_end = now - timedelta(weeks=w)

        total_stmt = select(func.count(Contact.id)).where(
            and_(Contact.created_at >= week_start, Contact.created_at < week_end)
        )
        total = (await db.execute(total_stmt)).scalar() or 0

        subscribed_stmt = select(func.count(Contact.id)).where(
            and_(
                Contact.created_at >= week_start,
                Contact.created_at < week_end,
                Contact.subscribed.is_(True),
            )
        )
        subscribed = (await db.execute(subscribed_stmt)).scalar() or 0

        iso_week = week_start.isocalendar()
        cohort_label = f"{iso_week.year}-W{iso_week.week:02d}"
        retention = (subscribed / total * 100) if total > 0 else 0.0

        cohorts.append(CohortRow(
            cohort=cohort_label,
            total=total,
            subscribed=subscribed,
            retention_pct=round(retention, 1),
        ))

    return list(reversed(cohorts))


async def calculate_health_score(db: AsyncSession) -> HealthScore:
    """Calculate overall email marketing health score (0-100)."""
    # Get aggregate stats
    total_contacts = (await db.execute(select(func.count(Contact.id)))).scalar() or 0
    subscribed = (
        await db.execute(
            select(func.count(Contact.id)).where(Contact.subscribed.is_(True))
        )
    ).scalar() or 0
    total_sent = (
        await db.execute(select(func.coalesce(func.sum(Campaign.total_sent), 0)))
    ).scalar() or 0
    total_opened = (
        await db.execute(select(func.coalesce(func.sum(Campaign.total_opened), 0)))
    ).scalar() or 0
    total_bounced = (
        await db.execute(select(func.coalesce(func.sum(Campaign.total_bounced), 0)))
    ).scalar() or 0

    factors = {}

    # List health (max 25 points)
    if total_contacts > 0:
        sub_rate = subscribed / total_contacts * 100
        factors["subscription_rate"] = round(sub_rate, 1)
        list_score = min(25, sub_rate / 4)
    else:
        factors["subscription_rate"] = 0
        list_score = 0

    # Open rate (max 25 points)
    if total_sent > 0:
        open_rate = total_opened / total_sent * 100
        factors["open_rate"] = round(open_rate, 1)
        open_score = min(25, open_rate)
    else:
        factors["open_rate"] = 0
        open_score = 12.5  # Neutral if no sends

    # Bounce rate (max 25 points — lower is better)
    if total_sent > 0:
        bounce_rate = total_bounced / total_sent * 100
        factors["bounce_rate"] = round(bounce_rate, 1)
        bounce_score = max(0, 25 - bounce_rate * 5)
    else:
        factors["bounce_rate"] = 0
        bounce_score = 25

    # Activity (max 25 points)
    recent_campaigns = (
        await db.execute(
            select(func.count(Campaign.id)).where(
                Campaign.created_at >= datetime.now(timezone.utc) - timedelta(days=30)
            )
        )
    ).scalar() or 0
    factors["recent_campaigns_30d"] = recent_campaigns
    activity_score = min(25, recent_campaigns * 5)

    total_score = list_score + open_score + bounce_score + activity_score
    total_score = round(min(100, max(0, total_score)), 1)

    grade = (
        "A" if total_score >= 85
        else "B" if total_score >= 70
        else "C" if total_score >= 55
        else "D" if total_score >= 40
        else "F"
    )

    return HealthScore(score=total_score, grade=grade, factors=factors)
