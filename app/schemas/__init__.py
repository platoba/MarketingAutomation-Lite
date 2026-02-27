"""Pydantic schemas for API request/response."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


# ── Contact ──────────────────────────────────────────────
class ContactBase(BaseModel):
    email: EmailStr
    first_name: str = ""
    last_name: str = ""
    phone: str = ""
    country: str = ""
    language: str = "en"
    custom_fields: dict = Field(default_factory=dict)
    subscribed: bool = True


class ContactCreate(ContactBase):
    pass


class ContactUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    country: Optional[str] = None
    language: Optional[str] = None
    custom_fields: Optional[dict] = None
    subscribed: Optional[bool] = None


class ContactOut(ContactBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Tag ──────────────────────────────────────────────────
class TagCreate(BaseModel):
    name: str
    color: str = "#3B82F6"


class TagOut(TagCreate):
    id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Segment ──────────────────────────────────────────────
class SegmentCreate(BaseModel):
    name: str
    description: str = ""
    rules: list = Field(default_factory=list)


class SegmentOut(SegmentCreate):
    id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Campaign ─────────────────────────────────────────────
class CampaignCreate(BaseModel):
    name: str
    subject: str
    from_name: str = ""
    from_email: str = ""
    html_body: str = ""
    text_body: str = ""
    segment_id: Optional[UUID] = None
    scheduled_at: Optional[datetime] = None


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    subject: Optional[str] = None
    html_body: Optional[str] = None
    text_body: Optional[str] = None
    status: Optional[str] = None
    scheduled_at: Optional[datetime] = None


class CampaignOut(BaseModel):
    id: UUID
    name: str
    subject: str
    from_name: str
    from_email: str
    status: str
    total_sent: int
    total_opened: int
    total_clicked: int
    total_bounced: int
    scheduled_at: Optional[datetime]
    sent_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Workflow ─────────────────────────────────────────────
class WorkflowCreate(BaseModel):
    name: str
    trigger_type: str = "manual"
    trigger_config: dict = Field(default_factory=dict)
    steps: list = Field(default_factory=list)
    active: bool = False


class WorkflowOut(WorkflowCreate):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Auth ─────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Stats ────────────────────────────────────────────────
class DashboardStats(BaseModel):
    total_contacts: int
    subscribed_contacts: int
    total_campaigns: int
    campaigns_sent: int
    total_emails_sent: int
    avg_open_rate: float
    avg_click_rate: float
