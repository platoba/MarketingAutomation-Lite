"""Workflow CRUD + execution API."""

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Contact, Workflow, WorkflowLog
from app.schemas import WorkflowCreate, WorkflowLogOut, WorkflowOut, WorkflowTriggerRequest, WorkflowUpdate
from app.services.workflow_engine import execute_workflow

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("/", response_model=list[WorkflowOut])
async def list_workflows(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    active: bool | None = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Workflow)
    if active is not None:
        stmt = stmt.where(Workflow.active == active)
    stmt = stmt.order_by(Workflow.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    workflows = result.scalars().all()
    return [WorkflowOut.from_model(w) for w in workflows]


@router.post("/", response_model=WorkflowOut, status_code=201)
async def create_workflow(data: WorkflowCreate, db: AsyncSession = Depends(get_db)):
    workflow = Workflow(
        name=data.name,
        trigger_type=data.trigger_type,
        trigger_config=json.dumps(data.trigger_config),
        steps=json.dumps(data.steps),
        active=data.active,
    )
    db.add(workflow)
    await db.commit()
    await db.refresh(workflow)
    return WorkflowOut.from_model(workflow)


@router.get("/{workflow_id}", response_model=WorkflowOut)
async def get_workflow(workflow_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(404, "Workflow not found")
    return WorkflowOut.from_model(workflow)


@router.patch("/{workflow_id}", response_model=WorkflowOut)
async def update_workflow(workflow_id: str, data: WorkflowUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(404, "Workflow not found")
    for key, val in data.model_dump(exclude_unset=True).items():
        if key in ("trigger_config", "steps") and val is not None:
            setattr(workflow, key, json.dumps(val))
        else:
            setattr(workflow, key, val)
    await db.commit()
    await db.refresh(workflow)
    return WorkflowOut.from_model(workflow)


@router.patch("/{workflow_id}/activate", response_model=WorkflowOut)
async def activate_workflow(workflow_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(404, "Workflow not found")
    workflow.active = True
    await db.commit()
    await db.refresh(workflow)
    return WorkflowOut.from_model(workflow)


@router.patch("/{workflow_id}/deactivate", response_model=WorkflowOut)
async def deactivate_workflow(workflow_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(404, "Workflow not found")
    workflow.active = False
    await db.commit()
    await db.refresh(workflow)
    return WorkflowOut.from_model(workflow)


@router.post("/{workflow_id}/trigger", status_code=200)
async def trigger_workflow(
    workflow_id: str,
    body: WorkflowTriggerRequest,
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger a workflow execution."""
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(404, "Workflow not found")

    contact = None
    if body.contact_id:
        contact_result = await db.execute(
            select(Contact).options(selectinload(Contact.tags)).where(Contact.id == body.contact_id)
        )
        contact = contact_result.scalar_one_or_none()
        if not contact:
            raise HTTPException(404, "Contact not found")

    results = await execute_workflow(workflow, contact, body.context, db)
    return {
        "workflow_id": workflow_id,
        "contact_id": body.contact_id,
        "steps_executed": len(results),
        "results": results,
    }


@router.get("/{workflow_id}/logs", response_model=list[WorkflowLogOut])
async def get_workflow_logs(
    workflow_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Get execution logs for a workflow."""
    stmt = (
        select(WorkflowLog)
        .where(WorkflowLog.workflow_id == workflow_id)
        .order_by(WorkflowLog.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    logs = result.scalars().all()
    return [WorkflowLogOut.from_model(log) for log in logs]


@router.delete("/{workflow_id}", status_code=204)
async def delete_workflow(workflow_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(404, "Workflow not found")
    # Delete associated logs
    logs_result = await db.execute(select(WorkflowLog).where(WorkflowLog.workflow_id == workflow_id))
    for log in logs_result.scalars().all():
        await db.delete(log)
    await db.delete(workflow)
    await db.commit()
