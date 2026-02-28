"""Tests for suppression list management."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.models.lead_score import SuppressionList


class TestSuppressionListModel:
    """Test SuppressionList model fields and defaults."""

    def test_create_bounce_entry(self):
        entry = SuppressionList(
            email="hard-bounce@example.com",
            reason="bounce",
            source="campaign-abc",
            notes="550 mailbox not found",
        )
        assert entry.email == "hard-bounce@example.com"
        assert entry.reason == "bounce"

    def test_create_complaint_entry(self):
        entry = SuppressionList(
            email="complainer@example.com",
            reason="complaint",
            source="ses-feedback",
        )
        assert entry.reason == "complaint"

    def test_create_manual_entry(self):
        entry = SuppressionList(
            email="ceo@competitor.com",
            reason="manual",
            notes="Do not email — competitor",
        )
        assert entry.reason == "manual"

    def test_create_compliance_entry(self):
        entry = SuppressionList(
            email="gdpr-request@eu.com",
            reason="compliance",
            source="gdpr-portal",
        )
        assert entry.reason == "compliance"

    def test_default_empty_notes(self):
        entry = SuppressionList(email="a@b.com", reason="unsubscribe")
        assert entry.notes == ""

    def test_default_empty_source(self):
        entry = SuppressionList(email="a@b.com", reason="bounce")
        assert entry.source == ""


class TestSuppressionSchemas:
    """Test API schema validation for suppression endpoints."""

    def test_create_schema(self):
        from app.api.scoring import SuppressionCreate

        data = SuppressionCreate(
            email="test@example.com",
            reason="bounce",
            source="campaign-1",
            notes="Hard bounce",
        )
        assert data.email == "test@example.com"
        assert data.reason == "bounce"

    def test_create_schema_minimal(self):
        from app.api.scoring import SuppressionCreate

        data = SuppressionCreate(email="x@y.com", reason="manual")
        assert data.source == ""
        assert data.notes == ""

    def test_out_schema(self):
        from app.api.scoring import SuppressionOut

        now = datetime.now(timezone.utc)
        out = SuppressionOut(
            id="s-1",
            email="a@b.com",
            reason="complaint",
            source="ses",
            notes="",
            created_at=now,
        )
        assert out.id == "s-1"
        assert out.reason == "complaint"

    def test_bulk_suppression_schema(self):
        from app.api.scoring import BulkSuppressionRequest

        bulk = BulkSuppressionRequest(
            emails=["a@b.com", "c@d.com", "e@f.com"],
            reason="bounce",
            source="import-batch-1",
        )
        assert len(bulk.emails) == 3
        assert bulk.reason == "bounce"

    def test_bulk_suppression_empty_list(self):
        from app.api.scoring import BulkSuppressionRequest

        bulk = BulkSuppressionRequest(emails=[], reason="manual")
        assert len(bulk.emails) == 0


class TestSuppressionReasons:
    """Validate all supported suppression reason types."""

    VALID_REASONS = ["bounce", "complaint", "unsubscribe", "manual", "compliance"]

    @pytest.mark.parametrize("reason", VALID_REASONS)
    def test_valid_reason(self, reason):
        entry = SuppressionList(email=f"{reason}@test.com", reason=reason)
        assert entry.reason == reason


class TestSuppressionEmail:
    """Test email handling in suppression list."""

    def test_email_stored(self):
        entry = SuppressionList(email="Test@Example.COM", reason="manual")
        assert entry.email == "Test@Example.COM"  # Storage preserves case; normalization is in service

    def test_long_email(self):
        long_local = "a" * 64
        long_domain = "b" * 250 + ".com"
        entry = SuppressionList(email=f"{long_local}@{long_domain}", reason="manual")
        assert len(entry.email) > 100

    def test_email_with_plus(self):
        entry = SuppressionList(email="user+tag@gmail.com", reason="unsubscribe")
        assert "+" in entry.email
