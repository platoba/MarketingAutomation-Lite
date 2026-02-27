"""Contact CRUD API."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Contact
from app.schemas import ContactCreate, ContactOut, ContactUpdate

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get("/", response_model=list[ContactOut])
async def list_contacts(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    subscribed: bool | None = None,
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Contact)
    if subscribed is not None:
        stmt = stmt.where(Contact.subscribed == subscribed)
    if q:
        stmt = stmt.where(
            Contact.email.ilike(f"%{q}%")
            | Contact.first_name.ilike(f"%{q}%")
            | Contact.last_name.ilike(f"%{q}%")
        )
    stmt = stmt.order_by(Contact.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/count")
async def count_contacts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(func.count(Contact.id)))
    return {"count": result.scalar()}


@router.post("/", response_model=ContactOut, status_code=201)
async def create_contact(data: ContactCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Contact).where(Contact.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Contact with this email already exists")
    contact = Contact(**data.model_dump())
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact


@router.get("/{contact_id}", response_model=ContactOut)
async def get_contact(contact_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Contact).where(Contact.id == contact_id))
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(404, "Contact not found")
    return contact


@router.patch("/{contact_id}", response_model=ContactOut)
async def update_contact(contact_id: UUID, data: ContactUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Contact).where(Contact.id == contact_id))
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(404, "Contact not found")
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(contact, key, val)
    await db.commit()
    await db.refresh(contact)
    return contact


@router.delete("/{contact_id}", status_code=204)
async def delete_contact(contact_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Contact).where(Contact.id == contact_id))
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(404, "Contact not found")
    await db.delete(contact)
    await db.commit()


@router.post("/import", status_code=201)
async def import_contacts(contacts: list[ContactCreate], db: AsyncSession = Depends(get_db)):
    """Bulk import contacts."""
    created, skipped = 0, 0
    for c in contacts:
        existing = await db.execute(select(Contact).where(Contact.email == c.email))
        if existing.scalar_one_or_none():
            skipped += 1
            continue
        db.add(Contact(**c.model_dump()))
        created += 1
    await db.commit()
    return {"created": created, "skipped": skipped}
