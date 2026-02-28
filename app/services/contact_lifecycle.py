"""Contact lifecycle management — automated stage transitions, engagement tracking, and dormancy detection."""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import and_, case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Contact, EmailEvent
from app.models.lead_score import ContactScore

logger = logging.getLogger(__name__)


# ── Lifecycle stages (ordered progression) ─────────────
class LifecycleStage(str, Enum):
    NEW = "new"                     # Just signed up, no engagement
    SUBSCRIBER = "subscriber"       # Confirmed subscription
    LEAD = "lead"                   # Showed initial interest
    MQL = "mql"                     # Marketing Qualified Lead
    SQL = "sql"                     # Sales Qualified Lead
    OPPORTUNITY = "opportunity"     # Active deal / high engagement
    CUSTOMER = "customer"           # Made a purchase / converted
    EVANGELIST = "evangelist"       # Top advocate
    DORMANT = "dormant"             # Inactive for extended period
    CHURNED = "churned"             # Unsubscribed or bounced out


# Stage progression order (higher index = more engaged)
STAGE_ORDER = {
    LifecycleStage.NEW: 0,
    LifecycleStage.SUBSCRIBER: 1,
    LifecycleStage.LEAD: 2,
    LifecycleStage.MQL: 3,
    LifecycleStage.SQL: 4,
    LifecycleStage.OPPORTUNITY: 5,
    LifecycleStage.CUSTOMER: 6,
    LifecycleStage.EVANGELIST: 7,
    LifecycleStage.DORMANT: -1,
    LifecycleStage.CHURNED: -2,
}


# ── Transition rules ──────────────────────────────────
@dataclass
class TransitionRule:
    """Rule for automatic stage transition."""
    from_stage: LifecycleStage
    to_stage: LifecycleStage
    min_score: float = 0
    min_opens: int = 0
    min_clicks: int = 0
    min_days_in_stage: int = 0
    max_inactive_days: Optional[int] = None  # For dormancy detection
    description: str = ""


# Default transition rules
DEFAULT_RULES: list[TransitionRule] = [
    TransitionRule(
        from_stage=LifecycleStage.NEW,
        to_stage=LifecycleStage.SUBSCRIBER,
        min_score=5,
        description="Confirmed signup or first page view",
    ),
    TransitionRule(
        from_stage=LifecycleStage.SUBSCRIBER,
        to_stage=LifecycleStage.LEAD,
        min_opens=2,
        min_score=15,
        description="Opened 2+ emails, showing interest",
    ),
    TransitionRule(
        from_stage=LifecycleStage.LEAD,
        to_stage=LifecycleStage.MQL,
        min_clicks=3,
        min_score=35,
        min_days_in_stage=3,
        description="Clicked 3+ links, score above 35",
    ),
    TransitionRule(
        from_stage=LifecycleStage.MQL,
        to_stage=LifecycleStage.SQL,
        min_score=55,
        min_clicks=5,
        min_days_in_stage=5,
        description="High engagement, ready for sales",
    ),
    TransitionRule(
        from_stage=LifecycleStage.SQL,
        to_stage=LifecycleStage.OPPORTUNITY,
        min_score=70,
        min_days_in_stage=3,
        description="Very high engagement, active opportunity",
    ),
    TransitionRule(
        from_stage=LifecycleStage.OPPORTUNITY,
        to_stage=LifecycleStage.CUSTOMER,
        min_score=80,
        description="Converted — marked as customer",
    ),
    TransitionRule(
        from_stage=LifecycleStage.CUSTOMER,
        to_stage=LifecycleStage.EVANGELIST,
        min_score=90,
        min_clicks=10,
        description="Top advocate with highest engagement",
    ),
]

# Dormancy rules (apply to any active stage)
DORMANCY_RULES: list[TransitionRule] = [
    TransitionRule(
        from_stage=LifecycleStage.SUBSCRIBER,
        to_stage=LifecycleStage.DORMANT,
        max_inactive_days=60,
        description="No engagement for 60 days",
    ),
    TransitionRule(
        from_stage=LifecycleStage.LEAD,
        to_stage=LifecycleStage.DORMANT,
        max_inactive_days=45,
        description="No engagement for 45 days",
    ),
    TransitionRule(
        from_stage=LifecycleStage.MQL,
        to_stage=LifecycleStage.DORMANT,
        max_inactive_days=30,
        description="No engagement for 30 days",
    ),
    TransitionRule(
        from_stage=LifecycleStage.SQL,
        to_stage=LifecycleStage.DORMANT,
        max_inactive_days=21,
        description="No engagement for 21 days",
    ),
]


@dataclass
class TransitionResult:
    """Result of a lifecycle transition attempt."""
    contact_id: str
    previous_stage: str
    new_stage: str
    transitioned: bool
    rule_description: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "contact_id": self.contact_id,
            "previous_stage": self.previous_stage,
            "new_stage": self.new_stage,
            "transitioned": self.transitioned,
            "rule_description": self.rule_description,
            "reason": self.reason,
        }


# ── Get engagement stats for a contact ────────────────
async def get_contact_engagement(
    db: AsyncSession,
    contact_id: str,
    days: int = 90,
) -> dict:
    """
    Calculate engagement metrics for a contact over the specified period.

    Returns:
        {
            "total_opens": int,
            "total_clicks": int,
            "total_bounces": int,
            "total_unsubscribes": int,
            "last_open_at": datetime | None,
            "last_click_at": datetime | None,
            "last_activity_at": datetime | None,
            "days_since_last_activity": int | None,
            "engagement_velocity": float,  # events per week
        }
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)

    # Count events by type
    stmt = (
        select(
            EmailEvent.event_type,
            func.count(EmailEvent.id),
            func.max(EmailEvent.created_at),
        )
        .where(
            EmailEvent.contact_id == contact_id,
            EmailEvent.created_at >= start,
        )
        .group_by(EmailEvent.event_type)
    )
    result = await db.execute(stmt)
    rows = result.all()

    stats = {
        "total_opens": 0,
        "total_clicks": 0,
        "total_bounces": 0,
        "total_unsubscribes": 0,
        "last_open_at": None,
        "last_click_at": None,
        "last_activity_at": None,
        "days_since_last_activity": None,
        "engagement_velocity": 0.0,
    }

    last_activity = None
    total_events = 0

    for event_type, count, last_at in rows:
        if event_type == "opened":
            stats["total_opens"] = count
            stats["last_open_at"] = last_at
        elif event_type == "clicked":
            stats["total_clicks"] = count
            stats["last_click_at"] = last_at
        elif event_type == "bounced":
            stats["total_bounces"] = count
        elif event_type == "unsubscribed":
            stats["total_unsubscribes"] = count

        total_events += count
        if last_at and (last_activity is None or last_at > last_activity):
            last_activity = last_at

    if last_activity:
        if last_activity.tzinfo is None:
            last_activity = last_activity.replace(tzinfo=timezone.utc)
        stats["last_activity_at"] = last_activity
        stats["days_since_last_activity"] = (now - last_activity).days

    # Engagement velocity: events per week
    weeks = max(days / 7, 1)
    stats["engagement_velocity"] = round(total_events / weeks, 2)

    return stats


# ── Evaluate and apply transitions ────────────────────
async def evaluate_lifecycle(
    db: AsyncSession,
    contact_id: str,
    current_stage: str = "new",
    score: float = 0,
    custom_rules: Optional[list[TransitionRule]] = None,
) -> TransitionResult:
    """
    Evaluate lifecycle transition rules for a contact.

    Checks both progression rules and dormancy rules.
    Returns the transition result (may or may not trigger a change).
    """
    rules = custom_rules or DEFAULT_RULES
    engagement = await get_contact_engagement(db, contact_id)

    # First check dormancy
    for rule in DORMANCY_RULES:
        if rule.from_stage.value != current_stage:
            continue
        if rule.max_inactive_days and engagement["days_since_last_activity"] is not None:
            if engagement["days_since_last_activity"] >= rule.max_inactive_days:
                return TransitionResult(
                    contact_id=contact_id,
                    previous_stage=current_stage,
                    new_stage=rule.to_stage.value,
                    transitioned=True,
                    rule_description=rule.description,
                    reason=f"Inactive for {engagement['days_since_last_activity']} days (threshold: {rule.max_inactive_days})",
                )

    # Check churn (unsubscribed)
    if engagement["total_unsubscribes"] > 0 and current_stage != LifecycleStage.CHURNED.value:
        return TransitionResult(
            contact_id=contact_id,
            previous_stage=current_stage,
            new_stage=LifecycleStage.CHURNED.value,
            transitioned=True,
            rule_description="Auto-churn on unsubscribe",
            reason="Contact unsubscribed",
        )

    # Then check progression
    for rule in rules:
        if rule.from_stage.value != current_stage:
            continue

        # Check all conditions
        if score < rule.min_score:
            continue
        if engagement["total_opens"] < rule.min_opens:
            continue
        if engagement["total_clicks"] < rule.min_clicks:
            continue

        return TransitionResult(
            contact_id=contact_id,
            previous_stage=current_stage,
            new_stage=rule.to_stage.value,
            transitioned=True,
            rule_description=rule.description,
            reason=f"Score={score:.0f}, opens={engagement['total_opens']}, clicks={engagement['total_clicks']}",
        )

    return TransitionResult(
        contact_id=contact_id,
        previous_stage=current_stage,
        new_stage=current_stage,
        transitioned=False,
        reason="No matching transition rule",
    )


# ── Batch lifecycle processing ────────────────────────
async def process_lifecycle_batch(
    db: AsyncSession,
    limit: int = 100,
) -> dict:
    """
    Process lifecycle transitions for a batch of contacts.
    Checks scored contacts and applies transition rules.

    Returns:
        {
            "processed": int,
            "transitioned": int,
            "transitions": [TransitionResult.to_dict(), ...]
        }
    """
    # Get contacts with scores
    stmt = (
        select(ContactScore)
        .order_by(ContactScore.score_updated_at.desc().nullslast())
        .limit(limit)
    )
    result = await db.execute(stmt)
    scored_contacts = result.scalars().all()

    transitions = []
    transitioned_count = 0

    for cs in scored_contacts:
        current_stage = cs.lifecycle_stage or "new"
        tr = await evaluate_lifecycle(
            db,
            contact_id=cs.contact_id,
            current_stage=current_stage,
            score=cs.total_score or 0,
        )

        if tr.transitioned:
            cs.lifecycle_stage = tr.new_stage
            transitioned_count += 1
            transitions.append(tr.to_dict())

    if transitioned_count > 0:
        await db.commit()

    return {
        "processed": len(scored_contacts),
        "transitioned": transitioned_count,
        "transitions": transitions,
    }


# ── Lifecycle distribution report ─────────────────────
async def get_lifecycle_report(db: AsyncSession) -> dict:
    """
    Get comprehensive lifecycle distribution with stats per stage.

    Returns:
        {
            "total_contacts": int,
            "stages": {
                "new": {"count": N, "pct": X},
                ...
            },
            "health": {
                "active_rate": float,
                "dormant_rate": float,
                "churn_rate": float,
            }
        }
    """
    stmt = (
        select(
            ContactScore.lifecycle_stage,
            func.count(ContactScore.id),
            func.avg(ContactScore.total_score),
            func.avg(ContactScore.engagement_score),
        )
        .group_by(ContactScore.lifecycle_stage)
    )
    result = await db.execute(stmt)
    rows = result.all()

    total = sum(row[1] for row in rows)
    stages = {}
    dormant = 0
    churned = 0

    for stage, count, avg_score, avg_engagement in rows:
        stage_name = stage or "unknown"
        stages[stage_name] = {
            "count": count,
            "pct": round((count / max(total, 1)) * 100, 1),
            "avg_score": round(float(avg_score or 0), 1),
            "avg_engagement": round(float(avg_engagement or 0), 1),
        }
        if stage_name == "dormant":
            dormant = count
        elif stage_name == "churned":
            churned = count

    active = total - dormant - churned

    return {
        "total_contacts": total,
        "stages": stages,
        "health": {
            "active_rate": round((active / max(total, 1)) * 100, 1),
            "dormant_rate": round((dormant / max(total, 1)) * 100, 1),
            "churn_rate": round((churned / max(total, 1)) * 100, 1),
        },
    }


# ── Re-engagement candidates ─────────────────────────
async def get_reengagement_candidates(
    db: AsyncSession,
    min_inactive_days: int = 30,
    max_inactive_days: int = 90,
    limit: int = 100,
) -> list[dict]:
    """
    Find contacts who are becoming dormant but might be re-engaged.
    These are contacts with some past engagement but recent inactivity.
    """
    now = datetime.now(timezone.utc)
    inactive_start = now - timedelta(days=max_inactive_days)
    inactive_end = now - timedelta(days=min_inactive_days)

    # Find contacts whose last activity was between min and max days ago
    stmt = (
        select(
            ContactScore.contact_id,
            ContactScore.lifecycle_stage,
            ContactScore.total_score,
            ContactScore.engagement_score,
            ContactScore.last_activity_at,
            Contact.email,
            Contact.first_name,
        )
        .join(Contact, Contact.id == ContactScore.contact_id)
        .where(
            ContactScore.last_activity_at.isnot(None),
            ContactScore.last_activity_at >= inactive_start,
            ContactScore.last_activity_at <= inactive_end,
            ContactScore.engagement_score > 5,  # Had some engagement
            Contact.subscribed.is_(True),
        )
        .order_by(ContactScore.engagement_score.desc())
        .limit(limit)
    )

    result = await db.execute(stmt)
    rows = result.all()

    candidates = []
    for row in rows:
        last_active = row.last_activity_at
        if last_active and last_active.tzinfo is None:
            last_active = last_active.replace(tzinfo=timezone.utc)
        days_inactive = (now - last_active).days if last_active else None

        candidates.append({
            "contact_id": row.contact_id,
            "email": row.email,
            "name": row.first_name or "",
            "lifecycle_stage": row.lifecycle_stage,
            "total_score": round(row.total_score or 0, 1),
            "engagement_score": round(row.engagement_score or 0, 1),
            "days_inactive": days_inactive,
            "reengagement_priority": "high" if (row.engagement_score or 0) > 30 else "medium",
        })

    return candidates
