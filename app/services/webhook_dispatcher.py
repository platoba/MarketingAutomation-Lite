"""Webhook dispatch service — delivers events to registered endpoints with retry and HMAC signing."""

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook import WebhookDelivery, WebhookEndpoint


def sign_payload(payload: str, secret: str) -> str:
    """Generate HMAC-SHA256 signature for webhook payload."""
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


async def dispatch_webhook(
    db: AsyncSession,
    endpoint: WebhookEndpoint,
    event_type: str,
    payload: dict,
    attempt: int = 1,
) -> WebhookDelivery:
    """Send a webhook event to an endpoint and record the delivery."""
    import httpx

    body = json.dumps({
        "event": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": payload,
    })

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Event": event_type,
        "X-Webhook-Delivery-Attempt": str(attempt),
    }

    if endpoint.secret:
        sig = sign_payload(body, endpoint.secret)
        headers["X-Webhook-Signature-256"] = f"sha256={sig}"

    delivery = WebhookDelivery(
        endpoint_id=endpoint.id,
        event_type=event_type,
        payload=body,
        attempt=attempt,
    )

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(endpoint.url, content=body, headers=headers)
            delivery.response_status = resp.status_code
            delivery.response_body = resp.text[:2000]
            delivery.success = 200 <= resp.status_code < 300
            delivery.duration_ms = int((time.monotonic() - start) * 1000)
    except Exception as exc:
        delivery.response_status = 0
        delivery.response_body = str(exc)[:2000]
        delivery.success = False
        delivery.duration_ms = int((time.monotonic() - start) * 1000)

    # Update endpoint stats
    endpoint.total_deliveries = (endpoint.total_deliveries or 0) + 1
    if delivery.success:
        endpoint.consecutive_failures = 0
        endpoint.last_success_at = datetime.now(timezone.utc)
    else:
        endpoint.consecutive_failures = (endpoint.consecutive_failures or 0) + 1
        endpoint.total_failures = (endpoint.total_failures or 0) + 1
        endpoint.last_failure_at = datetime.now(timezone.utc)

        # Auto-disable if too many consecutive failures
        if endpoint.consecutive_failures >= (endpoint.max_failures or 10):
            endpoint.active = False

    db.add(delivery)
    await db.commit()
    return delivery


async def dispatch_event(
    db: AsyncSession,
    event_type: str,
    payload: dict,
) -> list[WebhookDelivery]:
    """Dispatch an event to all matching active endpoints."""
    stmt = select(WebhookEndpoint).where(WebhookEndpoint.active.is_(True))
    result = await db.execute(stmt)
    endpoints = result.scalars().all()

    deliveries = []
    for ep in endpoints:
        events = ep.events
        if isinstance(events, str):
            try:
                events = json.loads(events)
            except (json.JSONDecodeError, TypeError):
                events = []

        # Check if endpoint subscribes to this event
        if "*" in events or event_type in events:
            delivery = await dispatch_webhook(db, ep, event_type, payload)
            deliveries.append(delivery)

    return deliveries
