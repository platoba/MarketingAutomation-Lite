"""Lead scoring engine — calculates, updates, and manages contact scores."""

import json
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Contact, EmailEvent
from app.models.lead_score import ContactScore, ScoreEvent, ScoringRule, SuppressionList


# ── Grade thresholds ───────────────────────────────────
GRADE_THRESHOLDS = [
    (90, "A+"),
    (80, "A"),
    (70, "B+"),
    (60, "B"),
    (45, "C"),
    (25, "D"),
    (0, "F"),
]

LIFECYCLE_THRESHOLDS = [
    (90, "evangelist"),
    (70, "customer"),
    (55, "sql"),
    (40, "mql"),
    (20, "lead"),
    (0, "subscriber"),
]


def _score_to_grade(score: float) -> str:
    for threshold, grade in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


def _score_to_lifecycle(score: float, current: str) -> str:
    """Determine lifecycle stage from score. Never auto-demote from customer/evangelist."""
    if current in ("customer", "evangelist"):
        return current
    for threshold, stage in LIFECYCLE_THRESHOLDS:
        if score >= threshold:
            return stage
    return "subscriber"


# ── Profile completeness scoring ───────────────────────
def calculate_profile_score(contact: Contact) -> float:
    """Score 0-20 based on how complete the contact profile is."""
    score = 0.0
    if contact.email:
        score += 4
    if contact.first_name and contact.first_name.strip():
        score += 4
    if contact.last_name and contact.last_name.strip():
        score += 3
    if contact.phone and contact.phone.strip():
        score += 3
    if contact.country and contact.country.strip():
        score += 3
    # Custom fields bonus
    custom = contact.custom_fields
    if isinstance(custom, str):
        try:
            custom = json.loads(custom)
        except (json.JSONDecodeError, TypeError):
            custom = {}
    if isinstance(custom, dict) and len(custom) >= 2:
        score += 3
    return min(20.0, score)


# ── Recency scoring ───────────────────────────────────
def calculate_recency_score(last_activity: Optional[datetime]) -> float:
    """Score 0-20 based on recency of last engagement. Decays over 90 days."""
    if not last_activity:
        return 0.0
    now = datetime.now(timezone.utc)
    if last_activity.tzinfo is None:
        last_activity = last_activity.replace(tzinfo=timezone.utc)
    days_ago = (now - last_activity).total_seconds() / 86400
    if days_ago <= 0:
        return 20.0
    if days_ago >= 90:
        return 0.0
    # Exponential decay
    return round(20.0 * math.exp(-0.03 * days_ago), 2)


# ── Core scoring engine ───────────────────────────────
async def record_score_event(
    db: AsyncSession,
    contact_id: str,
    event_type: str,
    points: float,
    reason: str = "",
    rule_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> ScoreEvent:
    """Record a scoring event and update the contact's total score."""
    event = ScoreEvent(
        contact_id=contact_id,
        rule_id=rule_id,
        event_type=event_type,
        points=points,
        reason=reason,
        metadata_=json.dumps(metadata or {}),
    )
    db.add(event)

    # Upsert contact score
    result = await db.execute(
        select(ContactScore).where(ContactScore.contact_id == contact_id)
    )
    contact_score = result.scalar_one_or_none()

    if not contact_score:
        contact_score = ContactScore(contact_id=contact_id, total_score=0, engagement_score=0)
        db.add(contact_score)
        await db.flush()

    contact_score.engagement_score = max(0, (contact_score.engagement_score or 0) + points)
    contact_score.last_activity_at = datetime.now(timezone.utc)

    # Recalculate total
    contact_score.recency_score = calculate_recency_score(contact_score.last_activity_at)
    contact_score.total_score = (
        contact_score.engagement_score
        + contact_score.profile_score
        + contact_score.recency_score
    )
    contact_score.grade = _score_to_grade(contact_score.total_score)
    contact_score.lifecycle_stage = _score_to_lifecycle(
        contact_score.total_score, contact_score.lifecycle_stage
    )
    contact_score.score_updated_at = datetime.now(timezone.utc)

    await db.commit()
    return event


async def recalculate_contact_score(db: AsyncSession, contact_id: str) -> ContactScore:
    """Full recalculation of a contact's score from all events + profile + recency."""
    # Get contact
    result = await db.execute(select(Contact).where(Contact.id == contact_id))
    contact = result.scalar_one_or_none()
    if not contact:
        raise ValueError(f"Contact {contact_id} not found")

    # Sum engagement points from events
    events_sum = (
        await db.execute(
            select(func.coalesce(func.sum(ScoreEvent.points), 0)).where(
                ScoreEvent.contact_id == contact_id
            )
        )
    ).scalar() or 0

    # Profile score
    profile_score = calculate_profile_score(contact)

    # Last activity
    last_event = (
        await db.execute(
            select(func.max(ScoreEvent.created_at)).where(
                ScoreEvent.contact_id == contact_id
            )
        )
    ).scalar()

    recency_score = calculate_recency_score(last_event)

    # Upsert
    result = await db.execute(
        select(ContactScore).where(ContactScore.contact_id == contact_id)
    )
    contact_score = result.scalar_one_or_none()

    if not contact_score:
        contact_score = ContactScore(contact_id=contact_id)
        db.add(contact_score)

    engagement = max(0, float(events_sum))
    contact_score.engagement_score = engagement
    contact_score.profile_score = profile_score
    contact_score.recency_score = recency_score
    contact_score.total_score = engagement + profile_score + recency_score
    contact_score.grade = _score_to_grade(contact_score.total_score)
    contact_score.lifecycle_stage = _score_to_lifecycle(
        contact_score.total_score, contact_score.lifecycle_stage or "subscriber"
    )
    contact_score.last_activity_at = last_event
    contact_score.score_updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(contact_score)
    return contact_score


async def get_score_leaderboard(
    db: AsyncSession,
    limit: int = 50,
    min_score: float = 0,
    lifecycle_stage: Optional[str] = None,
) -> list[dict]:
    """Get top scored contacts — leaderboard view."""
    stmt = (
        select(ContactScore, Contact.email, Contact.first_name, Contact.last_name)
        .join(Contact, Contact.id == ContactScore.contact_id)
        .where(ContactScore.total_score >= min_score)
    )
    if lifecycle_stage:
        stmt = stmt.where(ContactScore.lifecycle_stage == lifecycle_stage)
    stmt = stmt.order_by(ContactScore.total_score.desc()).limit(limit)

    result = await db.execute(stmt)
    rows = result.all()

    return [
        {
            "contact_id": row.ContactScore.contact_id,
            "email": row.email,
            "name": f"{row.first_name or ''} {row.last_name or ''}".strip(),
            "total_score": round(row.ContactScore.total_score, 2),
            "engagement_score": round(row.ContactScore.engagement_score, 2),
            "profile_score": round(row.ContactScore.profile_score, 2),
            "recency_score": round(row.ContactScore.recency_score, 2),
            "grade": row.ContactScore.grade,
            "lifecycle_stage": row.ContactScore.lifecycle_stage,
            "last_activity_at": (
                row.ContactScore.last_activity_at.isoformat()
                if row.ContactScore.last_activity_at
                else None
            ),
        }
        for row in rows
    ]


async def get_lifecycle_distribution(db: AsyncSession) -> dict:
    """Get count of contacts per lifecycle stage."""
    stmt = (
        select(ContactScore.lifecycle_stage, func.count(ContactScore.id))
        .group_by(ContactScore.lifecycle_stage)
    )
    result = await db.execute(stmt)
    return {stage: count for stage, count in result.all()}


async def process_scoring_rules(
    db: AsyncSession, contact_id: str, event_type: str, metadata: Optional[dict] = None
) -> list[ScoreEvent]:
    """Apply all active scoring rules matching an event type."""
    result = await db.execute(
        select(ScoringRule).where(
            ScoringRule.active.is_(True),
            ScoringRule.event_type == event_type,
        )
    )
    rules = result.scalars().all()
    events = []

    for rule in rules:
        # Check max_per_contact limit
        if rule.max_per_contact and rule.max_per_contact > 0:
            count = (
                await db.execute(
                    select(func.count(ScoreEvent.id)).where(
                        ScoreEvent.contact_id == contact_id,
                        ScoreEvent.rule_id == rule.id,
                    )
                )
            ).scalar() or 0
            if count >= rule.max_per_contact:
                continue

        # Check condition filter
        if rule.condition and rule.condition != "{}":
            try:
                condition = json.loads(rule.condition) if isinstance(rule.condition, str) else rule.condition
                if metadata:
                    match = all(metadata.get(k) == v for k, v in condition.items())
                    if not match:
                        continue
                else:
                    continue
            except (json.JSONDecodeError, TypeError):
                pass

        event = await record_score_event(
            db,
            contact_id=contact_id,
            event_type=event_type,
            points=rule.points,
            reason=f"Rule: {rule.name}",
            rule_id=rule.id,
            metadata=metadata,
        )
        events.append(event)

    return events


# ── Suppression list management ────────────────────────
async def add_to_suppression(
    db: AsyncSession,
    email: str,
    reason: str,
    source: str = "",
    notes: str = "",
) -> SuppressionList:
    """Add email to global suppression list."""
    # Check if already exists
    result = await db.execute(
        select(SuppressionList).where(SuppressionList.email == email.lower())
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.reason = reason
        existing.source = source
        existing.notes = notes
        await db.commit()
        return existing

    entry = SuppressionList(
        email=email.lower(),
        reason=reason,
        source=source,
        notes=notes,
    )
    db.add(entry)
    await db.commit()
    return entry


async def check_suppression(db: AsyncSession, email: str) -> Optional[SuppressionList]:
    """Check if an email is on the suppression list."""
    result = await db.execute(
        select(SuppressionList).where(SuppressionList.email == email.lower())
    )
    return result.scalar_one_or_none()


async def remove_from_suppression(db: AsyncSession, email: str) -> bool:
    """Remove email from suppression list."""
    result = await db.execute(
        delete(SuppressionList).where(SuppressionList.email == email.lower())
    )
    await db.commit()
    return result.rowcount > 0


async def list_suppression(
    db: AsyncSession,
    reason: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> list[SuppressionList]:
    """List suppression entries with optional reason filter."""
    stmt = select(SuppressionList)
    if reason:
        stmt = stmt.where(SuppressionList.reason == reason)
    stmt = stmt.order_by(SuppressionList.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())
