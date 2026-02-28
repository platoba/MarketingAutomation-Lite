"""Tests for audience builder service."""

import json
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from app.services.audience_builder import Audience, AudienceBuilder, AudienceRule
from app.models import Contact


class TestAudienceModel:
    def test_defaults(self):
        a = Audience(name="Test")
        assert a.match_type == "all"
        assert a.exclude_unsubscribed is True
        assert a.exclude_suppressed is True
        assert a.exclude_bounced is True
        assert a.estimated_size == 0

    def test_any_match(self):
        a = Audience(name="Any", match_type="any")
        assert a.match_type == "any"


class TestAudienceRuleModel:
    def test_create(self):
        r = AudienceRule(name="US users", field="country", operator="eq", value='"US"')
        assert r.field == "country"
        assert r.operator == "eq"

    def test_defaults(self):
        r = AudienceRule(name="test", field="email", operator="contains")
        assert r.description == ""


class TestAudienceBuilder:
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
    async def test_create_audience(self, db):
        builder = AudienceBuilder(db)
        a = await builder.create_audience(
            "US VIPs", [{"field": "country", "operator": "eq", "value": "US"}],
        )
        assert a.name == "US VIPs"
        assert a.id is not None

    @pytest.mark.asyncio
    async def test_create_with_match_any(self, db):
        builder = AudienceBuilder(db)
        a = await builder.create_audience(
            "Multi", [
                {"field": "country", "operator": "eq", "value": "US"},
                {"field": "country", "operator": "eq", "value": "UK"},
            ],
            match_type="any",
        )
        assert a.match_type == "any"

    @pytest.mark.asyncio
    async def test_validate_invalid_field(self, db):
        builder = AudienceBuilder(db)
        with pytest.raises(ValueError, match="Invalid field"):
            await builder.create_audience(
                "Bad", [{"field": "nonexistent", "operator": "eq", "value": "x"}],
            )

    @pytest.mark.asyncio
    async def test_validate_invalid_operator(self, db):
        builder = AudienceBuilder(db)
        with pytest.raises(ValueError, match="Invalid operator"):
            await builder.create_audience(
                "Bad", [{"field": "email", "operator": "like", "value": "x"}],
            )

    @pytest.mark.asyncio
    async def test_validate_missing_field(self, db):
        builder = AudienceBuilder(db)
        with pytest.raises(ValueError, match="must have a 'field'"):
            await builder.create_audience("Bad", [{"operator": "eq", "value": "x"}])

    @pytest.mark.asyncio
    async def test_validate_missing_operator(self, db):
        builder = AudienceBuilder(db)
        with pytest.raises(ValueError, match="must have an 'operator'"):
            await builder.create_audience("Bad", [{"field": "email", "value": "x"}])

    @pytest.mark.asyncio
    async def test_estimate_empty(self, db):
        builder = AudienceBuilder(db)
        a = await builder.create_audience(
            "Empty", [{"field": "country", "operator": "eq", "value": "ZZ"}],
        )
        size = await builder.estimate_size(a)
        assert size == 0

    @pytest.mark.asyncio
    async def test_estimate_with_contacts(self, db):
        # Add contacts
        c1 = Contact(email="us1@test.com", country="US", subscribed=True)
        c2 = Contact(email="us2@test.com", country="US", subscribed=True)
        c3 = Contact(email="uk1@test.com", country="UK", subscribed=True)
        db.add_all([c1, c2, c3])
        await db.commit()

        builder = AudienceBuilder(db)
        a = await builder.create_audience(
            "US", [{"field": "country", "operator": "eq", "value": "US"}],
        )
        size = await builder.estimate_size(a)
        assert size == 2

    @pytest.mark.asyncio
    async def test_get_contacts(self, db):
        c1 = Contact(email="en1@test.com", language="en", subscribed=True)
        c2 = Contact(email="en2@test.com", language="en", subscribed=True)
        c3 = Contact(email="fr1@test.com", language="fr", subscribed=True)
        db.add_all([c1, c2, c3])
        await db.commit()

        builder = AudienceBuilder(db)
        a = await builder.create_audience(
            "English", [{"field": "language", "operator": "eq", "value": "en"}],
        )
        contacts = await builder.get_contacts(a)
        assert len(contacts) == 2

    @pytest.mark.asyncio
    async def test_exclude_unsubscribed(self, db):
        c1 = Contact(email="sub@test.com", country="US", subscribed=True)
        c2 = Contact(email="unsub@test.com", country="US", subscribed=False)
        db.add_all([c1, c2])
        await db.commit()

        builder = AudienceBuilder(db)
        a = await builder.create_audience(
            "US All", [{"field": "country", "operator": "eq", "value": "US"}],
            exclude_unsubscribed=True,
        )
        size = await builder.estimate_size(a)
        assert size == 1

    @pytest.mark.asyncio
    async def test_contains_operator(self, db):
        c1 = Contact(email="john@gmail.com", subscribed=True)
        c2 = Contact(email="jane@yahoo.com", subscribed=True)
        db.add_all([c1, c2])
        await db.commit()

        builder = AudienceBuilder(db)
        a = await builder.create_audience(
            "Gmail", [{"field": "email", "operator": "contains", "value": "gmail"}],
        )
        contacts = await builder.get_contacts(a)
        assert len(contacts) == 1

    @pytest.mark.asyncio
    async def test_list_audiences(self, db):
        builder = AudienceBuilder(db)
        await builder.create_audience("A1", [{"field": "country", "operator": "eq", "value": "US"}])
        await builder.create_audience("A2", [{"field": "country", "operator": "eq", "value": "UK"}])
        audiences = await builder.list_audiences()
        assert len(audiences) == 2

    @pytest.mark.asyncio
    async def test_delete_audience(self, db):
        builder = AudienceBuilder(db)
        a = await builder.create_audience("Del", [{"field": "country", "operator": "eq", "value": "US"}])
        deleted = await builder.delete_audience(a.id)
        assert deleted is True
        assert await builder.get_audience(a.id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, db):
        builder = AudienceBuilder(db)
        deleted = await builder.delete_audience("nope")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_update_audience(self, db):
        builder = AudienceBuilder(db)
        a = await builder.create_audience("Old", [{"field": "country", "operator": "eq", "value": "US"}])
        updated = await builder.update_audience(a.id, name="New Name")
        assert updated.name == "New Name"

    @pytest.mark.asyncio
    async def test_update_nonexistent(self, db):
        builder = AudienceBuilder(db)
        result = await builder.update_audience("nope", name="x")
        assert result is None

    @pytest.mark.asyncio
    async def test_preview_rules(self, db):
        c1 = Contact(email="a@test.com", country="US", subscribed=True)
        db.add(c1)
        await db.commit()

        builder = AudienceBuilder(db)
        count = await builder.preview_rules(
            [{"field": "country", "operator": "eq", "value": "US"}],
        )
        assert count == 1

    @pytest.mark.asyncio
    async def test_neq_operator(self, db):
        c1 = Contact(email="a@test.com", country="US", subscribed=True)
        c2 = Contact(email="b@test.com", country="UK", subscribed=True)
        db.add_all([c1, c2])
        await db.commit()

        builder = AudienceBuilder(db)
        a = await builder.create_audience(
            "Not US", [{"field": "country", "operator": "neq", "value": "US"}],
        )
        contacts = await builder.get_contacts(a)
        assert len(contacts) == 1
        assert contacts[0].country == "UK"

    @pytest.mark.asyncio
    async def test_is_set_operator(self, db):
        c1 = Contact(email="a@test.com", phone="123", subscribed=True)
        c2 = Contact(email="b@test.com", phone="", subscribed=True)
        db.add_all([c1, c2])
        await db.commit()

        builder = AudienceBuilder(db)
        a = await builder.create_audience(
            "Has Phone", [{"field": "phone", "operator": "is_set"}],
        )
        contacts = await builder.get_contacts(a)
        assert len(contacts) == 1

    @pytest.mark.asyncio
    async def test_starts_with_operator(self, db):
        c1 = Contact(email="a@test.com", first_name="John", subscribed=True)
        c2 = Contact(email="b@test.com", first_name="Jane", subscribed=True)
        c3 = Contact(email="c@test.com", first_name="Bob", subscribed=True)
        db.add_all([c1, c2, c3])
        await db.commit()

        builder = AudienceBuilder(db)
        a = await builder.create_audience(
            "J Names", [{"field": "first_name", "operator": "starts_with", "value": "J"}],
        )
        contacts = await builder.get_contacts(a)
        assert len(contacts) == 2

    @pytest.mark.asyncio
    async def test_in_operator(self, db):
        c1 = Contact(email="a@test.com", country="US", subscribed=True)
        c2 = Contact(email="b@test.com", country="UK", subscribed=True)
        c3 = Contact(email="c@test.com", country="DE", subscribed=True)
        db.add_all([c1, c2, c3])
        await db.commit()

        builder = AudienceBuilder(db)
        a = await builder.create_audience(
            "English", [{"field": "country", "operator": "in", "value": json.dumps(["US", "UK"])}],
        )
        contacts = await builder.get_contacts(a)
        assert len(contacts) == 2
