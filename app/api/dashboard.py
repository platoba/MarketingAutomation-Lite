"""Dashboard stats API."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Campaign, Contact, Workflow
from app.schemas import DashboardStats

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
async def get_stats(db: AsyncSession = Depends(get_db)):
    total_contacts = (await db.execute(select(func.count(Contact.id)))).scalar() or 0
    subscribed = (
        await db.execute(select(func.count(Contact.id)).where(Contact.subscribed.is_(True)))
    ).scalar() or 0
    unsubscribed = total_contacts - subscribed

    total_campaigns = (await db.execute(select(func.count(Campaign.id)))).scalar() or 0
    sent_campaigns = (
        await db.execute(select(func.count(Campaign.id)).where(Campaign.status == "sent"))
    ).scalar() or 0
    draft_campaigns = (
        await db.execute(select(func.count(Campaign.id)).where(Campaign.status == "draft"))
    ).scalar() or 0

    total_sent = (
        await db.execute(select(func.coalesce(func.sum(Campaign.total_sent), 0)))
    ).scalar() or 0
    total_opened = (
        await db.execute(select(func.coalesce(func.sum(Campaign.total_opened), 0)))
    ).scalar() or 0
    total_clicked = (
        await db.execute(select(func.coalesce(func.sum(Campaign.total_clicked), 0)))
    ).scalar() or 0

    avg_open = (total_opened / total_sent * 100) if total_sent > 0 else 0.0
    avg_click = (total_clicked / total_sent * 100) if total_sent > 0 else 0.0

    total_workflows = (await db.execute(select(func.count(Workflow.id)))).scalar() or 0
    active_workflows = (
        await db.execute(select(func.count(Workflow.id)).where(Workflow.active.is_(True)))
    ).scalar() or 0

    return DashboardStats(
        total_contacts=total_contacts,
        subscribed_contacts=subscribed,
        unsubscribed_contacts=unsubscribed,
        total_campaigns=total_campaigns,
        campaigns_sent=sent_campaigns,
        campaigns_draft=draft_campaigns,
        total_emails_sent=total_sent,
        avg_open_rate=round(avg_open, 2),
        avg_click_rate=round(avg_click, 2),
        total_workflows=total_workflows,
        active_workflows=active_workflows,
    )
