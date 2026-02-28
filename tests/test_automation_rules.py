"""Tests for automation rules API and rule engine."""

import json
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from app.api.automation_rules import (
    AutomationLog,
    AutomationRule,
    RuleCreate,
    RuleEngine,
    RuleOut,
    RuleUpdate,
)


# ── Model tests ──────────────────────────────────────────

class TestAutomationRuleModel:
    def test_defaults(self):
        r = AutomationRule(name="Test", trigger_type="contact_created")
        assert r.active is True
        assert r.priority == 0
        assert r.max_executions == 0
        assert r.total_executions == 0
        assert r.cooldown_minutes == 0

    def test_custom_values(self):
        r = AutomationRule(
            name="VIP", trigger_type="score_changed",
            priority=10, max_executions=100,
        )
        assert r.priority == 10
        assert r.max_executions == 100


class TestAutomationLogModel:
    def test_defaults(self):
        log = AutomationLog(
            rule_id="r1", trigger_type="contact_created",
        )
        assert log.status == "success"
        assert log.duration_ms == 0
        assert log.error_message == ""


# ── Rule Engine tests ────────────────────────────────────

class TestRuleEngine:
    @pytest_asyncio.fixture
    async def db(self):
        from app.database import engine, Base, async_session
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_session() as session:
            yield session
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    @pytest.mark.asyncio
    async def test_get_matching_rules(self, db):
        rule = AutomationRule(
            name="Welcome", trigger_type="contact_created",
            actions=json.dumps([{"type": "send_email", "config": {"template_id": "t1"}}]),
        )
        db.add(rule)
        await db.commit()

        engine = RuleEngine(db)
        matches = await engine.get_matching_rules("contact_created")
        assert len(matches) == 1
        assert matches[0].name == "Welcome"

    @pytest.mark.asyncio
    async def test_no_matching_rules(self, db):
        engine = RuleEngine(db)
        matches = await engine.get_matching_rules("nonexistent")
        assert len(matches) == 0

    @pytest.mark.asyncio
    async def test_inactive_rules_excluded(self, db):
        rule = AutomationRule(
            name="Inactive", trigger_type="contact_created", active=False,
        )
        db.add(rule)
        await db.commit()

        engine = RuleEngine(db)
        matches = await engine.get_matching_rules("contact_created")
        assert len(matches) == 0

    def test_check_conditions_empty(self):
        rule = AutomationRule(
            name="No Cond", trigger_type="test", conditions="[]",
        )
        engine = RuleEngine.__new__(RuleEngine)
        assert engine.check_conditions(rule, {}) is True

    def test_check_conditions_eq(self):
        rule = AutomationRule(
            name="EQ", trigger_type="test",
            conditions=json.dumps([{"field": "country", "operator": "eq", "value": "US"}]),
        )
        engine = RuleEngine.__new__(RuleEngine)
        assert engine.check_conditions(rule, {"country": "US"}) is True
        assert engine.check_conditions(rule, {"country": "UK"}) is False

    def test_check_conditions_gt(self):
        rule = AutomationRule(
            name="GT", trigger_type="test",
            conditions=json.dumps([{"field": "score", "operator": "gt", "value": 50}]),
        )
        engine = RuleEngine.__new__(RuleEngine)
        assert engine.check_conditions(rule, {"score": 100}) is True
        assert engine.check_conditions(rule, {"score": 30}) is False

    def test_check_conditions_contains(self):
        rule = AutomationRule(
            name="Contains", trigger_type="test",
            conditions=json.dumps([{"field": "email", "operator": "contains", "value": "gmail"}]),
        )
        engine = RuleEngine.__new__(RuleEngine)
        assert engine.check_conditions(rule, {"email": "user@gmail.com"}) is True
        assert engine.check_conditions(rule, {"email": "user@yahoo.com"}) is False

    def test_check_conditions_in(self):
        rule = AutomationRule(
            name="In", trigger_type="test",
            conditions=json.dumps([{"field": "tag", "operator": "in", "value": ["vip", "premium"]}]),
        )
        engine = RuleEngine.__new__(RuleEngine)
        assert engine.check_conditions(rule, {"tag": "vip"}) is True
        assert engine.check_conditions(rule, {"tag": "basic"}) is False

    def test_check_conditions_is_set(self):
        rule = AutomationRule(
            name="IsSet", trigger_type="test",
            conditions=json.dumps([{"field": "phone", "operator": "is_set"}]),
        )
        engine = RuleEngine.__new__(RuleEngine)
        assert engine.check_conditions(rule, {"phone": "123"}) is True
        assert engine.check_conditions(rule, {"phone": ""}) is False
        assert engine.check_conditions(rule, {"phone": None}) is False

    def test_check_conditions_multiple(self):
        rule = AutomationRule(
            name="Multi", trigger_type="test",
            conditions=json.dumps([
                {"field": "country", "operator": "eq", "value": "US"},
                {"field": "score", "operator": "gte", "value": 50},
            ]),
        )
        engine = RuleEngine.__new__(RuleEngine)
        assert engine.check_conditions(rule, {"country": "US", "score": 60}) is True
        assert engine.check_conditions(rule, {"country": "US", "score": 30}) is False

    def test_execution_limit_not_reached(self):
        rule = AutomationRule(
            name="Limit", trigger_type="test",
            max_executions=10, total_executions=5,
        )
        engine = RuleEngine.__new__(RuleEngine)
        assert engine.check_execution_limits(rule) is True

    def test_execution_limit_reached(self):
        rule = AutomationRule(
            name="Limit", trigger_type="test",
            max_executions=10, total_executions=10,
        )
        engine = RuleEngine.__new__(RuleEngine)
        assert engine.check_execution_limits(rule) is False

    def test_execution_limit_unlimited(self):
        rule = AutomationRule(
            name="Unlimited", trigger_type="test",
            max_executions=0, total_executions=9999,
        )
        engine = RuleEngine.__new__(RuleEngine)
        assert engine.check_execution_limits(rule) is True

    def test_cooldown_active(self):
        rule = AutomationRule(
            name="Cool", trigger_type="test",
            cooldown_minutes=60,
            last_executed_at=datetime.now(timezone.utc) - timedelta(minutes=30),
        )
        engine = RuleEngine.__new__(RuleEngine)
        assert engine.check_execution_limits(rule) is False

    def test_cooldown_expired(self):
        rule = AutomationRule(
            name="Cool", trigger_type="test",
            cooldown_minutes=60,
            last_executed_at=datetime.now(timezone.utc) - timedelta(minutes=90),
        )
        engine = RuleEngine.__new__(RuleEngine)
        assert engine.check_execution_limits(rule) is True

    def test_parse_actions(self):
        rule = AutomationRule(
            name="Actions", trigger_type="test",
            actions=json.dumps([
                {"type": "add_tag", "config": {"tag_name": "vip"}},
                {"type": "send_email", "config": {"template_id": "t1"}},
            ]),
        )
        engine = RuleEngine.__new__(RuleEngine)
        actions = engine.parse_actions(rule)
        assert len(actions) == 2
        assert actions[0]["type"] == "add_tag"

    @pytest.mark.asyncio
    async def test_execute_rule_success(self, db):
        rule = AutomationRule(
            name="Exec", trigger_type="contact_created",
            actions=json.dumps([{"type": "add_tag", "config": {"tag_name": "new"}}]),
        )
        db.add(rule)
        await db.commit()

        engine = RuleEngine(db)
        log = await engine.execute_rule(rule, "ct1", {})
        assert log.status == "success"
        assert rule.total_executions == 1

    @pytest.mark.asyncio
    async def test_execute_rule_conditions_not_met(self, db):
        rule = AutomationRule(
            name="Cond", trigger_type="test",
            conditions=json.dumps([{"field": "country", "operator": "eq", "value": "US"}]),
            actions=json.dumps([{"type": "add_tag", "config": {"tag_name": "x"}}]),
        )
        db.add(rule)
        await db.commit()

        engine = RuleEngine(db)
        log = await engine.execute_rule(rule, "ct1", context={"country": "UK"})
        assert log.status == "skipped"

    @pytest.mark.asyncio
    async def test_execute_unknown_action(self, db):
        rule = AutomationRule(
            name="Unknown", trigger_type="test",
            actions=json.dumps([{"type": "unknown_action", "config": {}}]),
        )
        db.add(rule)
        await db.commit()

        engine = RuleEngine(db)
        log = await engine.execute_rule(rule, "ct1")
        assert log.status == "failed"

    @pytest.mark.asyncio
    async def test_fire_event(self, db):
        rule1 = AutomationRule(
            name="R1", trigger_type="contact_created",
            actions=json.dumps([{"type": "add_tag", "config": {"tag_name": "new"}}]),
        )
        rule2 = AutomationRule(
            name="R2", trigger_type="contact_created",
            actions=json.dumps([{"type": "send_email", "config": {"template_id": "t1"}}]),
        )
        db.add_all([rule1, rule2])
        await db.commit()

        engine = RuleEngine(db)
        logs = await engine.fire_event("contact_created", "ct1")
        assert len(logs) == 2

    @pytest.mark.asyncio
    async def test_get_rule_stats(self, db):
        rule = AutomationRule(
            name="Stats", trigger_type="test",
            actions=json.dumps([{"type": "add_tag", "config": {"tag_name": "x"}}]),
        )
        db.add(rule)
        await db.commit()

        engine = RuleEngine(db)
        await engine.execute_rule(rule, "ct1")
        await engine.execute_rule(rule, "ct2")
        stats = await engine.get_rule_stats(rule.id)
        assert stats["total"] == 2
        assert stats["success"] == 2


# ── Schema tests ─────────────────────────────────────────

class TestRuleSchemas:
    def test_rule_create(self):
        rc = RuleCreate(
            name="New Rule",
            trigger_type="contact_created",
            actions=[{"type": "add_tag", "config": {"tag_name": "new"}}],
        )
        assert rc.name == "New Rule"
        assert rc.priority == 0

    def test_rule_update(self):
        ru = RuleUpdate(name="Updated", active=False)
        assert ru.name == "Updated"
        assert ru.active is False


# ── API endpoint tests ───────────────────────────────────

@pytest.mark.asyncio
async def test_create_rule_endpoint(client):
    resp = await client.post("/api/v1/automation-rules/", json={
        "name": "Welcome Email",
        "trigger_type": "contact_created",
        "actions": [{"type": "send_email", "config": {"template_id": "t1"}}],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Welcome Email"
    assert data["active"] is True


@pytest.mark.asyncio
async def test_list_rules_endpoint(client):
    resp = await client.get("/api/v1/automation-rules/")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_get_rule_404(client):
    resp = await client.get("/api/v1/automation-rules/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_rule_404(client):
    resp = await client.delete("/api/v1/automation-rules/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_fire_event_endpoint(client):
    resp = await client.post("/api/v1/automation-rules/fire", json={
        "trigger_type": "contact_created",
        "contact_id": "ct-1",
        "data": {"country": "US"},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "rules_matched" in data
