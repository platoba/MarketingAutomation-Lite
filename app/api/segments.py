"""Segment CRUD API with contact membership management."""

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Contact, Segment
from app.schemas import ContactOut, SegmentCreate, SegmentOut, SegmentUpdate

router = APIRouter(prefix="/segments", tags=["segments"])


@router.get("/", response_model=list[SegmentOut])
async def list_segments(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Segment)
        .options(selectinload(Segment.contacts))
        .order_by(Segment.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    segments = result.scalars().unique().all()
    return [SegmentOut.from_model(s) for s in segments]


@router.post("/", response_model=SegmentOut, status_code=201)
async def create_segment(data: SegmentCreate, db: AsyncSession = Depends(get_db)):
    segment = Segment(
        name=data.name,
        description=data.description,
        rules=json.dumps(data.rules),
    )
    db.add(segment)
    await db.commit()

    result = await db.execute(
        select(Segment).options(selectinload(Segment.contacts)).where(Segment.id == segment.id)
    )
    segment = result.scalar_one()
    return SegmentOut.from_model(segment)


@router.get("/{segment_id}", response_model=SegmentOut)
async def get_segment(segment_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Segment).options(selectinload(Segment.contacts)).where(Segment.id == segment_id)
    )
    segment = result.scalar_one_or_none()
    if not segment:
        raise HTTPException(404, "Segment not found")
    return SegmentOut.from_model(segment)


@router.patch("/{segment_id}", response_model=SegmentOut)
async def update_segment(segment_id: str, data: SegmentUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Segment).options(selectinload(Segment.contacts)).where(Segment.id == segment_id)
    )
    segment = result.scalar_one_or_none()
    if not segment:
        raise HTTPException(404, "Segment not found")
    for key, val in data.model_dump(exclude_unset=True).items():
        if key == "rules" and val is not None:
            setattr(segment, key, json.dumps(val))
        else:
            setattr(segment, key, val)
    await db.commit()
    await db.refresh(segment)
    return SegmentOut.from_model(segment)


@router.delete("/{segment_id}", status_code=204)
async def delete_segment(segment_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Segment).where(Segment.id == segment_id))
    segment = result.scalar_one_or_none()
    if not segment:
        raise HTTPException(404, "Segment not found")
    await db.delete(segment)
    await db.commit()


@router.post("/{segment_id}/contacts/{contact_id}", status_code=200)
async def add_contact_to_segment(segment_id: str, contact_id: str, db: AsyncSession = Depends(get_db)):
    """Add a contact to a segment."""
    result = await db.execute(
        select(Segment).options(selectinload(Segment.contacts)).where(Segment.id == segment_id)
    )
    segment = result.scalar_one_or_none()
    if not segment:
        raise HTTPException(404, "Segment not found")

    contact_result = await db.execute(select(Contact).where(Contact.id == contact_id))
    contact = contact_result.scalar_one_or_none()
    if not contact:
        raise HTTPException(404, "Contact not found")

    if contact not in segment.contacts:
        segment.contacts.append(contact)
        await db.commit()

    return {"message": "Contact added to segment"}


@router.delete("/{segment_id}/contacts/{contact_id}", status_code=200)
async def remove_contact_from_segment(segment_id: str, contact_id: str, db: AsyncSession = Depends(get_db)):
    """Remove a contact from a segment."""
    result = await db.execute(
        select(Segment).options(selectinload(Segment.contacts)).where(Segment.id == segment_id)
    )
    segment = result.scalar_one_or_none()
    if not segment:
        raise HTTPException(404, "Segment not found")

    contact_result = await db.execute(select(Contact).where(Contact.id == contact_id))
    contact = contact_result.scalar_one_or_none()
    if not contact:
        raise HTTPException(404, "Contact not found")

    if contact in segment.contacts:
        segment.contacts.remove(contact)
        await db.commit()

    return {"message": "Contact removed from segment"}


@router.get("/{segment_id}/contacts", response_model=list[ContactOut])
async def list_segment_contacts(
    segment_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List all contacts in a segment."""
    result = await db.execute(
        select(Segment).options(selectinload(Segment.contacts)).where(Segment.id == segment_id)
    )
    segment = result.scalar_one_or_none()
    if not segment:
        raise HTTPException(404, "Segment not found")

    contacts = segment.contacts[skip : skip + limit]
    return [ContactOut.from_model(c) for c in contacts]
