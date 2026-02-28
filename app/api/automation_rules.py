"""Automation rules — trigger-based workflow automation engine."""

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, Text, Boolean
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import Base, get_db
from app.models import new_uuid, utcnow


# ── Models ───────────────────────────────────────────────

class AutomationRule(Base):
    """Event-driven automation rule: trigger → condition → action."""

    __tablename__ = "automation_rules"

    id = Column(String(36), primary_key=True, default=new_uuid)
    name = Column(String(300), nullable=False)
    description = Column(Text, default="")
    active = Column(Boolean, default=True)
    priority = Column(Integer, default=0)  # Higher = runs first

    # Trigger
    trigger_type = Column(String(50), nullable=False)
    # contact_created|contact_updated|tag_added|tag_removed|
    # score_changed|email_opened|email_clicked|form_submitted|
    # campaign_sent|unsubscribed|milestone_reached
    trigger_config = Column(Text, default="{}")  # JSON: {"tag_name": "vip"} etc.

    # Conditions (all must be true)
    conditions = Column(Text, default="[]")
    # JSON: [{"field": "country", "operator": "eq", "value": "US"}, ...]

    # Actions (executed in order)
    actions = Column(Text, default="[]")
    # JSON: [{"type": "send_email", "config": {"template_id": "..."}}, ...]
    # Types: send_email|add_tag|remove_tag|update_field|update_score|
    #        webhook|wait_delay|move_lifecycle|add_to_segment|
    #        remove_from_segment|notify_admin

    # Execution limits
    max_executions = Column(Integer, default=0)  # 0 = unlimited
    total_executions = Column(Integer, default=0)
    cooldown_minutes = Column(Integer, default=0)  # Min minutes between runs for same contact
    last_executed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class AutomationLog(Base):
    """Log of automation rule executions."""

    __tablename__ = "automation_logs"

    id = Column(String(36), primary_key=True, default=new_uuid)
    rule_id = Column(String(36), nullable=False, index=True)
    contact_id = Column(String(36), nullable=True)
    trigger_type = Column(String(50), nullable=False)
    trigger_data = Column(Text, default="{}")
    actions_executed = Column(Text, default="[]")  # JSON array of action results
    status = Column(String(20), default="success")  # success|failed|skipped
    error_message = Column(Text, default="")
    duration_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)


# ── Rule Engine ──────────────────────────────────────────

class RuleEngine:
    """Evaluates automation rules against events."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_matching_rules(self, trigger_type: str) -> list[AutomationRule]:
        """Find all active rules matching a trigger type."""
        result = await self.db.execute(
            select(AutomationRule).where(
                AutomationRule.active.is_(True),
                AutomationRule.trigger_type == trigger_type,
            ).order_by(AutomationRule.priority.desc())
        )
        return list(result.scalars().all())

    def check_conditions(self, rule: AutomationRule, context: dict) -> bool:
        """Evaluate rule conditions against context data."""
        try:
            conditions = json.loads(rule.conditions) if isinstance(rule.conditions, str) else rule.conditions
        except (json.JSONDecodeError, TypeError):
            conditions = []

        if not conditions:
            return True

        for cond in conditions:
            field = cond.get("field", "")
            operator = cond.get("operator", "eq")
            expected = cond.get("value")
            actual = context.get(field)

            if not self._eval_condition(actual, operator, expected):
                return False
        return True

    def _eval_condition(self, actual, operator: str, expected) -> bool:
        """Evaluate a single condition."""
        if operator == "eq":
            return actual == expected
        elif operator == "neq":
            return actual != expected
        elif operator == "gt":
            return actual is not None and actual > expected
        elif operator == "lt":
            return actual is not None and actual < expected
        elif operator == "gte":
            return actual is not None and actual >= expected
        elif operator == "lte":
            return actual is not None and actual <= expected
        elif operator == "contains":
            return expected in str(actual) if actual else False
        elif operator == "in":
            return actual in (expected if isinstance(expected, list) else [expected])
        elif operator == "is_set":
            return actual is not None and actual != ""
        elif operator == "not_set":
            return actual is None or actual == ""
        return False

    def check_execution_limits(self, rule: AutomationRule) -> bool:
        """Check if rule has hit execution limits."""
        if rule.max_executions > 0 and rule.total_executions >= rule.max_executions:
            return False
        if rule.cooldown_minutes > 0 and rule.last_executed_at:
            from datetime import timedelta
            cooldown_end = rule.last_executed_at + timedelta(minutes=rule.cooldown_minutes)
            if datetime.now(timezone.utc) < cooldown_end:
                return False
        return True

    def parse_actions(self, rule: AutomationRule) -> list[dict]:
        """Parse actions from a rule."""
        try:
            actions = json.loads(rule.actions) if isinstance(rule.actions, str) else rule.actions
        except (json.JSONDecodeError, TypeError):
            actions = []
        return actions

    async def execute_rule(
        self,
        rule: AutomationRule,
        contact_id: Optional[str] = None,
        trigger_data: Optional[dict] = None,
        context: Optional[dict] = None,
    ) -> AutomationLog:
        """Execute a rule's actions and log the result."""
        start = datetime.now(timezone.utc)
        trigger_data = trigger_data or {}
        context = context or {}

        # Check conditions
        if not self.check_conditions(rule, context):
            log = AutomationLog(
                rule_id=rule.id,
                contact_id=contact_id,
                trigger_type=rule.trigger_type,
                trigger_data=json.dumps(trigger_data),
                status="skipped",
                error_message="Conditions not met",
            )
            self.db.add(log)
            await self.db.commit()
            return log

        # Check limits
        if not self.check_execution_limits(rule):
            log = AutomationLog(
                rule_id=rule.id,
                contact_id=contact_id,
                trigger_type=rule.trigger_type,
                trigger_data=json.dumps(trigger_data),
                status="skipped",
                error_message="Execution limit reached",
            )
            self.db.add(log)
            await self.db.commit()
            return log

        # Execute actions
        actions = self.parse_actions(rule)
        action_results = []
        status = "success"
        error_msg = ""

        for action in actions:
            action_type = action.get("type", "")
            config = action.get("config", {})
            try:
                result = await self._execute_action(action_type, config, contact_id, context)
                action_results.append({"type": action_type, "status": "ok", "result": result})
            except Exception as e:
                action_results.append({"type": action_type, "status": "error", "error": str(e)})
                status = "failed"
                error_msg = str(e)

        # Update rule counters
        rule.total_executions = (rule.total_executions or 0) + 1
        rule.last_executed_at = datetime.now(timezone.utc)

        end = datetime.now(timezone.utc)
        duration = int((end - start).total_seconds() * 1000)

        log = AutomationLog(
            rule_id=rule.id,
            contact_id=contact_id,
            trigger_type=rule.trigger_type,
            trigger_data=json.dumps(trigger_data),
            actions_executed=json.dumps(action_results),
            status=status,
            error_message=error_msg,
            duration_ms=duration,
        )
        self.db.add(log)
        await self.db.commit()
        return log

    async def _execute_action(
        self, action_type: str, config: dict, contact_id: Optional[str], context: dict
    ) -> dict:
        """Execute a single action. Returns result dict."""
        if action_type == "update_field":
            return {"action": "update_field", "field": config.get("field"), "value": config.get("value")}
        elif action_type == "add_tag":
            return {"action": "add_tag", "tag": config.get("tag_name", "")}
        elif action_type == "remove_tag":
            return {"action": "remove_tag", "tag": config.get("tag_name", "")}
        elif action_type == "update_score":
            return {"action": "update_score", "points": config.get("points", 0)}
        elif action_type == "send_email":
            return {"action": "send_email", "template_id": config.get("template_id", "")}
        elif action_type == "webhook":
            return {"action": "webhook", "url": config.get("url", "")}
        elif action_type == "wait_delay":
            return {"action": "wait_delay", "minutes": config.get("minutes", 0)}
        elif action_type == "move_lifecycle":
            return {"action": "move_lifecycle", "stage": config.get("stage", "")}
        elif action_type == "notify_admin":
            return {"action": "notify_admin", "message": config.get("message", "")}
        else:
            raise ValueError(f"Unknown action type: {action_type}")

    async def fire_event(self, trigger_type: str, contact_id: Optional[str] = None, data: Optional[dict] = None):
        """Fire an event and execute all matching rules."""
        rules = await self.get_matching_rules(trigger_type)
        results = []
        for rule in rules:
            log = await self.execute_rule(rule, contact_id, data, data)
            results.append(log)
        return results

    async def get_rule_stats(self, rule_id: str) -> dict:
        """Get execution stats for a rule."""
        total = (await self.db.execute(
            select(func.count(AutomationLog.id)).where(AutomationLog.rule_id == rule_id)
        )).scalar() or 0
        success = (await self.db.execute(
            select(func.count(AutomationLog.id)).where(
                AutomationLog.rule_id == rule_id,
                AutomationLog.status == "success",
            )
        )).scalar() or 0
        failed = (await self.db.execute(
            select(func.count(AutomationLog.id)).where(
                AutomationLog.rule_id == rule_id,
                AutomationLog.status == "failed",
            )
        )).scalar() or 0
        skipped = (await self.db.execute(
            select(func.count(AutomationLog.id)).where(
                AutomationLog.rule_id == rule_id,
                AutomationLog.status == "skipped",
            )
        )).scalar() or 0

        return {
            "rule_id": rule_id,
            "total": total,
            "success": success,
            "failed": failed,
            "skipped": skipped,
            "success_rate": round(success / total * 100, 2) if total > 0 else 0.0,
        }


# ── API Router ──────────────────────────────────────────

router = APIRouter(prefix="/automation-rules", tags=["automation"])


class RuleCreate(BaseModel):
    name: str
    description: str = ""
    trigger_type: str
    trigger_config: dict = Field(default_factory=dict)
    conditions: list[dict] = Field(default_factory=list)
    actions: list[dict] = Field(default_factory=list)
    priority: int = 0
    max_executions: int = 0
    cooldown_minutes: int = 0


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    active: Optional[bool] = None
    trigger_type: Optional[str] = None
    trigger_config: Optional[dict] = None
    conditions: Optional[list[dict]] = None
    actions: Optional[list[dict]] = None
    priority: Optional[int] = None
    max_executions: Optional[int] = None
    cooldown_minutes: Optional[int] = None


class RuleOut(BaseModel):
    id: str
    name: str
    description: str
    active: bool
    trigger_type: str
    trigger_config: dict
    conditions: list
    actions: list
    priority: int
    max_executions: int
    total_executions: int
    cooldown_minutes: int
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, rule: AutomationRule):
        def safe_json(val):
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    return []
            return val or []

        return cls(
            id=rule.id,
            name=rule.name,
            description=rule.description or "",
            active=rule.active,
            trigger_type=rule.trigger_type,
            trigger_config=safe_json(rule.trigger_config) if isinstance(safe_json(rule.trigger_config), dict) else {},
            conditions=safe_json(rule.conditions),
            actions=safe_json(rule.actions),
            priority=rule.priority or 0,
            max_executions=rule.max_executions or 0,
            total_executions=rule.total_executions or 0,
            cooldown_minutes=rule.cooldown_minutes or 0,
            created_at=rule.created_at,
        )


class FireEventRequest(BaseModel):
    trigger_type: str
    contact_id: Optional[str] = None
    data: dict = Field(default_factory=dict)


@router.post("/", response_model=RuleOut, status_code=201)
async def create_rule(body: RuleCreate, db: AsyncSession = Depends(get_db)):
    rule = AutomationRule(
        name=body.name,
        description=body.description,
        trigger_type=body.trigger_type,
        trigger_config=json.dumps(body.trigger_config),
        conditions=json.dumps(body.conditions),
        actions=json.dumps(body.actions),
        priority=body.priority,
        max_executions=body.max_executions,
        cooldown_minutes=body.cooldown_minutes,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return RuleOut.from_model(rule)


@router.get("/", response_model=list[RuleOut])
async def list_rules(
    active: Optional[bool] = None,
    trigger_type: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    query = select(AutomationRule).order_by(AutomationRule.priority.desc())
    if active is not None:
        query = query.where(AutomationRule.active == active)
    if trigger_type:
        query = query.where(AutomationRule.trigger_type == trigger_type)
    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    return [RuleOut.from_model(r) for r in result.scalars().all()]


@router.get("/{rule_id}", response_model=RuleOut)
async def get_rule(rule_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AutomationRule).where(AutomationRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Rule not found")
    return RuleOut.from_model(rule)


@router.patch("/{rule_id}", response_model=RuleOut)
async def update_rule(rule_id: str, body: RuleUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AutomationRule).where(AutomationRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Rule not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        if field in ("trigger_config", "conditions", "actions"):
            setattr(rule, field, json.dumps(value))
        else:
            setattr(rule, field, value)

    await db.commit()
    await db.refresh(rule)
    return RuleOut.from_model(rule)


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(rule_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AutomationRule).where(AutomationRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Rule not found")
    await db.delete(rule)
    await db.commit()


@router.post("/fire")
async def fire_event(body: FireEventRequest, db: AsyncSession = Depends(get_db)):
    engine = RuleEngine(db)
    logs = await engine.fire_event(body.trigger_type, body.contact_id, body.data)
    return {
        "trigger_type": body.trigger_type,
        "rules_matched": len(logs),
        "results": [
            {"rule_id": log.rule_id, "status": log.status}
            for log in logs
        ],
    }


@router.get("/{rule_id}/stats")
async def get_rule_stats(rule_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AutomationRule).where(AutomationRule.id == rule_id))
    if not result.scalar_one_or_none():
        raise HTTPException(404, "Rule not found")
    engine = RuleEngine(db)
    return await engine.get_rule_stats(rule_id)


@router.get("/{rule_id}/logs")
async def get_rule_logs(
    rule_id: str,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AutomationLog).where(
            AutomationLog.rule_id == rule_id
        ).order_by(AutomationLog.created_at.desc()).limit(limit).offset(offset)
    )
    logs = result.scalars().all()
    return [
        {
            "id": log.id,
            "contact_id": log.contact_id,
            "trigger_type": log.trigger_type,
            "status": log.status,
            "duration_ms": log.duration_ms,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]
