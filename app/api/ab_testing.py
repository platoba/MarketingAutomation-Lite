"""A/B Testing API — create, manage, and evaluate split tests for campaigns."""

import json
import random
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.database import get_db
from app.models import Campaign
from app.models.ab_test import ABTest, ABTestVariant

router = APIRouter(prefix="/ab-tests", tags=["ab-testing"])


# ── Schemas ──────────────────────────────────────────────
class VariantCreate(BaseModel):
    name: str = "Variant A"
    subject: Optional[str] = None
    html_body: Optional[str] = None
    send_delay_minutes: int = 0


class ABTestCreate(BaseModel):
    campaign_id: str
    name: str
    test_type: str = "subject"  # subject|content|send_time
    winner_metric: str = "open_rate"
    auto_select_winner: bool = True
    test_percentage: float = Field(20.0, ge=5.0, le=50.0)
    wait_hours: int = Field(4, ge=1, le=72)
    variants: list[VariantCreate] = Field(default_factory=list, min_length=2, max_length=5)


class VariantOut(BaseModel):
    id: str
    name: str
    subject: Optional[str]
    html_body: Optional[str]
    send_delay_minutes: int
    total_sent: int
    total_opened: int
    total_clicked: int
    total_bounced: int
    open_rate: float
    click_rate: float
    is_winner: bool

    model_config = {"from_attributes": True}


class ABTestOut(BaseModel):
    id: str
    campaign_id: str
    name: str
    test_type: str
    status: str
    winner_variant_id: Optional[str]
    winner_metric: str
    auto_select_winner: bool
    test_percentage: float
    wait_hours: int
    variants: list[VariantOut] = Field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class RecordEventRequest(BaseModel):
    variant_id: str
    event_type: str  # sent|opened|clicked|bounced


class ABTestUpdate(BaseModel):
    name: Optional[str] = None
    winner_metric: Optional[str] = None
    auto_select_winner: Optional[bool] = None
    test_percentage: Optional[float] = None
    wait_hours: Optional[int] = None


# ── Endpoints ────────────────────────────────────────────
@router.post("/", response_model=ABTestOut, status_code=201)
async def create_ab_test(data: ABTestCreate, db: AsyncSession = Depends(get_db)):
    """Create an A/B test with variants for a campaign."""
    # Verify campaign exists
    result = await db.execute(select(Campaign).where(Campaign.id == data.campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if campaign.status not in ("draft", "scheduled"):
        raise HTTPException(400, "Campaign must be in draft or scheduled status")

    ab_test = ABTest(
        campaign_id=data.campaign_id,
        name=data.name,
        test_type=data.test_type,
        winner_metric=data.winner_metric,
        auto_select_winner=data.auto_select_winner,
        test_percentage=data.test_percentage,
        wait_hours=data.wait_hours,
    )
    db.add(ab_test)
    await db.flush()

    variants = []
    for v in data.variants:
        variant = ABTestVariant(
            ab_test_id=ab_test.id,
            name=v.name,
            subject=v.subject,
            html_body=v.html_body,
            send_delay_minutes=v.send_delay_minutes,
        )
        db.add(variant)
        variants.append(variant)

    await db.commit()

    return ABTestOut(
        id=ab_test.id,
        campaign_id=ab_test.campaign_id,
        name=ab_test.name,
        test_type=ab_test.test_type,
        status=ab_test.status,
        winner_variant_id=ab_test.winner_variant_id,
        winner_metric=ab_test.winner_metric,
        auto_select_winner=ab_test.auto_select_winner,
        test_percentage=ab_test.test_percentage,
        wait_hours=ab_test.wait_hours,
        variants=[VariantOut.model_validate(v) for v in variants],
        started_at=ab_test.started_at,
        completed_at=ab_test.completed_at,
        created_at=ab_test.created_at,
    )


@router.get("/", response_model=list[ABTestOut])
async def list_ab_tests(
    campaign_id: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ABTest)
    if campaign_id:
        stmt = stmt.where(ABTest.campaign_id == campaign_id)
    if status:
        stmt = stmt.where(ABTest.status == status)
    stmt = stmt.order_by(ABTest.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    tests = result.scalars().all()

    out = []
    for t in tests:
        vresult = await db.execute(
            select(ABTestVariant).where(ABTestVariant.ab_test_id == t.id)
        )
        variants = vresult.scalars().all()
        out.append(ABTestOut(
            id=t.id,
            campaign_id=t.campaign_id,
            name=t.name,
            test_type=t.test_type,
            status=t.status,
            winner_variant_id=t.winner_variant_id,
            winner_metric=t.winner_metric,
            auto_select_winner=t.auto_select_winner,
            test_percentage=t.test_percentage,
            wait_hours=t.wait_hours,
            variants=[VariantOut.model_validate(v) for v in variants],
            started_at=t.started_at,
            completed_at=t.completed_at,
            created_at=t.created_at,
        ))
    return out


@router.get("/{test_id}", response_model=ABTestOut)
async def get_ab_test(test_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ABTest).where(ABTest.id == test_id))
    ab_test = result.scalar_one_or_none()
    if not ab_test:
        raise HTTPException(404, "A/B test not found")

    vresult = await db.execute(
        select(ABTestVariant).where(ABTestVariant.ab_test_id == test_id)
    )
    variants = vresult.scalars().all()

    return ABTestOut(
        id=ab_test.id,
        campaign_id=ab_test.campaign_id,
        name=ab_test.name,
        test_type=ab_test.test_type,
        status=ab_test.status,
        winner_variant_id=ab_test.winner_variant_id,
        winner_metric=ab_test.winner_metric,
        auto_select_winner=ab_test.auto_select_winner,
        test_percentage=ab_test.test_percentage,
        wait_hours=ab_test.wait_hours,
        variants=[VariantOut.model_validate(v) for v in variants],
        started_at=ab_test.started_at,
        completed_at=ab_test.completed_at,
        created_at=ab_test.created_at,
    )


@router.patch("/{test_id}", response_model=ABTestOut)
async def update_ab_test(test_id: str, data: ABTestUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ABTest).where(ABTest.id == test_id))
    ab_test = result.scalar_one_or_none()
    if not ab_test:
        raise HTTPException(404, "A/B test not found")
    if ab_test.status not in ("draft",):
        raise HTTPException(400, "Can only update A/B tests in draft status")

    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(ab_test, key, val)
    await db.commit()
    await db.refresh(ab_test)

    vresult = await db.execute(
        select(ABTestVariant).where(ABTestVariant.ab_test_id == test_id)
    )
    variants = vresult.scalars().all()

    return ABTestOut(
        id=ab_test.id,
        campaign_id=ab_test.campaign_id,
        name=ab_test.name,
        test_type=ab_test.test_type,
        status=ab_test.status,
        winner_variant_id=ab_test.winner_variant_id,
        winner_metric=ab_test.winner_metric,
        auto_select_winner=ab_test.auto_select_winner,
        test_percentage=ab_test.test_percentage,
        wait_hours=ab_test.wait_hours,
        variants=[VariantOut.model_validate(v) for v in variants],
        started_at=ab_test.started_at,
        completed_at=ab_test.completed_at,
        created_at=ab_test.created_at,
    )


@router.post("/{test_id}/start", status_code=200)
async def start_ab_test(test_id: str, db: AsyncSession = Depends(get_db)):
    """Start the A/B test — begins sending to test segment."""
    result = await db.execute(select(ABTest).where(ABTest.id == test_id))
    ab_test = result.scalar_one_or_none()
    if not ab_test:
        raise HTTPException(404, "A/B test not found")
    if ab_test.status != "draft":
        raise HTTPException(400, f"Cannot start test in '{ab_test.status}' status")

    vresult = await db.execute(
        select(ABTestVariant).where(ABTestVariant.ab_test_id == test_id)
    )
    variants = vresult.scalars().all()
    if len(variants) < 2:
        raise HTTPException(400, "Need at least 2 variants to start a test")

    ab_test.status = "running"
    ab_test.started_at = datetime.now(timezone.utc)
    await db.commit()

    return {"message": "A/B test started", "test_id": test_id, "variants": len(variants)}


@router.post("/{test_id}/events", status_code=200)
async def record_variant_event(test_id: str, data: RecordEventRequest, db: AsyncSession = Depends(get_db)):
    """Record an event (sent/opened/clicked/bounced) for a variant."""
    result = await db.execute(select(ABTest).where(ABTest.id == test_id))
    ab_test = result.scalar_one_or_none()
    if not ab_test:
        raise HTTPException(404, "A/B test not found")

    vresult = await db.execute(
        select(ABTestVariant).where(
            ABTestVariant.id == data.variant_id,
            ABTestVariant.ab_test_id == test_id,
        )
    )
    variant = vresult.scalar_one_or_none()
    if not variant:
        raise HTTPException(404, "Variant not found")

    if data.event_type == "sent":
        variant.total_sent += 1
    elif data.event_type == "opened":
        variant.total_opened += 1
    elif data.event_type == "clicked":
        variant.total_clicked += 1
    elif data.event_type == "bounced":
        variant.total_bounced += 1
    else:
        raise HTTPException(400, f"Unknown event type: {data.event_type}")

    # Recalculate rates
    if variant.total_sent > 0:
        variant.open_rate = round(variant.total_opened / variant.total_sent * 100, 2)
        variant.click_rate = round(variant.total_clicked / variant.total_sent * 100, 2)

    await db.commit()
    return {"message": "Event recorded", "variant": variant.name}


@router.post("/{test_id}/select-winner", status_code=200)
async def select_winner(test_id: str, variant_id: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """Manually select a winner or auto-select based on metrics."""
    result = await db.execute(select(ABTest).where(ABTest.id == test_id))
    ab_test = result.scalar_one_or_none()
    if not ab_test:
        raise HTTPException(404, "A/B test not found")
    if ab_test.status == "completed":
        raise HTTPException(400, "Test already completed")

    vresult = await db.execute(
        select(ABTestVariant).where(ABTestVariant.ab_test_id == test_id)
    )
    variants = vresult.scalars().all()
    if not variants:
        raise HTTPException(400, "No variants found")

    if variant_id:
        # Manual selection
        winner = next((v for v in variants if v.id == variant_id), None)
        if not winner:
            raise HTTPException(404, "Variant not found")
    else:
        # Auto-select based on metric
        metric = ab_test.winner_metric or "open_rate"
        if metric == "open_rate":
            winner = max(variants, key=lambda v: v.open_rate)
        elif metric == "click_rate":
            winner = max(variants, key=lambda v: v.click_rate)
        else:
            winner = max(variants, key=lambda v: v.open_rate)

    # Mark winner
    for v in variants:
        v.is_winner = v.id == winner.id
    ab_test.winner_variant_id = winner.id
    ab_test.status = "completed"
    ab_test.completed_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "message": "Winner selected",
        "winner": {
            "id": winner.id,
            "name": winner.name,
            "open_rate": winner.open_rate,
            "click_rate": winner.click_rate,
        },
    }


@router.delete("/{test_id}", status_code=204)
async def delete_ab_test(test_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ABTest).where(ABTest.id == test_id))
    ab_test = result.scalar_one_or_none()
    if not ab_test:
        raise HTTPException(404, "A/B test not found")
    if ab_test.status == "running":
        raise HTTPException(400, "Cannot delete a running test")

    # Delete variants first
    vresult = await db.execute(
        select(ABTestVariant).where(ABTestVariant.ab_test_id == test_id)
    )
    for v in vresult.scalars().all():
        await db.delete(v)

    await db.delete(ab_test)
    await db.commit()
