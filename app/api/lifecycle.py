"""Lifecycle management & campaign analytics API."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.campaign_analytics import (
    compare_campaigns,
    get_campaign_funnel,
    get_dashboard_stats,
    get_engagement_timeseries,
    get_cohort_retention,
    get_top_campaigns,
)
from app.services.contact_lifecycle import (
    evaluate_lifecycle,
    get_contact_engagement,
    get_lifecycle_report,
    get_reengagement_candidates,
    process_lifecycle_batch,
)
from app.services.email_validator import (
    ValidationLevel,
    validate_email,
    validate_emails_bulk,
)

router = APIRouter(tags=["lifecycle"])


# ── Schemas ──────────────────────────────────────────
class EvaluateRequest(BaseModel):
    contact_id: str
    current_stage: str = "new"
    score: float = 0


class BulkValidateRequest(BaseModel):
    emails: list[str]
    level: str = "domain"


class CompareCampaignsRequest(BaseModel):
    campaign_ids: list[str]


# ── Lifecycle Endpoints ─────────────────────────────
@router.get("/lifecycle/report")
async def lifecycle_report(db: AsyncSession = Depends(get_db)):
    """Get comprehensive lifecycle stage distribution and health metrics."""
    return await get_lifecycle_report(db)


@router.post("/lifecycle/evaluate")
async def evaluate_contact_lifecycle(
    body: EvaluateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Evaluate lifecycle transition rules for a specific contact."""
    result = await evaluate_lifecycle(
        db,
        contact_id=body.contact_id,
        current_stage=body.current_stage,
        score=body.score,
    )
    return result.to_dict()


@router.post("/lifecycle/process")
async def process_lifecycle(
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """
    Batch process lifecycle transitions for all scored contacts.
    Automatically applies progression and dormancy rules.
    """
    return await process_lifecycle_batch(db, limit=limit)


@router.get("/lifecycle/contacts/{contact_id}/engagement")
async def contact_engagement(
    contact_id: str,
    days: int = Query(90, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed engagement metrics for a specific contact."""
    return await get_contact_engagement(db, contact_id, days=days)


@router.get("/lifecycle/reengagement")
async def reengagement_candidates(
    min_inactive_days: int = Query(30, ge=7),
    max_inactive_days: int = Query(90, le=365),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Find contacts who are becoming dormant but might be re-engaged."""
    return await get_reengagement_candidates(
        db,
        min_inactive_days=min_inactive_days,
        max_inactive_days=max_inactive_days,
        limit=limit,
    )


# ── Campaign Analytics Endpoints ─────────────────────
@router.get("/analytics/campaigns/{campaign_id}/funnel")
async def campaign_funnel(
    campaign_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get conversion funnel analysis for a campaign."""
    try:
        metrics = await get_campaign_funnel(db, campaign_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return metrics.to_dict()


@router.post("/analytics/campaigns/compare")
async def compare(
    body: CompareCampaignsRequest,
    db: AsyncSession = Depends(get_db),
):
    """Compare metrics across multiple campaigns side by side."""
    if len(body.campaign_ids) > 10:
        raise HTTPException(400, "Maximum 10 campaigns for comparison")
    return await compare_campaigns(db, body.campaign_ids)


@router.get("/analytics/timeseries")
async def engagement_timeseries(
    campaign_id: Optional[str] = None,
    days: int = Query(30, ge=1, le=365),
    granularity: str = Query("day", pattern="^(hour|day|week)$"),
    db: AsyncSession = Depends(get_db),
):
    """Get time-series engagement data (opens, clicks, bounces over time)."""
    return await get_engagement_timeseries(
        db, campaign_id=campaign_id, days=days, granularity=granularity
    )


@router.get("/analytics/cohort")
async def cohort_retention(
    periods: int = Query(12, ge=2, le=52),
    granularity: str = Query("week", pattern="^(day|week|month)$"),
    db: AsyncSession = Depends(get_db),
):
    """Get cohort retention analysis table."""
    return await get_cohort_retention(db, periods=periods, granularity=granularity)


@router.get("/analytics/top-campaigns")
async def top_campaigns(
    metric: str = Query("open_rate", pattern="^(open_rate|click_rate|engagement_score)$"),
    limit: int = Query(10, ge=1, le=50),
    min_sent: int = Query(10, ge=1),
    db: AsyncSession = Depends(get_db),
):
    """Get top performing campaigns ranked by specified metric."""
    return await get_top_campaigns(db, metric=metric, limit=limit, min_sent=min_sent)


@router.get("/analytics/dashboard")
async def dashboard_stats(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Get aggregate dashboard statistics (contacts, campaigns, events, health)."""
    return await get_dashboard_stats(db, days=days)


# ── Email Validation Endpoints ───────────────────────
@router.post("/validate/email")
async def validate_single_email(
    email: str,
    level: str = Query("domain", pattern="^(syntax|domain|mx|full)$"),
):
    """
    Validate a single email address.
    Levels: syntax, domain (+ disposable/role check), mx (+ MX record), full (all checks).
    """
    result = validate_email(
        email,
        level=ValidationLevel(level),
        check_mx=(level in ("mx", "full")),
    )
    return result.to_dict()


@router.post("/validate/emails/bulk")
async def validate_bulk_emails(body: BulkValidateRequest):
    """Validate a batch of emails and get summary statistics."""
    if len(body.emails) > 1000:
        raise HTTPException(400, "Maximum 1000 emails per batch")
    return validate_emails_bulk(body.emails, level=ValidationLevel(body.level))
