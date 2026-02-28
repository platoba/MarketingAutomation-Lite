"""Webhook tracking — open pixel + click redirect + unsubscribe."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Campaign, Contact, EmailEvent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/track", tags=["tracking"])

# 1x1 transparent GIF pixel
TRACKING_PIXEL = (
    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
    b"\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x00\x00\x00\x00"
    b"\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
    b"\x44\x01\x00\x3b"
)


@router.get("/open/{campaign_id}/{contact_id}")
async def track_open(
    campaign_id: str,
    contact_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Record an email open event and return a tracking pixel."""
    existing = await db.execute(
        select(EmailEvent).where(
            EmailEvent.campaign_id == campaign_id,
            EmailEvent.contact_id == contact_id,
            EmailEvent.event_type == "opened",
        )
    )
    if not existing.scalar_one_or_none():
        db.add(EmailEvent(
            campaign_id=campaign_id,
            contact_id=contact_id,
            event_type="opened",
        ))
        result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
        campaign = result.scalar_one_or_none()
        if campaign:
            campaign.total_opened = (campaign.total_opened or 0) + 1
        await db.commit()
        logger.info(f"Open tracked: campaign={campaign_id} contact={contact_id}")

    return Response(content=TRACKING_PIXEL, media_type="image/gif")


@router.get("/click/{campaign_id}/{contact_id}")
async def track_click(
    campaign_id: str,
    contact_id: str,
    url: str = Query(..., description="Destination URL"),
    db: AsyncSession = Depends(get_db),
):
    """Record a click event and redirect to the destination URL."""
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "Invalid redirect URL")

    db.add(EmailEvent(
        campaign_id=campaign_id,
        contact_id=contact_id,
        event_type="clicked",
        metadata_='{"url": "' + url + '"}',
    ))
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if campaign:
        campaign.total_clicked = (campaign.total_clicked or 0) + 1
    await db.commit()
    logger.info(f"Click tracked: campaign={campaign_id} contact={contact_id} url={url}")

    return RedirectResponse(url=url, status_code=302)


@router.get("/unsubscribe/{campaign_id}/{contact_id}")
async def track_unsubscribe(
    campaign_id: str,
    contact_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Unsubscribe a contact and record the event."""
    result = await db.execute(select(Contact).where(Contact.id == contact_id))
    contact = result.scalar_one_or_none()
    if contact:
        contact.subscribed = False

    db.add(EmailEvent(
        campaign_id=campaign_id,
        contact_id=contact_id,
        event_type="unsubscribed",
    ))
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if campaign:
        campaign.total_unsubscribed = (campaign.total_unsubscribed or 0) + 1
    await db.commit()

    return {"message": "You have been unsubscribed successfully."}
