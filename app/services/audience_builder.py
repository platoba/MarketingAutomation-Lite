"""Audience builder — rule-based dynamic segmentation with exclusions."""

import json
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import Column, DateTime, Integer, String, Text, Boolean, Float
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, not_

from app.database import Base
from app.models import new_uuid, utcnow, Contact, SuppressionList


# ── Models ───────────────────────────────────────────────

class AudienceRule(Base):
    """A reusable audience rule (filter condition)."""

    __tablename__ = "audience_rules"

    id = Column(String(36), primary_key=True, default=new_uuid)
    name = Column(String(300), nullable=False)
    description = Column(Text, default="")
    field = Column(String(100), nullable=False)  # email|first_name|country|language|subscribed|created_at|tag|score|lifecycle
    operator = Column(String(30), nullable=False)  # eq|neq|contains|starts_with|gt|lt|gte|lte|in|not_in|between|is_set|not_set
    value = Column(Text, default="")  # JSON-encoded value
    created_at = Column(DateTime, default=utcnow)


class Audience(Base):
    """A saved audience definition with rules and exclusions."""

    __tablename__ = "audiences"

    id = Column(String(36), primary_key=True, default=new_uuid)
    name = Column(String(300), nullable=False)
    description = Column(Text, default="")
    # Rules as JSON array: [{"field": "country", "operator": "eq", "value": "US"}, ...]
    rules = Column(Text, default="[]")
    # Combine logic
    match_type = Column(String(10), default="all")  # all|any
    # Exclusions
    exclude_unsubscribed = Column(Boolean, default=True)
    exclude_suppressed = Column(Boolean, default=True)
    exclude_bounced = Column(Boolean, default=True)
    exclude_campaign_ids = Column(Text, default="[]")  # JSON: campaign IDs already sent to
    # Cache
    estimated_size = Column(Integer, default=0)
    last_estimated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# ── Audience Builder Service ────────────────────────────

class AudienceBuilder:
    """Build dynamic audiences from rules with exclusion logic."""

    VALID_FIELDS = {
        "email", "first_name", "last_name", "phone", "country",
        "language", "subscribed", "created_at",
    }
    VALID_OPERATORS = {
        "eq", "neq", "contains", "starts_with", "ends_with",
        "gt", "lt", "gte", "lte", "in", "not_in", "between",
        "is_set", "not_set",
    }

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_audience(
        self,
        name: str,
        rules: list[dict],
        description: str = "",
        match_type: str = "all",
        exclude_unsubscribed: bool = True,
        exclude_suppressed: bool = True,
        exclude_bounced: bool = True,
        exclude_campaign_ids: Optional[list[str]] = None,
    ) -> Audience:
        """Create a new audience definition."""
        # Validate rules
        for rule in rules:
            self._validate_rule(rule)

        audience = Audience(
            name=name,
            description=description,
            rules=json.dumps(rules),
            match_type=match_type,
            exclude_unsubscribed=exclude_unsubscribed,
            exclude_suppressed=exclude_suppressed,
            exclude_bounced=exclude_bounced,
            exclude_campaign_ids=json.dumps(exclude_campaign_ids or []),
        )
        self.db.add(audience)
        await self.db.commit()
        await self.db.refresh(audience)
        return audience

    def _validate_rule(self, rule: dict):
        """Validate a single rule definition."""
        field = rule.get("field")
        operator = rule.get("operator")

        if not field:
            raise ValueError("Rule must have a 'field'")
        if not operator:
            raise ValueError("Rule must have an 'operator'")
        if field not in self.VALID_FIELDS:
            raise ValueError(f"Invalid field: {field}. Valid: {self.VALID_FIELDS}")
        if operator not in self.VALID_OPERATORS:
            raise ValueError(f"Invalid operator: {operator}. Valid: {self.VALID_OPERATORS}")

    def _build_condition(self, rule: dict):
        """Convert a rule dict into a SQLAlchemy condition."""
        field_name = rule["field"]
        operator = rule["operator"]
        value = rule.get("value", "")

        # Parse JSON value if needed
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                pass

        col = getattr(Contact, field_name, None)
        if col is None:
            return None

        if operator == "eq":
            return col == value
        elif operator == "neq":
            return col != value
        elif operator == "contains":
            return col.ilike(f"%{value}%")
        elif operator == "starts_with":
            return col.ilike(f"{value}%")
        elif operator == "ends_with":
            return col.ilike(f"%{value}")
        elif operator == "gt":
            return col > value
        elif operator == "lt":
            return col < value
        elif operator == "gte":
            return col >= value
        elif operator == "lte":
            return col <= value
        elif operator == "in":
            if isinstance(value, list):
                return col.in_(value)
            return col.in_([value])
        elif operator == "not_in":
            if isinstance(value, list):
                return ~col.in_(value)
            return ~col.in_([value])
        elif operator == "is_set":
            return and_(col.isnot(None), col != "")
        elif operator == "not_set":
            return or_(col.is_(None), col == "")
        return None

    async def build_query(self, audience: Audience):
        """Build a SQLAlchemy query from audience definition."""
        try:
            rules = json.loads(audience.rules) if isinstance(audience.rules, str) else audience.rules
        except (json.JSONDecodeError, TypeError):
            rules = []

        conditions = []
        for rule in rules:
            cond = self._build_condition(rule)
            if cond is not None:
                conditions.append(cond)

        query = select(Contact)

        if conditions:
            if audience.match_type == "any":
                query = query.where(or_(*conditions))
            else:
                query = query.where(and_(*conditions))

        # Exclusions
        if audience.exclude_unsubscribed:
            query = query.where(Contact.subscribed.is_(True))

        if audience.exclude_suppressed:
            suppressed = select(SuppressionList.email)
            query = query.where(~Contact.email.in_(suppressed))

        return query

    async def estimate_size(self, audience: Audience) -> int:
        """Estimate the number of contacts matching this audience."""
        query = await self.build_query(audience)
        count_query = select(func.count()).select_from(query.subquery())
        result = await self.db.execute(count_query)
        count = result.scalar() or 0

        # Update cache
        audience.estimated_size = count
        audience.last_estimated_at = datetime.now(timezone.utc)
        await self.db.commit()

        return count

    async def get_contacts(self, audience: Audience, limit: int = 1000, offset: int = 0) -> list:
        """Retrieve contacts matching the audience rules."""
        query = await self.build_query(audience)
        query = query.limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def preview_rules(self, rules: list[dict], match_type: str = "all") -> int:
        """Preview how many contacts match rules without saving."""
        temp = Audience(
            name="_preview",
            rules=json.dumps(rules),
            match_type=match_type,
            exclude_unsubscribed=True,
            exclude_suppressed=True,
        )
        return await self.estimate_size(temp)

    async def get_audience(self, audience_id: str) -> Optional[Audience]:
        result = await self.db.execute(
            select(Audience).where(Audience.id == audience_id)
        )
        return result.scalar_one_or_none()

    async def list_audiences(self, limit: int = 50, offset: int = 0) -> list[Audience]:
        result = await self.db.execute(
            select(Audience).order_by(Audience.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def delete_audience(self, audience_id: str) -> bool:
        audience = await self.get_audience(audience_id)
        if audience:
            await self.db.delete(audience)
            await self.db.commit()
            return True
        return False

    async def update_audience(
        self,
        audience_id: str,
        name: Optional[str] = None,
        rules: Optional[list[dict]] = None,
        match_type: Optional[str] = None,
    ) -> Optional[Audience]:
        audience = await self.get_audience(audience_id)
        if not audience:
            return None
        if name:
            audience.name = name
        if rules is not None:
            for rule in rules:
                self._validate_rule(rule)
            audience.rules = json.dumps(rules)
        if match_type:
            audience.match_type = match_type
        await self.db.commit()
        await self.db.refresh(audience)
        return audience

    async def overlap_analysis(self, audience_id_a: str, audience_id_b: str) -> dict:
        """Analyze overlap between two audiences."""
        a = await self.get_audience(audience_id_a)
        b = await self.get_audience(audience_id_b)
        if not a or not b:
            return {"error": "Audience not found"}

        query_a = await self.build_query(a)
        query_b = await self.build_query(b)

        contacts_a = set()
        result = await self.db.execute(select(Contact.id).where(Contact.id.in_(select(Contact.id).select_from(query_a.subquery()))))
        for row in result:
            contacts_a.add(row[0])

        contacts_b = set()
        result = await self.db.execute(select(Contact.id).where(Contact.id.in_(select(Contact.id).select_from(query_b.subquery()))))
        for row in result:
            contacts_b.add(row[0])

        overlap = contacts_a & contacts_b
        union = contacts_a | contacts_b

        return {
            "audience_a": {"id": audience_id_a, "size": len(contacts_a)},
            "audience_b": {"id": audience_id_b, "size": len(contacts_b)},
            "overlap": len(overlap),
            "union": len(union),
            "jaccard_index": round(len(overlap) / len(union), 4) if union else 0.0,
        }
