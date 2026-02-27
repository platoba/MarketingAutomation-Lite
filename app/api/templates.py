"""Email template model + Jinja2 rendering service."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from jinja2 import BaseLoader, Environment, TemplateSyntaxError
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import EmailTemplate

router = APIRouter(prefix="/templates", tags=["templates"])

_jinja_env = Environment(loader=BaseLoader(), autoescape=True)


# ── Schemas ──────────────────────────────────────────────
class TemplateCreate(BaseModel):
    name: str
    subject: str
    html_body: str
    text_body: str = ""
    variables: list[str] = Field(default_factory=list)
    category: str = "general"


class TemplateUpdate(BaseModel):
    name: str | None = None
    subject: str | None = None
    html_body: str | None = None
    text_body: str | None = None
    variables: list[str] | None = None
    category: str | None = None


class TemplateOut(TemplateCreate):
    id: UUID

    model_config = {"from_attributes": True}


class RenderRequest(BaseModel):
    variables: dict = Field(default_factory=dict)


class RenderResponse(BaseModel):
    subject: str
    html_body: str
    text_body: str


# ── Helpers ──────────────────────────────────────────────
def render_template_string(template_str: str, variables: dict) -> str:
    """Render a Jinja2 template string with given variables."""
    try:
        tpl = _jinja_env.from_string(template_str)
        return tpl.render(**variables)
    except TemplateSyntaxError as e:
        raise ValueError(f"Template syntax error: {e}") from e


# ── CRUD ─────────────────────────────────────────────────
@router.get("/", response_model=list[TemplateOut])
async def list_templates(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(EmailTemplate)
    if category:
        stmt = stmt.where(EmailTemplate.category == category)
    stmt = stmt.order_by(EmailTemplate.name).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/", response_model=TemplateOut, status_code=201)
async def create_template(data: TemplateCreate, db: AsyncSession = Depends(get_db)):
    tpl = EmailTemplate(**data.model_dump())
    db.add(tpl)
    await db.commit()
    await db.refresh(tpl)
    return tpl


@router.get("/{template_id}", response_model=TemplateOut)
async def get_template(template_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(EmailTemplate).where(EmailTemplate.id == template_id))
    tpl = result.scalar_one_or_none()
    if not tpl:
        raise HTTPException(404, "Template not found")
    return tpl


@router.patch("/{template_id}", response_model=TemplateOut)
async def update_template(template_id: UUID, data: TemplateUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(EmailTemplate).where(EmailTemplate.id == template_id))
    tpl = result.scalar_one_or_none()
    if not tpl:
        raise HTTPException(404, "Template not found")
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(tpl, key, val)
    await db.commit()
    await db.refresh(tpl)
    return tpl


@router.delete("/{template_id}", status_code=204)
async def delete_template(template_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(EmailTemplate).where(EmailTemplate.id == template_id))
    tpl = result.scalar_one_or_none()
    if not tpl:
        raise HTTPException(404, "Template not found")
    await db.delete(tpl)
    await db.commit()


@router.post("/{template_id}/render", response_model=RenderResponse)
async def render_template(
    template_id: UUID,
    body: RenderRequest,
    db: AsyncSession = Depends(get_db),
):
    """Preview a template with sample variables."""
    result = await db.execute(select(EmailTemplate).where(EmailTemplate.id == template_id))
    tpl = result.scalar_one_or_none()
    if not tpl:
        raise HTTPException(404, "Template not found")
    try:
        return RenderResponse(
            subject=render_template_string(tpl.subject, body.variables),
            html_body=render_template_string(tpl.html_body, body.variables),
            text_body=render_template_string(tpl.text_body, body.variables) if tpl.text_body else "",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
