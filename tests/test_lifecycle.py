"""Tests for contact lifecycle management service."""

import pytest
from datetime import datetime, timedelta, timezone

from app.services.contact_lifecycle import (
    DEFAULT_RULES,
    DORMANCY_RULES,
    LifecycleStage,
    STAGE_ORDER,
    TransitionResult,
    TransitionRule,
)


class TestLifecycleStage:
    """Tests for lifecycle stage enum."""

    def test_all_stages_exist(self):
        stages = [
            "new", "subscriber", "lead", "mql", "sql",
            "opportunity", "customer", "evangelist", "dormant", "churned",
        ]
        for s in stages:
            assert LifecycleStage(s) is not None

    def test_stage_count(self):
        assert len(LifecycleStage) == 10

    def test_stage_order_values(self):
        assert STAGE_ORDER[LifecycleStage.NEW] < STAGE_ORDER[LifecycleStage.SUBSCRIBER]
        assert STAGE_ORDER[LifecycleStage.SUBSCRIBER] < STAGE_ORDER[LifecycleStage.LEAD]
        assert STAGE_ORDER[LifecycleStage.LEAD] < STAGE_ORDER[LifecycleStage.MQL]
        assert STAGE_ORDER[LifecycleStage.MQL] < STAGE_ORDER[LifecycleStage.SQL]
        assert STAGE_ORDER[LifecycleStage.SQL] < STAGE_ORDER[LifecycleStage.OPPORTUNITY]
        assert STAGE_ORDER[LifecycleStage.OPPORTUNITY] < STAGE_ORDER[LifecycleStage.CUSTOMER]
        assert STAGE_ORDER[LifecycleStage.CUSTOMER] < STAGE_ORDER[LifecycleStage.EVANGELIST]

    def test_dormant_negative_order(self):
        assert STAGE_ORDER[LifecycleStage.DORMANT] < 0

    def test_churned_negative_order(self):
        assert STAGE_ORDER[LifecycleStage.CHURNED] < 0


class TestTransitionRule:
    """Tests for transition rule dataclass."""

    def test_basic_creation(self):
        rule = TransitionRule(
            from_stage=LifecycleStage.NEW,
            to_stage=LifecycleStage.SUBSCRIBER,
            min_score=5,
        )
        assert rule.from_stage == LifecycleStage.NEW
        assert rule.to_stage == LifecycleStage.SUBSCRIBER
        assert rule.min_score == 5

    def test_defaults(self):
        rule = TransitionRule(
            from_stage=LifecycleStage.NEW,
            to_stage=LifecycleStage.SUBSCRIBER,
        )
        assert rule.min_score == 0
        assert rule.min_opens == 0
        assert rule.min_clicks == 0
        assert rule.min_days_in_stage == 0
        assert rule.max_inactive_days is None

    def test_dormancy_rule(self):
        rule = TransitionRule(
            from_stage=LifecycleStage.LEAD,
            to_stage=LifecycleStage.DORMANT,
            max_inactive_days=45,
        )
        assert rule.max_inactive_days == 45


class TestDefaultRules:
    """Validate the default rule set."""

    def test_default_rules_exist(self):
        assert len(DEFAULT_RULES) >= 7

    def test_progression_chain(self):
        """Verify rules form a progression chain."""
        stages_covered = set()
        for rule in DEFAULT_RULES:
            stages_covered.add(rule.from_stage)
            stages_covered.add(rule.to_stage)
        # Should cover the full progression
        assert LifecycleStage.NEW in stages_covered
        assert LifecycleStage.EVANGELIST in stages_covered

    def test_scores_increase_along_chain(self):
        """Higher stages should require higher scores."""
        score_by_from = {}
        for rule in DEFAULT_RULES:
            if rule.from_stage not in score_by_from:
                score_by_from[rule.from_stage] = rule.min_score

        if LifecycleStage.SUBSCRIBER in score_by_from and LifecycleStage.MQL in score_by_from:
            assert score_by_from[LifecycleStage.SUBSCRIBER] <= score_by_from[LifecycleStage.MQL]

    def test_all_rules_have_descriptions(self):
        for rule in DEFAULT_RULES:
            assert rule.description, f"Rule {rule.from_stage}→{rule.to_stage} missing description"

    def test_dormancy_rules_exist(self):
        assert len(DORMANCY_RULES) >= 4

    def test_dormancy_rules_target_dormant(self):
        for rule in DORMANCY_RULES:
            assert rule.to_stage == LifecycleStage.DORMANT

    def test_dormancy_days_decrease_with_stage(self):
        """Higher stages should have shorter dormancy thresholds."""
        subscriber_days = None
        mql_days = None
        for rule in DORMANCY_RULES:
            if rule.from_stage == LifecycleStage.SUBSCRIBER:
                subscriber_days = rule.max_inactive_days
            elif rule.from_stage == LifecycleStage.MQL:
                mql_days = rule.max_inactive_days
        if subscriber_days and mql_days:
            assert subscriber_days > mql_days


class TestTransitionResult:
    """Tests for TransitionResult dataclass."""

    def test_basic_transitioned(self):
        r = TransitionResult(
            contact_id="c1",
            previous_stage="new",
            new_stage="subscriber",
            transitioned=True,
            rule_description="Confirmed signup",
        )
        assert r.transitioned is True
        assert r.new_stage == "subscriber"

    def test_no_transition(self):
        r = TransitionResult(
            contact_id="c1",
            previous_stage="new",
            new_stage="new",
            transitioned=False,
            reason="No matching rule",
        )
        assert r.transitioned is False
        assert r.previous_stage == r.new_stage

    def test_to_dict(self):
        r = TransitionResult(
            contact_id="c1",
            previous_stage="lead",
            new_stage="mql",
            transitioned=True,
            rule_description="Score threshold met",
            reason="Score=40, opens=5, clicks=3",
        )
        d = r.to_dict()
        assert d["contact_id"] == "c1"
        assert d["previous_stage"] == "lead"
        assert d["new_stage"] == "mql"
        assert d["transitioned"] is True
        assert "Score threshold" in d["rule_description"]

    def test_dormancy_transition(self):
        r = TransitionResult(
            contact_id="c1",
            previous_stage="subscriber",
            new_stage="dormant",
            transitioned=True,
            reason="Inactive for 65 days",
        )
        assert r.new_stage == "dormant"
        assert "65 days" in r.reason

    def test_churn_transition(self):
        r = TransitionResult(
            contact_id="c1",
            previous_stage="lead",
            new_stage="churned",
            transitioned=True,
            reason="Contact unsubscribed",
        )
        assert r.new_stage == "churned"


class TestLifecycleLogic:
    """Unit tests for lifecycle evaluation logic (no DB)."""

    def test_rule_matching_by_stage(self):
        """Only rules matching current stage should apply."""
        matching = [r for r in DEFAULT_RULES if r.from_stage.value == "new"]
        assert len(matching) >= 1
        for r in matching:
            assert r.from_stage == LifecycleStage.NEW

    def test_no_rules_for_evangelist_progression(self):
        """Evangelist is the top stage - no progression from it."""
        evangelist_rules = [r for r in DEFAULT_RULES if r.from_stage == LifecycleStage.EVANGELIST]
        # May have 0 (top of chain) or special rules
        if evangelist_rules:
            for r in evangelist_rules:
                assert r.to_stage != LifecycleStage.EVANGELIST  # No self-loop

    def test_customer_to_evangelist_high_threshold(self):
        """Customer→Evangelist should require high score."""
        for rule in DEFAULT_RULES:
            if rule.from_stage == LifecycleStage.CUSTOMER and rule.to_stage == LifecycleStage.EVANGELIST:
                assert rule.min_score >= 80

    def test_mql_requires_clicks(self):
        """MQL transition should require click engagement."""
        for rule in DEFAULT_RULES:
            if rule.to_stage == LifecycleStage.MQL:
                assert rule.min_clicks > 0

    def test_sql_requires_higher_score_than_mql(self):
        """SQL should require higher engagement than MQL."""
        mql_score = 0
        sql_score = 0
        for rule in DEFAULT_RULES:
            if rule.to_stage == LifecycleStage.MQL:
                mql_score = rule.min_score
            if rule.to_stage == LifecycleStage.SQL:
                sql_score = rule.min_score
        if mql_score and sql_score:
            assert sql_score > mql_score

    def test_stage_order_is_consistent(self):
        """Transition rules should always go to a higher stage."""
        for rule in DEFAULT_RULES:
            from_order = STAGE_ORDER[rule.from_stage]
            to_order = STAGE_ORDER[rule.to_stage]
            assert to_order > from_order, (
                f"Rule {rule.from_stage}→{rule.to_stage} goes to lower stage"
            )

    def test_dormancy_applies_to_active_stages_only(self):
        """Dormancy rules should not apply to already dormant/churned contacts."""
        for rule in DORMANCY_RULES:
            assert rule.from_stage not in (LifecycleStage.DORMANT, LifecycleStage.CHURNED)

    def test_dormancy_not_for_customer(self):
        """Customers shouldn't auto-dormant (they've converted)."""
        customer_dormancy = [r for r in DORMANCY_RULES if r.from_stage == LifecycleStage.CUSTOMER]
        assert len(customer_dormancy) == 0

    def test_dormancy_not_for_evangelist(self):
        """Evangelists shouldn't auto-dormant."""
        ev_dormancy = [r for r in DORMANCY_RULES if r.from_stage == LifecycleStage.EVANGELIST]
        assert len(ev_dormancy) == 0
