"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.api import (
    auth, contacts, campaigns, templates, tracking, workflows, dashboard,
    ab_testing, analytics, import_export, webhooks, scoring, lifecycle,
    tags, segments, automation_rules,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create admin user if not exists
    from app.database import async_session
    from app.models import User
    from app.services.auth import hash_password
    from sqlalchemy import select

    async with async_session() as db:
        result = await db.execute(select(User).where(User.email == settings.admin_email))
        if not result.scalar_one_or_none():
            admin = User(
                email=settings.admin_email,
                hashed_password=hash_password(settings.admin_password),
                is_superuser=True,
            )
            db.add(admin)
            await db.commit()

    yield


app = FastAPI(
    title=settings.app_name,
    version="6.0.0",
    description="Lightweight marketing automation for cross-border e-commerce — with campaign scheduling, audience builder, automation rules, lead scoring, lifecycle management, A/B testing, suppression lists, webhooks, campaign analytics, email validation, and cohort analysis",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(contacts.router, prefix="/api/v1")
app.include_router(campaigns.router, prefix="/api/v1")
app.include_router(templates.router, prefix="/api/v1")
app.include_router(tracking.router, prefix="/api/v1")
app.include_router(workflows.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(ab_testing.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")
app.include_router(import_export.router, prefix="/api/v1")
app.include_router(webhooks.router, prefix="/api/v1")
app.include_router(scoring.router, prefix="/api/v1")
app.include_router(lifecycle.router, prefix="/api/v1")
app.include_router(tags.router, prefix="/api/v1")
app.include_router(segments.router, prefix="/api/v1")
app.include_router(automation_rules.router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.app_name}
