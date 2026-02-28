"""Pydantic schemas for API request/response."""

import json
from datetime import datetime
from typing import Optional

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
    tag_ids: list[str] = Field(default_factory=list)


class ContactUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    country: Optional[str] = None
    language: Optional[str] = None
    custom_fields: Optional[dict] = None
    subscribed: Optional[bool] = None


class TagBrief(BaseModel):
    id: str
    name: str
    color: str

    model_config = {"from_attributes": True}


class SegmentBrief(BaseModel):
    id: str
    name: str

    model_config = {"from_attributes": True}


class ContactOut(BaseModel):
    id: str
    email: str
    first_name: str
    last_name: str
    phone: str
    country: str
    language: str
    custom_fields: dict
    subscribed: bool
    tags: list[TagBrief] = Field(default_factory=list)
    segments: list[SegmentBrief] = Field(default_factory=list)
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, contact):
        custom = contact.custom_fields
        if isinstance(custom, str):
            try:
                custom = json.loads(custom)
            except (json.JSONDecodeError, TypeError):
                custom = {}
        return cls(
            id=contact.id,
            email=contact.email,
            first_name=contact.first_name or "",
            last_name=contact.last_name or "",
            phone=contact.phone or "",
            country=contact.country or "",
            language=contact.language or "en",
            custom_fields=custom,
            subscribed=contact.subscribed,
            tags=[TagBrief.model_validate(t) for t in (contact.tags or [])],
            segments=[SegmentBrief.model_validate(s) for s in (contact.segments or [])],
            created_at=contact.created_at,
            updated_at=contact.updated_at,
        )


# ── Tag ──────────────────────────────────────────────────
class TagCreate(BaseModel):
    name: str
    color: str = "#3B82F6"


class TagOut(TagCreate):
    id: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Segment ──────────────────────────────────────────────
class SegmentCreate(BaseModel):
    name: str
    description: str = ""
    rules: list = Field(default_factory=list)


class SegmentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    rules: Optional[list] = None


class SegmentOut(BaseModel):
    id: str
    name: str
    description: str
    rules: list
    contact_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, segment):
        rules = segment.rules
        if isinstance(rules, str):
            try:
                rules = json.loads(rules)
            except (json.JSONDecodeError, TypeError):
                rules = []
        return cls(
            id=segment.id,
            name=segment.name,
            description=segment.description or "",
            rules=rules,
            contact_count=len(segment.contacts) if segment.contacts else 0,
            created_at=segment.created_at,
        )


# ── Campaign ─────────────────────────────────────────────
class CampaignCreate(BaseModel):
    name: str
    subject: str
    from_name: str = ""
    from_email: str = ""
    html_body: str = ""
    text_body: str = ""
    segment_id: Optional[str] = None
    scheduled_at: Optional[datetime] = None


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    subject: Optional[str] = None
    html_body: Optional[str] = None
    text_body: Optional[str] = None
    status: Optional[str] = None
    scheduled_at: Optional[datetime] = None


class CampaignOut(BaseModel):
    id: str
    name: str
    subject: str
    from_name: str
    from_email: str
    status: str
    total_sent: int
    total_opened: int
    total_clicked: int
    total_bounced: int
    total_unsubscribed: int
    scheduled_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Workflow ─────────────────────────────────────────────
class WorkflowCreate(BaseModel):
    name: str
    trigger_type: str = "manual"
    trigger_config: dict = Field(default_factory=dict)
    steps: list = Field(default_factory=list)
    active: bool = False


class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    trigger_type: Optional[str] = None
    trigger_config: Optional[dict] = None
    steps: Optional[list] = None
    active: Optional[bool] = None


class WorkflowOut(BaseModel):
    id: str
    name: str
    trigger_type: str
    trigger_config: dict
    steps: list
    active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, workflow):
        tc = workflow.trigger_config
        if isinstance(tc, str):
            try:
                tc = json.loads(tc)
            except (json.JSONDecodeError, TypeError):
                tc = {}
        steps = workflow.steps
        if isinstance(steps, str):
            try:
                steps = json.loads(steps)
            except (json.JSONDecodeError, TypeError):
                steps = []
        return cls(
            id=workflow.id,
            name=workflow.name,
            trigger_type=workflow.trigger_type or "manual",
            trigger_config=tc,
            steps=steps,
            active=workflow.active,
            created_at=workflow.created_at,
            updated_at=workflow.updated_at,
        )


class WorkflowTriggerRequest(BaseModel):
    contact_id: Optional[str] = None
    context: dict = Field(default_factory=dict)


class WorkflowLogOut(BaseModel):
    id: str
    workflow_id: str
    contact_id: Optional[str]
    step_index: int
    status: str
    result: dict
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, log):
        result = log.result
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                result = {}
        return cls(
            id=log.id,
            workflow_id=log.workflow_id,
            contact_id=log.contact_id,
            step_index=log.step_index,
            status=log.status,
            result=result,
            created_at=log.created_at,
        )


# ── Auth ─────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Template ─────────────────────────────────────────────
class TemplateCreate(BaseModel):
    name: str
    subject: str
    html_body: str
    text_body: str = ""
    variables: list[str] = Field(default_factory=list)
    category: str = "general"


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    subject: Optional[str] = None
    html_body: Optional[str] = None
    text_body: Optional[str] = None
    variables: Optional[list[str]] = None
    category: Optional[str] = None


class TemplateOut(BaseModel):
    id: str
    name: str
    subject: str
    html_body: str
    text_body: str
    variables: list
    category: str

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, tpl):
        variables = tpl.variables
        if isinstance(variables, str):
            try:
                variables = json.loads(variables)
            except (json.JSONDecodeError, TypeError):
                variables = []
        return cls(
            id=tpl.id,
            name=tpl.name,
            subject=tpl.subject,
            html_body=tpl.html_body or "",
            text_body=tpl.text_body or "",
            variables=variables,
            category=tpl.category or "general",
        )


class RenderRequest(BaseModel):
    variables: dict = Field(default_factory=dict)


class RenderResponse(BaseModel):
    subject: str
    html_body: str
    text_body: str


# ── Dashboard Stats ─────────────────────────────────────
class DashboardStats(BaseModel):
    total_contacts: int
    subscribed_contacts: int
    unsubscribed_contacts: int
    total_campaigns: int
    campaigns_sent: int
    campaigns_draft: int
    total_emails_sent: int
    avg_open_rate: float
    avg_click_rate: float
    total_workflows: int
    active_workflows: int


class FunnelStage(BaseModel):
    stage: str
    count: int
    percentage: float


class FunnelAnalysis(BaseModel):
    campaign_id: Optional[str] = None
    stages: list[FunnelStage]


class ContactGrowth(BaseModel):
    date: str
    count: int


class CampaignPerformance(BaseModel):
    campaign_id: str
    campaign_name: str
    sent: int
    opened: int
    clicked: int
    bounced: int
    open_rate: float
    click_rate: float
