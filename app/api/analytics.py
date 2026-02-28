"""Analytics API — campaign metrics, engagement reports, cohort analysis, health score."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.analytics import (
    CampaignMetrics,
    CohortRow,
    EngagementReport,
    HealthScore,
    calculate_health_score,
    get_campaign_metrics,
    get_contact_cohorts,
    get_engagement_report,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/campaigns/{campaign_id}/metrics", response_model=CampaignMetrics)
async def campaign_metrics(campaign_id: str, db: AsyncSession = Depends(get_db)):
    """Get detailed metrics for a specific campaign."""
    try:
        return await get_campaign_metrics(db, campaign_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/campaigns/{campaign_id}/engagement", response_model=EngagementReport)
async def campaign_engagement(campaign_id: str, db: AsyncSession = Depends(get_db)):
    """Get hourly engagement breakdown for a campaign."""
    return await get_engagement_report(db, campaign_id)


@router.get("/cohorts", response_model=list[CohortRow])
async def contact_cohorts(
    weeks: int = Query(12, ge=1, le=52),
    db: AsyncSession = Depends(get_db),
):
    """Get weekly contact cohort analysis."""
    return await get_contact_cohorts(db, weeks)


@router.get("/health", response_model=HealthScore)
async def health_score(db: AsyncSession = Depends(get_db)):
    """Calculate overall email marketing health score."""
    return await calculate_health_score(db)
