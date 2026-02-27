"""Email campaign sending tasks."""

import asyncio
import logging

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_campaign_task(self, campaign_id: str):
    """Send all emails for a campaign."""
    asyncio.run(_send_campaign(campaign_id))


async def _send_campaign(campaign_id: str):
    from uuid import UUID

    from sqlalchemy import select

    from app.database import async_session
    from app.models import Campaign, Contact, EmailEvent
    from app.services.email import send_email

    async with async_session() as db:
        result = await db.execute(select(Campaign).where(Campaign.id == UUID(campaign_id)))
        campaign = result.scalar_one_or_none()
        if not campaign:
            logger.error(f"Campaign {campaign_id} not found")
            return

        # Get target contacts (from segment or all subscribed)
        stmt = select(Contact).where(Contact.subscribed.is_(True))
        if campaign.segment_id:
            from app.models import contact_segments
            stmt = stmt.join(contact_segments).where(
                contact_segments.c.segment_id == campaign.segment_id
            )

        result = await db.execute(stmt)
        contacts = result.scalars().all()

        sent_count = 0
        for contact in contacts:
            success = await send_email(
                to_email=contact.email,
                subject=campaign.subject,
                html_body=campaign.html_body,
                text_body=campaign.text_body,
                from_name=campaign.from_name,
                from_email=campaign.from_email,
            )
            event_type = "sent" if success else "bounced"
            db.add(EmailEvent(
                campaign_id=campaign.id,
                contact_id=contact.id,
                event_type=event_type,
            ))
            if success:
                sent_count += 1

        campaign.total_sent = sent_count
        campaign.total_bounced = len(contacts) - sent_count
        campaign.status = "sent"
        from datetime import datetime, timezone
        campaign.sent_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(f"Campaign {campaign_id}: sent={sent_count}, bounced={len(contacts) - sent_count}")
