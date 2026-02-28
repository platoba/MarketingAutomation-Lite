"""Contact CRUD API with CSV export, tag/segment assignment."""

import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Contact, Tag, contact_tags
from app.schemas import ContactCreate, ContactOut, ContactUpdate

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get("/", response_model=list[ContactOut])
async def list_contacts(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    subscribed: bool | None = None,
    tag: str | None = None,
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Contact).options(selectinload(Contact.tags), selectinload(Contact.segments))
    if subscribed is not None:
        stmt = stmt.where(Contact.subscribed == subscribed)
    if q:
        stmt = stmt.where(
            Contact.email.ilike(f"%{q}%")
            | Contact.first_name.ilike(f"%{q}%")
            | Contact.last_name.ilike(f"%{q}%")
        )
    if tag:
        stmt = stmt.join(contact_tags).join(Tag).where(Tag.name == tag)
    stmt = stmt.order_by(Contact.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    contacts = result.scalars().unique().all()
    return [ContactOut.from_model(c) for c in contacts]


@router.get("/count")
async def count_contacts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(func.count(Contact.id)))
    return {"count": result.scalar()}


@router.post("/", response_model=ContactOut, status_code=201)
async def create_contact(data: ContactCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Contact).where(Contact.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Contact with this email already exists")

    contact = Contact(
        email=data.email,
        first_name=data.first_name,
        last_name=data.last_name,
        phone=data.phone,
        country=data.country,
        language=data.language,
        custom_fields=json.dumps(data.custom_fields),
        subscribed=data.subscribed,
    )

    # Attach tags if provided
    if data.tag_ids:
        for tid in data.tag_ids:
            result = await db.execute(select(Tag).where(Tag.id == tid))
            tag = result.scalar_one_or_none()
            if tag:
                contact.tags.append(tag)

    db.add(contact)
    await db.commit()

    # Reload with relationships
    result = await db.execute(
        select(Contact)
        .options(selectinload(Contact.tags), selectinload(Contact.segments))
        .where(Contact.id == contact.id)
    )
    contact = result.scalar_one()
    return ContactOut.from_model(contact)


@router.get("/{contact_id}", response_model=ContactOut)
async def get_contact(contact_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Contact)
        .options(selectinload(Contact.tags), selectinload(Contact.segments))
        .where(Contact.id == contact_id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(404, "Contact not found")
    return ContactOut.from_model(contact)


@router.patch("/{contact_id}", response_model=ContactOut)
async def update_contact(contact_id: str, data: ContactUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Contact)
        .options(selectinload(Contact.tags), selectinload(Contact.segments))
        .where(Contact.id == contact_id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(404, "Contact not found")
    for key, val in data.model_dump(exclude_unset=True).items():
        if key == "custom_fields" and val is not None:
            setattr(contact, key, json.dumps(val))
        else:
            setattr(contact, key, val)
    await db.commit()
    await db.refresh(contact)
    return ContactOut.from_model(contact)


@router.delete("/{contact_id}", status_code=204)
async def delete_contact(contact_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Contact).where(Contact.id == contact_id))
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(404, "Contact not found")
    await db.delete(contact)
    await db.commit()


@router.post("/{contact_id}/tags/{tag_id}", status_code=200)
async def add_tag_to_contact(contact_id: str, tag_id: str, db: AsyncSession = Depends(get_db)):
    """Add a tag to a contact."""
    result = await db.execute(
        select(Contact).options(selectinload(Contact.tags)).where(Contact.id == contact_id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(404, "Contact not found")

    tag_result = await db.execute(select(Tag).where(Tag.id == tag_id))
    tag = tag_result.scalar_one_or_none()
    if not tag:
        raise HTTPException(404, "Tag not found")

    if tag not in contact.tags:
        contact.tags.append(tag)
        await db.commit()

    return {"message": "Tag added"}


@router.delete("/{contact_id}/tags/{tag_id}", status_code=200)
async def remove_tag_from_contact(contact_id: str, tag_id: str, db: AsyncSession = Depends(get_db)):
    """Remove a tag from a contact."""
    result = await db.execute(
        select(Contact).options(selectinload(Contact.tags)).where(Contact.id == contact_id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(404, "Contact not found")

    tag_result = await db.execute(select(Tag).where(Tag.id == tag_id))
    tag = tag_result.scalar_one_or_none()
    if not tag:
        raise HTTPException(404, "Tag not found")

    if tag in contact.tags:
        contact.tags.remove(tag)
        await db.commit()

    return {"message": "Tag removed"}


@router.post("/import", status_code=201)
async def import_contacts(contacts: list[ContactCreate], db: AsyncSession = Depends(get_db)):
    """Bulk import contacts."""
    created, skipped = 0, 0
    for c in contacts:
        existing = await db.execute(select(Contact).where(Contact.email == c.email))
        if existing.scalar_one_or_none():
            skipped += 1
            continue
        db.add(Contact(
            email=c.email,
            first_name=c.first_name,
            last_name=c.last_name,
            phone=c.phone,
            country=c.country,
            language=c.language,
            custom_fields=json.dumps(c.custom_fields),
            subscribed=c.subscribed,
        ))
        created += 1
    await db.commit()
    return {"created": created, "skipped": skipped}


@router.get("/export/csv")
async def export_contacts_csv(
    subscribed: bool | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Export all contacts as CSV."""
    stmt = select(Contact)
    if subscribed is not None:
        stmt = stmt.where(Contact.subscribed == subscribed)
    stmt = stmt.order_by(Contact.created_at.desc())
    result = await db.execute(stmt)
    contacts_list = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["email", "first_name", "last_name", "phone", "country", "language", "subscribed", "created_at"])
    for c in contacts_list:
        writer.writerow([
            c.email, c.first_name, c.last_name, c.phone,
            c.country, c.language, c.subscribed,
            c.created_at.isoformat() if c.created_at else "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=contacts.csv"},
    )
