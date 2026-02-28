"""Webhook management and event dispatch API."""

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.webhook import WebhookDelivery, WebhookEndpoint

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ── Event Types ──────────────────────────────────────────
VALID_EVENTS = [
    "contact.created",
    "contact.updated",
    "contact.deleted",
    "contact.subscribed",
    "contact.unsubscribed",
    "campaign.created",
    "campaign.sent",
    "campaign.completed",
    "email.sent",
    "email.opened",
    "email.clicked",
    "email.bounced",
    "email.unsubscribed",
    "workflow.triggered",
    "workflow.completed",
    "workflow.failed",
    "ab_test.started",
    "ab_test.completed",
    "ab_test.winner_selected",
]


# ── Schemas ──────────────────────────────────────────────
class WebhookCreate(BaseModel):
    url: str
    secret: Optional[str] = None
    events: list[str] = Field(default_factory=lambda: ["*"])
    description: str = ""
    max_failures: int = Field(10, ge=1, le=100)


class WebhookUpdate(BaseModel):
    url: Optional[str] = None
    secret: Optional[str] = None
    events: Optional[list[str]] = None
    description: Optional[str] = None
    active: Optional[bool] = None
    max_failures: Optional[int] = None


class WebhookOut(BaseModel):
    id: str
    url: str
    events: list[str]
    active: bool
    description: str
    consecutive_failures: int
    total_deliveries: int
    total_failures: int
    max_failures: int
    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, wh):
        events = wh.events
        if isinstance(events, str):
            try:
                events = json.loads(events)
            except (json.JSONDecodeError, TypeError):
                events = []
        return cls(
            id=wh.id,
            url=wh.url,
            events=events,
            active=wh.active,
            description=wh.description or "",
            consecutive_failures=wh.consecutive_failures or 0,
            total_deliveries=wh.total_deliveries or 0,
            total_failures=wh.total_failures or 0,
            max_failures=wh.max_failures or 10,
            last_success_at=wh.last_success_at,
            last_failure_at=wh.last_failure_at,
            created_at=wh.created_at,
        )


class DeliveryOut(BaseModel):
    id: str
    endpoint_id: str
    event_type: str
    response_status: Optional[int]
    success: bool
    duration_ms: int
    attempt: int
    created_at: datetime

    model_config = {"from_attributes": True}


class TestWebhookRequest(BaseModel):
    event_type: str = "test.ping"
    payload: dict = Field(default_factory=lambda: {"message": "Test webhook delivery"})


# ── Endpoints ────────────────────────────────────────────
@router.get("/events", response_model=list[str])
async def list_event_types():
    """List all available webhook event types."""
    return VALID_EVENTS


@router.post("/", response_model=WebhookOut, status_code=201)
async def create_webhook(data: WebhookCreate, db: AsyncSession = Depends(get_db)):
    # Validate event types
    for evt in data.events:
        if evt != "*" and evt not in VALID_EVENTS:
            raise HTTPException(400, f"Invalid event type: {evt}")

    wh = WebhookEndpoint(
        url=data.url,
        secret=data.secret,
        events=json.dumps(data.events),
        description=data.description,
        max_failures=data.max_failures,
    )
    db.add(wh)
    await db.commit()
    await db.refresh(wh)
    return WebhookOut.from_model(wh)


@router.get("/", response_model=list[WebhookOut])
async def list_webhooks(
    active: Optional[bool] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(WebhookEndpoint)
    if active is not None:
        stmt = stmt.where(WebhookEndpoint.active == active)
    stmt = stmt.order_by(WebhookEndpoint.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return [WebhookOut.from_model(wh) for wh in result.scalars().all()]


@router.get("/{webhook_id}", response_model=WebhookOut)
async def get_webhook(webhook_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WebhookEndpoint).where(WebhookEndpoint.id == webhook_id))
    wh = result.scalar_one_or_none()
    if not wh:
        raise HTTPException(404, "Webhook not found")
    return WebhookOut.from_model(wh)


@router.patch("/{webhook_id}", response_model=WebhookOut)
async def update_webhook(webhook_id: str, data: WebhookUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WebhookEndpoint).where(WebhookEndpoint.id == webhook_id))
    wh = result.scalar_one_or_none()
    if not wh:
        raise HTTPException(404, "Webhook not found")

    updates = data.model_dump(exclude_unset=True)
    if "events" in updates:
        for evt in updates["events"]:
            if evt != "*" and evt not in VALID_EVENTS:
                raise HTTPException(400, f"Invalid event type: {evt}")
        updates["events"] = json.dumps(updates["events"])

    for key, val in updates.items():
        setattr(wh, key, val)

    # Reset failure counter if re-enabled
    if data.active is True:
        wh.consecutive_failures = 0

    await db.commit()
    await db.refresh(wh)
    return WebhookOut.from_model(wh)


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(webhook_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WebhookEndpoint).where(WebhookEndpoint.id == webhook_id))
    wh = result.scalar_one_or_none()
    if not wh:
        raise HTTPException(404, "Webhook not found")
    await db.delete(wh)
    await db.commit()


@router.get("/{webhook_id}/deliveries", response_model=list[DeliveryOut])
async def list_deliveries(
    webhook_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List delivery history for a webhook."""
    stmt = (
        select(WebhookDelivery)
        .where(WebhookDelivery.endpoint_id == webhook_id)
        .order_by(WebhookDelivery.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/{webhook_id}/test", status_code=200)
async def test_webhook(
    webhook_id: str,
    data: TestWebhookRequest = TestWebhookRequest(),
    db: AsyncSession = Depends(get_db),
):
    """Send a test ping to the webhook endpoint."""
    result = await db.execute(select(WebhookEndpoint).where(WebhookEndpoint.id == webhook_id))
    wh = result.scalar_one_or_none()
    if not wh:
        raise HTTPException(404, "Webhook not found")

    from app.services.webhook_dispatcher import dispatch_webhook

    delivery = await dispatch_webhook(
        db=db,
        endpoint=wh,
        event_type=data.event_type,
        payload=data.payload,
    )

    return {
        "message": "Test webhook sent",
        "success": delivery.success,
        "response_status": delivery.response_status,
        "duration_ms": delivery.duration_ms,
    }
