"""Campaign analytics service — funnel analysis, cohort tracking, and time-series metrics."""

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import and_, case, cast, func, select, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Campaign, Contact, EmailEvent


# ── Funnel stages ──────────────────────────────────────
class FunnelStage(str, Enum):
    SENT = "sent"
    DELIVERED = "delivered"
    OPENED = "opened"
    CLICKED = "clicked"
    CONVERTED = "converted"
    UNSUBSCRIBED = "unsubscribed"
    BOUNCED = "bounced"


FUNNEL_ORDER = [
    FunnelStage.SENT,
    FunnelStage.DELIVERED,
    FunnelStage.OPENED,
    FunnelStage.CLICKED,
    FunnelStage.CONVERTED,
]


@dataclass
class FunnelStep:
    """Single step in the conversion funnel."""
    stage: str
    count: int
    rate: float = 0.0           # % of total sent
    drop_off_rate: float = 0.0  # % drop from previous step

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "count": self.count,
            "rate": round(self.rate, 2),
            "drop_off_rate": round(self.drop_off_rate, 2),
        }


@dataclass
class CampaignMetrics:
    """Comprehensive campaign performance metrics."""
    campaign_id: str
    campaign_name: str
    total_sent: int = 0
    total_opened: int = 0
    total_clicked: int = 0
    total_bounced: int = 0
    total_unsubscribed: int = 0
    open_rate: float = 0.0
    click_rate: float = 0.0     # CTR (clicks / sent)
    ctor: float = 0.0           # Click-to-open rate (clicks / opens)
    bounce_rate: float = 0.0
    unsubscribe_rate: float = 0.0
    engagement_score: float = 0.0
    funnel: list[FunnelStep] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "campaign_id": self.campaign_id,
            "campaign_name": self.campaign_name,
            "total_sent": self.total_sent,
            "total_opened": self.total_opened,
            "total_clicked": self.total_clicked,
            "total_bounced": self.total_bounced,
            "total_unsubscribed": self.total_unsubscribed,
            "open_rate": round(self.open_rate, 2),
            "click_rate": round(self.click_rate, 2),
            "ctor": round(self.ctor, 2),
            "bounce_rate": round(self.bounce_rate, 2),
            "unsubscribe_rate": round(self.unsubscribe_rate, 2),
            "engagement_score": round(self.engagement_score, 1),
            "funnel": [s.to_dict() for s in self.funnel],
        }


@dataclass
class CohortData:
    """Cohort analysis data point."""
    cohort_period: str          # e.g., "2026-W08"
    cohort_size: int
    period_offset: int          # 0 = same period, 1 = next, etc.
    active_count: int
    retention_rate: float

    def to_dict(self) -> dict:
        return {
            "cohort_period": self.cohort_period,
            "cohort_size": self.cohort_size,
            "period_offset": self.period_offset,
            "active_count": self.active_count,
            "retention_rate": round(self.retention_rate, 2),
        }


@dataclass
class TimeSeriesPoint:
    """Single point in a time series."""
    period: str
    value: float
    label: str = ""

    def to_dict(self) -> dict:
        return {"period": self.period, "value": round(self.value, 2), "label": self.label}


# ── Campaign funnel analysis ──────────────────────────
async def get_campaign_funnel(db: AsyncSession, campaign_id: str) -> CampaignMetrics:
    """
    Build a complete conversion funnel for a campaign.
    Aggregates event data into sent→delivered→opened→clicked stages.
    """
    # Get campaign
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    # Count events by type
    stmt = (
        select(EmailEvent.event_type, func.count(func.distinct(EmailEvent.contact_id)))
        .where(EmailEvent.campaign_id == campaign_id)
        .group_by(EmailEvent.event_type)
    )
    result = await db.execute(stmt)
    event_counts = {row[0]: row[1] for row in result.all()}

    total_sent = campaign.total_sent or event_counts.get("sent", 0) or 1
    total_opened = campaign.total_opened or event_counts.get("opened", 0)
    total_clicked = campaign.total_clicked or event_counts.get("clicked", 0)
    total_bounced = campaign.total_bounced or event_counts.get("bounced", 0)
    total_unsub = campaign.total_unsubscribed or event_counts.get("unsubscribed", 0)
    total_delivered = total_sent - total_bounced

    metrics = CampaignMetrics(
        campaign_id=campaign.id,
        campaign_name=campaign.name,
        total_sent=total_sent,
        total_opened=total_opened,
        total_clicked=total_clicked,
        total_bounced=total_bounced,
        total_unsubscribed=total_unsub,
        open_rate=(total_opened / max(total_delivered, 1)) * 100,
        click_rate=(total_clicked / max(total_sent, 1)) * 100,
        ctor=(total_clicked / max(total_opened, 1)) * 100 if total_opened > 0 else 0,
        bounce_rate=(total_bounced / max(total_sent, 1)) * 100,
        unsubscribe_rate=(total_unsub / max(total_sent, 1)) * 100,
    )

    # Engagement score (weighted composite)
    metrics.engagement_score = min(100, (
        metrics.open_rate * 0.3
        + metrics.ctor * 0.4
        + (100 - metrics.bounce_rate) * 0.15
        + (100 - metrics.unsubscribe_rate) * 0.15
    ))

    # Build funnel steps
    funnel_data = [
        ("sent", total_sent),
        ("delivered", total_delivered),
        ("opened", total_opened),
        ("clicked", total_clicked),
    ]
    prev_count = total_sent
    for stage_name, count in funnel_data:
        step = FunnelStep(
            stage=stage_name,
            count=count,
            rate=(count / max(total_sent, 1)) * 100,
            drop_off_rate=((prev_count - count) / max(prev_count, 1)) * 100 if prev_count > 0 else 0,
        )
        metrics.funnel.append(step)
        prev_count = count

    return metrics


# ── Campaign comparison ───────────────────────────────
async def compare_campaigns(
    db: AsyncSession,
    campaign_ids: list[str],
) -> list[dict]:
    """Compare metrics across multiple campaigns side by side."""
    results = []
    for cid in campaign_ids:
        try:
            metrics = await get_campaign_funnel(db, cid)
            results.append(metrics.to_dict())
        except ValueError:
            results.append({"campaign_id": cid, "error": "not found"})
    return results


# ── Time-series engagement ────────────────────────────
async def get_engagement_timeseries(
    db: AsyncSession,
    campaign_id: Optional[str] = None,
    days: int = 30,
    granularity: str = "day",   # "hour" | "day" | "week"
) -> dict:
    """
    Generate time-series data for email engagement events.

    Returns:
        {
            "period": "day",
            "series": {
                "opened": [TimeSeriesPoint, ...],
                "clicked": [TimeSeriesPoint, ...],
                "bounced": [TimeSeriesPoint, ...],
            }
        }
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)

    stmt = select(EmailEvent).where(EmailEvent.created_at >= start)
    if campaign_id:
        stmt = stmt.where(EmailEvent.campaign_id == campaign_id)
    stmt = stmt.order_by(EmailEvent.created_at)

    result = await db.execute(stmt)
    events = result.scalars().all()

    # Group events by period
    series: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for event in events:
        dt = event.created_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        if granularity == "hour":
            key = dt.strftime("%Y-%m-%d %H:00")
        elif granularity == "week":
            key = f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]:02d}"
        else:
            key = dt.strftime("%Y-%m-%d")

        series[event.event_type][key] += 1

    # Convert to TimeSeriesPoint lists
    output = {}
    for event_type, period_data in series.items():
        output[event_type] = [
            TimeSeriesPoint(period=p, value=v, label=event_type).to_dict()
            for p, v in sorted(period_data.items())
        ]

    return {"granularity": granularity, "days": days, "series": output}


# ── Cohort retention analysis ─────────────────────────
async def get_cohort_retention(
    db: AsyncSession,
    periods: int = 12,
    granularity: str = "week",   # "day" | "week" | "month"
) -> list[dict]:
    """
    Build a cohort retention table.

    Groups contacts by signup period, then tracks their email engagement
    in subsequent periods.

    Returns list of CohortData rows.
    """
    now = datetime.now(timezone.utc)

    if granularity == "day":
        delta = timedelta(days=1)
    elif granularity == "month":
        delta = timedelta(days=30)
    else:
        delta = timedelta(weeks=1)

    start = now - delta * periods

    # Get contacts grouped by signup period
    contacts_result = await db.execute(
        select(Contact.id, Contact.created_at)
        .where(Contact.created_at >= start)
        .order_by(Contact.created_at)
    )
    contacts = contacts_result.all()

    # Get all engagement events
    events_result = await db.execute(
        select(EmailEvent.contact_id, EmailEvent.created_at)
        .where(
            EmailEvent.created_at >= start,
            EmailEvent.event_type.in_(["opened", "clicked"]),
        )
    )
    events = events_result.all()

    # Build contact->events mapping
    contact_events: dict[str, list[datetime]] = defaultdict(list)
    for contact_id, event_dt in events:
        contact_events[contact_id].append(event_dt)

    def period_key(dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if granularity == "day":
            return dt.strftime("%Y-%m-%d")
        elif granularity == "month":
            return dt.strftime("%Y-%m")
        else:
            return f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]:02d}"

    def period_offset(signup_dt: datetime, event_dt: datetime) -> int:
        if signup_dt.tzinfo is None:
            signup_dt = signup_dt.replace(tzinfo=timezone.utc)
        if event_dt.tzinfo is None:
            event_dt = event_dt.replace(tzinfo=timezone.utc)
        diff = (event_dt - signup_dt).total_seconds()
        if granularity == "day":
            return int(diff / 86400)
        elif granularity == "month":
            return int(diff / (86400 * 30))
        else:
            return int(diff / (86400 * 7))

    # Group contacts into cohorts
    cohorts: dict[str, list[tuple[str, datetime]]] = defaultdict(list)
    for contact_id, created_at in contacts:
        key = period_key(created_at)
        cohorts[key].append((contact_id, created_at))

    # Calculate retention for each cohort
    results = []
    for cohort_key, cohort_contacts in sorted(cohorts.items()):
        cohort_size = len(cohort_contacts)
        if cohort_size == 0:
            continue

        for offset in range(min(periods, 8)):
            active_in_period = 0
            for contact_id, signup_dt in cohort_contacts:
                for event_dt in contact_events.get(contact_id, []):
                    if period_offset(signup_dt, event_dt) == offset:
                        active_in_period += 1
                        break

            results.append(CohortData(
                cohort_period=cohort_key,
                cohort_size=cohort_size,
                period_offset=offset,
                active_count=active_in_period,
                retention_rate=(active_in_period / cohort_size) * 100,
            ).to_dict())

    return results


# ── Top performing content ────────────────────────────
async def get_top_campaigns(
    db: AsyncSession,
    metric: str = "open_rate",    # open_rate|click_rate|engagement_score
    limit: int = 10,
    min_sent: int = 10,           # Minimum sent to qualify
) -> list[dict]:
    """Get top performing campaigns ranked by specified metric."""
    result = await db.execute(
        select(Campaign)
        .where(Campaign.total_sent >= min_sent, Campaign.status == "sent")
        .order_by(Campaign.sent_at.desc())
        .limit(100)  # Pre-filter recent
    )
    campaigns = result.scalars().all()

    scored = []
    for c in campaigns:
        sent = c.total_sent or 1
        opened = c.total_opened or 0
        clicked = c.total_clicked or 0
        bounced = c.total_bounced or 0
        delivered = sent - bounced

        open_rate = (opened / max(delivered, 1)) * 100
        click_rate = (clicked / max(sent, 1)) * 100
        ctor = (clicked / max(opened, 1)) * 100 if opened > 0 else 0
        bounce_rate = (bounced / max(sent, 1)) * 100

        engagement_score = min(100, (
            open_rate * 0.3 + ctor * 0.4
            + (100 - bounce_rate) * 0.15
            + 100 * 0.15  # placeholder for unsub rate
        ))

        metrics_map = {
            "open_rate": open_rate,
            "click_rate": click_rate,
            "engagement_score": engagement_score,
        }

        scored.append({
            "campaign_id": c.id,
            "campaign_name": c.name,
            "total_sent": sent,
            "open_rate": round(open_rate, 2),
            "click_rate": round(click_rate, 2),
            "ctor": round(ctor, 2),
            "bounce_rate": round(bounce_rate, 2),
            "engagement_score": round(engagement_score, 1),
            "sent_at": c.sent_at.isoformat() if c.sent_at else None,
            "_sort_key": metrics_map.get(metric, open_rate),
        })

    scored.sort(key=lambda x: x["_sort_key"], reverse=True)
    for item in scored:
        del item["_sort_key"]

    return scored[:limit]


# ── Aggregate dashboard stats ─────────────────────────
async def get_dashboard_stats(db: AsyncSession, days: int = 30) -> dict:
    """
    Aggregate statistics for the marketing dashboard.

    Returns summary metrics across all campaigns and contacts.
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)

    # Contact stats
    total_contacts = (await db.execute(
        select(func.count(Contact.id))
    )).scalar() or 0

    active_contacts = (await db.execute(
        select(func.count(Contact.id)).where(Contact.subscribed.is_(True))
    )).scalar() or 0

    new_contacts = (await db.execute(
        select(func.count(Contact.id)).where(Contact.created_at >= start)
    )).scalar() or 0

    # Campaign stats
    total_campaigns = (await db.execute(
        select(func.count(Campaign.id)).where(Campaign.status == "sent")
    )).scalar() or 0

    recent_campaigns = (await db.execute(
        select(func.count(Campaign.id)).where(
            Campaign.status == "sent",
            Campaign.sent_at >= start,
        )
    )).scalar() or 0

    # Email event stats (recent period)
    event_counts_result = await db.execute(
        select(EmailEvent.event_type, func.count(EmailEvent.id))
        .where(EmailEvent.created_at >= start)
        .group_by(EmailEvent.event_type)
    )
    event_counts = {row[0]: row[1] for row in event_counts_result.all()}

    total_sent = event_counts.get("sent", 0)
    total_opened = event_counts.get("opened", 0)
    total_clicked = event_counts.get("clicked", 0)
    total_bounced = event_counts.get("bounced", 0)
    total_unsub = event_counts.get("unsubscribed", 0)

    return {
        "period_days": days,
        "contacts": {
            "total": total_contacts,
            "active_subscribers": active_contacts,
            "new_in_period": new_contacts,
            "churn_rate": round(
                (total_unsub / max(active_contacts, 1)) * 100, 2
            ),
        },
        "campaigns": {
            "total_sent": total_campaigns,
            "in_period": recent_campaigns,
        },
        "email_events": {
            "sent": total_sent,
            "opened": total_opened,
            "clicked": total_clicked,
            "bounced": total_bounced,
            "unsubscribed": total_unsub,
            "open_rate": round(
                (total_opened / max(total_sent, 1)) * 100, 2
            ),
            "click_rate": round(
                (total_clicked / max(total_sent, 1)) * 100, 2
            ),
            "bounce_rate": round(
                (total_bounced / max(total_sent, 1)) * 100, 2
            ),
        },
        "health": {
            "deliverability": round(
                ((total_sent - total_bounced) / max(total_sent, 1)) * 100, 1
            ),
            "list_growth": new_contacts - total_unsub,
        },
    }
