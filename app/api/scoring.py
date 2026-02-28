"""Lead Scoring & Suppression API — manage scoring rules, view leaderboards, and suppress contacts."""

import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.lead_score import ContactScore, ScoreEvent, ScoringRule, SuppressionList
from app.services.scoring_engine import (
    add_to_suppression,
    check_suppression,
    get_lifecycle_distribution,
    get_score_leaderboard,
    list_suppression,
    process_scoring_rules,
    recalculate_contact_score,
    record_score_event,
    remove_from_suppression,
)

router = APIRouter(tags=["scoring"])


# ── Schemas ─────────────────────────────────────────────
class ScoringRuleCreate(BaseModel):
    name: str
    description: str = ""
    event_type: str  # email_opened|email_clicked|form_submitted|page_visited|tag_added|unsubscribed|bounced
    condition: dict = Field(default_factory=dict)
    points: int = 1
    max_per_contact: int = 0
    decay_days: int = 0
    active: bool = True


class ScoringRuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    event_type: Optional[str] = None
    condition: Optional[dict] = None
    points: Optional[int] = None
    max_per_contact: Optional[int] = None
    decay_days: Optional[int] = None
    active: Optional[bool] = None


class ScoringRuleOut(BaseModel):
    id: str
    name: str
    description: str
    event_type: str
    condition: dict
    points: int
    max_per_contact: int
    decay_days: int
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, rule):
        cond = rule.condition
        if isinstance(cond, str):
            try:
                cond = json.loads(cond)
            except (json.JSONDecodeError, TypeError):
                cond = {}
        return cls(
            id=rule.id,
            name=rule.name,
            description=rule.description or "",
            event_type=rule.event_type,
            condition=cond,
            points=rule.points,
            max_per_contact=rule.max_per_contact or 0,
            decay_days=rule.decay_days or 0,
            active=rule.active,
            created_at=rule.created_at,
        )


class ContactScoreOut(BaseModel):
    contact_id: str
    total_score: float
    engagement_score: float
    profile_score: float
    recency_score: float
    grade: str
    lifecycle_stage: str
    last_activity_at: Optional[datetime] = None
    score_updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ScoreEventCreate(BaseModel):
    contact_id: str
    event_type: str
    points: float
    reason: str = ""
    metadata: dict = Field(default_factory=dict)


class ScoreEventOut(BaseModel):
    id: str
    contact_id: str
    rule_id: Optional[str] = None
    event_type: str
    points: float
    reason: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SuppressionCreate(BaseModel):
    email: EmailStr
    reason: str  # bounce|complaint|unsubscribe|manual|compliance
    source: str = ""
    notes: str = ""


class SuppressionOut(BaseModel):
    id: str
    email: str
    reason: str
    source: str
    notes: str
    created_at: datetime

    model_config = {"from_attributes": True}


class BulkSuppressionRequest(BaseModel):
    emails: list[EmailStr]
    reason: str
    source: str = ""


# ── Scoring Rules CRUD ─────────────────────────────────
@router.post("/scoring/rules", response_model=ScoringRuleOut, status_code=201)
async def create_scoring_rule(body: ScoringRuleCreate, db: AsyncSession = Depends(get_db)):
    rule = ScoringRule(
        name=body.name,
        description=body.description,
        event_type=body.event_type,
        condition=json.dumps(body.condition),
        points=body.points,
        max_per_contact=body.max_per_contact,
        decay_days=body.decay_days,
        active=body.active,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return ScoringRuleOut.from_model(rule)


@router.get("/scoring/rules", response_model=list[ScoringRuleOut])
async def list_scoring_rules(
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ScoringRule)
    if active_only:
        stmt = stmt.where(ScoringRule.active.is_(True))
    stmt = stmt.order_by(ScoringRule.created_at.desc())
    result = await db.execute(stmt)
    return [ScoringRuleOut.from_model(r) for r in result.scalars().all()]


@router.get("/scoring/rules/{rule_id}", response_model=ScoringRuleOut)
async def get_scoring_rule(rule_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ScoringRule).where(ScoringRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Scoring rule not found")
    return ScoringRuleOut.from_model(rule)


@router.patch("/scoring/rules/{rule_id}", response_model=ScoringRuleOut)
async def update_scoring_rule(
    rule_id: str, body: ScoringRuleUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(ScoringRule).where(ScoringRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Scoring rule not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "condition":
            setattr(rule, field, json.dumps(value))
        else:
            setattr(rule, field, value)

    await db.commit()
    await db.refresh(rule)
    return ScoringRuleOut.from_model(rule)


@router.delete("/scoring/rules/{rule_id}", status_code=204)
async def delete_scoring_rule(rule_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ScoringRule).where(ScoringRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Scoring rule not found")
    await db.delete(rule)
    await db.commit()


# ── Contact Scores ─────────────────────────────────────
@router.get("/scoring/contacts/{contact_id}", response_model=ContactScoreOut)
async def get_contact_score(contact_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ContactScore).where(ContactScore.contact_id == contact_id)
    )
    score = result.scalar_one_or_none()
    if not score:
        raise HTTPException(404, "No score found for this contact")
    return score


@router.post("/scoring/contacts/{contact_id}/recalculate", response_model=ContactScoreOut)
async def recalculate_score(contact_id: str, db: AsyncSession = Depends(get_db)):
    try:
        score = await recalculate_contact_score(db, contact_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return score


@router.get("/scoring/leaderboard")
async def leaderboard(
    limit: int = Query(50, le=200),
    min_score: float = Query(0),
    lifecycle_stage: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    return await get_score_leaderboard(db, limit=limit, min_score=min_score, lifecycle_stage=lifecycle_stage)


@router.get("/scoring/lifecycle")
async def lifecycle_distribution(db: AsyncSession = Depends(get_db)):
    return await get_lifecycle_distribution(db)


# ── Score Events ───────────────────────────────────────
@router.post("/scoring/events", response_model=ScoreEventOut, status_code=201)
async def create_score_event(body: ScoreEventCreate, db: AsyncSession = Depends(get_db)):
    """Manually award/deduct points for a contact."""
    event = await record_score_event(
        db,
        contact_id=body.contact_id,
        event_type=body.event_type,
        points=body.points,
        reason=body.reason,
        metadata=body.metadata,
    )
    return event


class ProcessEventRequest(BaseModel):
    contact_id: str
    event_type: str
    metadata: dict = Field(default_factory=dict)


@router.post("/scoring/events/process")
async def process_event(
    body: ProcessEventRequest,
    db: AsyncSession = Depends(get_db),
):
    """Process an engagement event through all matching scoring rules."""
    events = await process_scoring_rules(db, body.contact_id, body.event_type, body.metadata)
    return {"processed": len(events), "events": [{"id": e.id, "points": e.points} for e in events]}


@router.get("/scoring/contacts/{contact_id}/history", response_model=list[ScoreEventOut])
async def score_history(
    contact_id: str,
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ScoreEvent)
        .where(ScoreEvent.contact_id == contact_id)
        .order_by(ScoreEvent.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


# ── Suppression List ───────────────────────────────────
@router.post("/suppression", response_model=SuppressionOut, status_code=201)
async def add_suppression(body: SuppressionCreate, db: AsyncSession = Depends(get_db)):
    entry = await add_to_suppression(db, body.email, body.reason, body.source, body.notes)
    return entry


@router.post("/suppression/bulk", status_code=201)
async def bulk_suppress(body: BulkSuppressionRequest, db: AsyncSession = Depends(get_db)):
    count = 0
    for email in body.emails:
        await add_to_suppression(db, email, body.reason, body.source)
        count += 1
    return {"suppressed": count}


@router.get("/suppression", response_model=list[SuppressionOut])
async def list_suppressions(
    reason: Optional[str] = None,
    skip: int = 0,
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
):
    return await list_suppression(db, reason=reason, skip=skip, limit=limit)


@router.get("/suppression/check")
async def check_suppressed(email: str, db: AsyncSession = Depends(get_db)):
    entry = await check_suppression(db, email)
    return {"suppressed": entry is not None, "entry": entry}


@router.delete("/suppression/{email}", status_code=204)
async def remove_suppression(email: str, db: AsyncSession = Depends(get_db)):
    removed = await remove_from_suppression(db, email)
    if not removed:
        raise HTTPException(404, "Email not found in suppression list")


@router.get("/suppression/stats")
async def suppression_stats(db: AsyncSession = Depends(get_db)):
    stmt = (
        select(SuppressionList.reason, func.count(SuppressionList.id))
        .group_by(SuppressionList.reason)
    )
    result = await db.execute(stmt)
    by_reason = {reason: count for reason, count in result.all()}
    total = sum(by_reason.values())
    return {"total": total, "by_reason": by_reason}
