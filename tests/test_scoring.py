"""Tests for lead scoring engine, lifecycle management, and suppression lists."""

import json
import math
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Scoring engine unit tests ─────────────────────────────


class TestProfileScoring:
    """Test profile completeness scoring."""

    def _make_contact(self, **kwargs):
        defaults = {
            "email": "test@example.com",
            "first_name": "",
            "last_name": "",
            "phone": "",
            "country": "",
            "custom_fields": "{}",
        }
        defaults.update(kwargs)
        contact = MagicMock()
        for k, v in defaults.items():
            setattr(contact, k, v)
        return contact

    def test_empty_profile(self):
        from app.services.scoring_engine import calculate_profile_score

        contact = self._make_contact(email="")
        score = calculate_profile_score(contact)
        assert score == 0.0

    def test_email_only(self):
        from app.services.scoring_engine import calculate_profile_score

        contact = self._make_contact()
        score = calculate_profile_score(contact)
        assert score == 4.0  # email only

    def test_full_profile(self):
        from app.services.scoring_engine import calculate_profile_score

        contact = self._make_contact(
            first_name="John",
            last_name="Doe",
            phone="+1234567890",
            country="US",
            custom_fields=json.dumps({"company": "Acme", "role": "CEO"}),
        )
        score = calculate_profile_score(contact)
        assert score == 20.0  # 4+4+3+3+3+3 = 20

    def test_partial_profile(self):
        from app.services.scoring_engine import calculate_profile_score

        contact = self._make_contact(first_name="Jane", country="UK")
        score = calculate_profile_score(contact)
        assert score == 11.0  # 4(email) + 4(first_name) + 3(country)

    def test_json_string_custom_fields(self):
        from app.services.scoring_engine import calculate_profile_score

        contact = self._make_contact(
            first_name="A",
            custom_fields='{"a": 1, "b": 2}',
        )
        score = calculate_profile_score(contact)
        assert score >= 11.0  # email + first_name + custom_fields bonus

    def test_invalid_json_custom_fields(self):
        from app.services.scoring_engine import calculate_profile_score

        contact = self._make_contact(custom_fields="not json")
        score = calculate_profile_score(contact)
        assert score == 4.0  # just email

    def test_dict_custom_fields(self):
        from app.services.scoring_engine import calculate_profile_score

        contact = self._make_contact(
            custom_fields={"industry": "tech", "size": "large"},
        )
        score = calculate_profile_score(contact)
        assert score >= 7.0


class TestRecencyScoring:
    """Test time-decay recency scoring."""

    def test_no_activity(self):
        from app.services.scoring_engine import calculate_recency_score

        assert calculate_recency_score(None) == 0.0

    def test_recent_activity(self):
        from app.services.scoring_engine import calculate_recency_score

        now = datetime.now(timezone.utc)
        score = calculate_recency_score(now)
        assert score == 20.0

    def test_old_activity(self):
        from app.services.scoring_engine import calculate_recency_score

        old = datetime.now(timezone.utc) - timedelta(days=100)
        score = calculate_recency_score(old)
        assert score == 0.0

    def test_30_days_ago(self):
        from app.services.scoring_engine import calculate_recency_score

        t = datetime.now(timezone.utc) - timedelta(days=30)
        score = calculate_recency_score(t)
        expected = 20.0 * math.exp(-0.03 * 30)
        assert abs(score - round(expected, 2)) < 0.1

    def test_naive_datetime_handled(self):
        from app.services.scoring_engine import calculate_recency_score

        naive = datetime.now() - timedelta(days=1)
        score = calculate_recency_score(naive)
        assert 0 < score < 20.0

    def test_exactly_90_days(self):
        from app.services.scoring_engine import calculate_recency_score

        t = datetime.now(timezone.utc) - timedelta(days=90)
        score = calculate_recency_score(t)
        assert score == 0.0


class TestGradeAndLifecycle:
    """Test grade and lifecycle stage determination."""

    def test_grades(self):
        from app.services.scoring_engine import _score_to_grade

        assert _score_to_grade(95) == "A+"
        assert _score_to_grade(85) == "A"
        assert _score_to_grade(75) == "B+"
        assert _score_to_grade(65) == "B"
        assert _score_to_grade(50) == "C"
        assert _score_to_grade(30) == "D"
        assert _score_to_grade(10) == "F"
        assert _score_to_grade(0) == "F"

    def test_lifecycle_stages(self):
        from app.services.scoring_engine import _score_to_lifecycle

        assert _score_to_lifecycle(95, "subscriber") == "evangelist"
        assert _score_to_lifecycle(75, "subscriber") == "customer"
        assert _score_to_lifecycle(60, "subscriber") == "sql"
        assert _score_to_lifecycle(45, "subscriber") == "mql"
        assert _score_to_lifecycle(25, "subscriber") == "lead"
        assert _score_to_lifecycle(10, "subscriber") == "subscriber"

    def test_lifecycle_no_demotion_from_customer(self):
        from app.services.scoring_engine import _score_to_lifecycle

        assert _score_to_lifecycle(10, "customer") == "customer"
        assert _score_to_lifecycle(5, "evangelist") == "evangelist"

    def test_lifecycle_promotion(self):
        from app.services.scoring_engine import _score_to_lifecycle

        assert _score_to_lifecycle(50, "lead") == "mql"
        assert _score_to_lifecycle(80, "mql") == "customer"


class TestScoringRuleModel:
    """Test ScoringRule model creation."""

    def test_create_rule(self):
        from app.models.lead_score import ScoringRule

        rule = ScoringRule(
            name="Email Open",
            event_type="email_opened",
            points=5,
            max_per_contact=10,
            decay_days=30,
        )
        assert rule.name == "Email Open"
        assert rule.points == 5
        assert rule.max_per_contact == 10
        assert rule.event_type == "email_opened"

    def test_negative_points(self):
        from app.models.lead_score import ScoringRule

        rule = ScoringRule(
            name="Unsubscribe Penalty",
            event_type="unsubscribed",
            points=-20,
        )
        assert rule.points == -20


class TestContactScoreModel:
    """Test ContactScore model."""

    def test_default_values(self):
        from app.models.lead_score import ContactScore

        score = ContactScore(contact_id="test-123")
        assert score.total_score == 0.0
        assert score.engagement_score == 0.0
        assert score.profile_score == 0.0
        assert score.recency_score == 0.0
        assert score.grade == "C"
        assert score.lifecycle_stage == "subscriber"


class TestScoreEventModel:
    """Test ScoreEvent model."""

    def test_create_event(self):
        from app.models.lead_score import ScoreEvent

        event = ScoreEvent(
            contact_id="contact-1",
            event_type="email_clicked",
            points=10,
            reason="Clicked CTA link",
        )
        assert event.points == 10
        assert event.event_type == "email_clicked"


class TestSuppressionModel:
    """Test SuppressionList model."""

    def test_create_suppression(self):
        from app.models.lead_score import SuppressionList

        entry = SuppressionList(
            email="bounce@example.com",
            reason="bounce",
            source="campaign-123",
        )
        assert entry.email == "bounce@example.com"
        assert entry.reason == "bounce"


# ── API schema validation tests ───────────────────────────


class TestScoringSchemas:
    """Test Pydantic schema validation for scoring API."""

    def test_scoring_rule_create(self):
        from app.api.scoring import ScoringRuleCreate

        rule = ScoringRuleCreate(
            name="Click Bonus",
            event_type="email_clicked",
            points=10,
            max_per_contact=5,
        )
        assert rule.name == "Click Bonus"
        assert rule.points == 10
        assert rule.condition == {}

    def test_scoring_rule_update_partial(self):
        from app.api.scoring import ScoringRuleUpdate

        update = ScoringRuleUpdate(points=15)
        data = update.model_dump(exclude_unset=True)
        assert data == {"points": 15}
        assert "name" not in data

    def test_score_event_create(self):
        from app.api.scoring import ScoreEventCreate

        event = ScoreEventCreate(
            contact_id="c-123",
            event_type="manual_award",
            points=25,
            reason="VIP customer upgrade",
        )
        assert event.points == 25
        assert event.metadata == {}

    def test_suppression_create(self):
        from app.api.scoring import SuppressionCreate

        supp = SuppressionCreate(
            email="bad@example.com",
            reason="complaint",
            source="feedback-form",
        )
        assert supp.reason == "complaint"

    def test_bulk_suppression(self):
        from app.api.scoring import BulkSuppressionRequest

        bulk = BulkSuppressionRequest(
            emails=["a@b.com", "c@d.com"],
            reason="bounce",
        )
        assert len(bulk.emails) == 2

    def test_contact_score_out(self):
        from app.api.scoring import ContactScoreOut

        score = ContactScoreOut(
            contact_id="c-1",
            total_score=75.5,
            engagement_score=50,
            profile_score=15,
            recency_score=10.5,
            grade="B+",
            lifecycle_stage="sql",
        )
        assert score.grade == "B+"

    def test_score_event_out(self):
        from app.api.scoring import ScoreEventOut

        now = datetime.now(timezone.utc)
        out = ScoreEventOut(
            id="e-1",
            contact_id="c-1",
            event_type="email_opened",
            points=5,
            reason="Rule: Open Bonus",
            created_at=now,
        )
        assert out.rule_id is None

    def test_scoring_rule_out_from_model(self):
        from app.api.scoring import ScoringRuleOut

        rule = MagicMock()
        rule.id = "r-1"
        rule.name = "Test Rule"
        rule.description = "A test"
        rule.event_type = "email_opened"
        rule.condition = '{"campaign_id": "c-1"}'
        rule.points = 5
        rule.max_per_contact = 10
        rule.decay_days = 30
        rule.active = True
        rule.created_at = datetime.now(timezone.utc)

        out = ScoringRuleOut.from_model(rule)
        assert out.condition == {"campaign_id": "c-1"}
        assert out.points == 5

    def test_scoring_rule_out_invalid_json(self):
        from app.api.scoring import ScoringRuleOut

        rule = MagicMock()
        rule.id = "r-2"
        rule.name = "Bad JSON"
        rule.description = ""
        rule.event_type = "email_clicked"
        rule.condition = "not-json"
        rule.points = 3
        rule.max_per_contact = 0
        rule.decay_days = 0
        rule.active = True
        rule.created_at = datetime.now(timezone.utc)

        out = ScoringRuleOut.from_model(rule)
        assert out.condition == {}


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_score_grade(self):
        from app.services.scoring_engine import _score_to_grade

        assert _score_to_grade(0) == "F"

    def test_exactly_90_grade(self):
        from app.services.scoring_engine import _score_to_grade

        assert _score_to_grade(90) == "A+"

    def test_negative_score_grade(self):
        from app.services.scoring_engine import _score_to_grade

        assert _score_to_grade(-5) == "F"

    def test_huge_score_grade(self):
        from app.services.scoring_engine import _score_to_grade

        assert _score_to_grade(1000) == "A+"

    def test_recency_far_future(self):
        from app.services.scoring_engine import calculate_recency_score

        future = datetime.now(timezone.utc) + timedelta(days=1)
        score = calculate_recency_score(future)
        assert score == 20.0

    def test_profile_score_capped_at_20(self):
        from app.services.scoring_engine import calculate_profile_score

        contact = MagicMock()
        contact.email = "a@b.com"
        contact.first_name = "A"
        contact.last_name = "B"
        contact.phone = "+1"
        contact.country = "US"
        contact.custom_fields = json.dumps({f"k{i}": i for i in range(10)})
        score = calculate_profile_score(contact)
        assert score <= 20.0

    def test_lifecycle_subscriber_default(self):
        from app.services.scoring_engine import _score_to_lifecycle

        assert _score_to_lifecycle(0, "subscriber") == "subscriber"

    def test_lifecycle_boundary_20(self):
        from app.services.scoring_engine import _score_to_lifecycle

        assert _score_to_lifecycle(20, "subscriber") == "lead"
        assert _score_to_lifecycle(19, "subscriber") == "subscriber"
