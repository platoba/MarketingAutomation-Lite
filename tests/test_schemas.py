"""Test Pydantic schemas validation."""

import pytest
from pydantic import ValidationError

from app.schemas import ContactCreate, CampaignCreate, WorkflowCreate


def test_contact_create_valid():
    c = ContactCreate(email="test@example.com", first_name="John")
    assert c.email == "test@example.com"
    assert c.subscribed is True


def test_contact_create_invalid_email():
    with pytest.raises(ValidationError):
        ContactCreate(email="not-an-email")


def test_campaign_create():
    c = CampaignCreate(name="Test Campaign", subject="Hello!")
    assert c.name == "Test Campaign"
    assert c.html_body == ""


def test_workflow_create():
    w = WorkflowCreate(
        name="Welcome Series",
        trigger_type="signup",
        steps=[
            {"type": "email", "template": "welcome", "delay_hours": 0},
            {"type": "delay", "hours": 24},
            {"type": "email", "template": "tips", "delay_hours": 0},
        ],
    )
    assert len(w.steps) == 3
    assert w.active is False
