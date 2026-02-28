"""Workflow automation engine — evaluates triggers, conditions, and executes actions."""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Contact, Tag, Workflow, WorkflowLog, contact_tags

logger = logging.getLogger(__name__)


async def execute_workflow(workflow: Workflow, contact: Contact | None, context: dict, db: AsyncSession) -> list[dict]:
    """
    Execute all steps of a workflow for a given contact.

    Steps format: [
        {"type": "condition", "field": "country", "operator": "eq", "value": "US"},
        {"type": "action", "action": "tag", "tag_name": "vip"},
        {"type": "action", "action": "update_field", "field": "language", "value": "en"},
        {"type": "action", "action": "send_email", "subject": "Welcome!", "body": "Hello!"},
    ]

    Returns list of step results.
    """
    steps_raw = workflow.steps
    if isinstance(steps_raw, str):
        try:
            steps = json.loads(steps_raw)
        except (json.JSONDecodeError, TypeError):
            steps = []
    else:
        steps = steps_raw or []

    results = []

    for i, step in enumerate(steps):
        step_type = step.get("type", "action")

        if step_type == "condition":
            passed = evaluate_condition(step, contact, context)
            status = "completed" if passed else "skipped"
            result = {"step": i, "type": "condition", "passed": passed}
            results.append(result)

            # Log
            db.add(WorkflowLog(
                workflow_id=workflow.id,
                contact_id=contact.id if contact else None,
                step_index=i,
                status=status,
                result=json.dumps(result),
            ))

            if not passed:
                # Skip remaining steps
                for j in range(i + 1, len(steps)):
                    skip_result = {"step": j, "type": steps[j].get("type", "action"), "skipped": True}
                    results.append(skip_result)
                    db.add(WorkflowLog(
                        workflow_id=workflow.id,
                        contact_id=contact.id if contact else None,
                        step_index=j,
                        status="skipped",
                        result=json.dumps(skip_result),
                    ))
                break

        elif step_type == "action":
            action_result = await execute_action(step, contact, context, db)
            results.append({"step": i, "type": "action", **action_result})

            db.add(WorkflowLog(
                workflow_id=workflow.id,
                contact_id=contact.id if contact else None,
                step_index=i,
                status="completed" if action_result.get("success") else "failed",
                result=json.dumps({"step": i, **action_result}),
            ))

        elif step_type == "delay":
            # In a real system, this would schedule a delayed execution
            # For now we just log it
            result = {"step": i, "type": "delay", "hours": step.get("hours", 0), "noted": True}
            results.append(result)
            db.add(WorkflowLog(
                workflow_id=workflow.id,
                contact_id=contact.id if contact else None,
                step_index=i,
                status="completed",
                result=json.dumps(result),
            ))

    await db.commit()
    return results


def evaluate_condition(step: dict, contact: Contact | None, context: dict) -> bool:
    """Evaluate a condition step against contact data or context."""
    field = step.get("field", "")
    operator = step.get("operator", "eq")
    value = step.get("value", "")

    # Get the actual value from contact or context
    actual = None
    if contact and hasattr(contact, field):
        actual = getattr(contact, field)
    elif field in context:
        actual = context[field]

    if actual is None:
        return operator == "is_null"

    # String comparison
    actual_str = str(actual).lower()
    value_str = str(value).lower()

    if operator == "eq":
        return actual_str == value_str
    elif operator == "neq":
        return actual_str != value_str
    elif operator == "contains":
        return value_str in actual_str
    elif operator == "not_contains":
        return value_str not in actual_str
    elif operator == "gt":
        try:
            return float(actual) > float(value)
        except (ValueError, TypeError):
            return False
    elif operator == "lt":
        try:
            return float(actual) < float(value)
        except (ValueError, TypeError):
            return False
    elif operator == "is_true":
        return bool(actual)
    elif operator == "is_false":
        return not bool(actual)
    elif operator == "is_null":
        return actual is None
    else:
        logger.warning(f"Unknown operator: {operator}")
        return False


async def execute_action(step: dict, contact: Contact | None, context: dict, db: AsyncSession) -> dict:
    """Execute an action step."""
    action = step.get("action", "")

    try:
        if action == "tag" and contact:
            tag_name = step.get("tag_name", "")
            if tag_name:
                # Find or create tag
                result = await db.execute(select(Tag).where(Tag.name == tag_name))
                tag = result.scalar_one_or_none()
                if not tag:
                    tag = Tag(name=tag_name)
                    db.add(tag)
                    await db.flush()
                if tag not in contact.tags:
                    contact.tags.append(tag)
            return {"success": True, "action": "tag", "tag_name": tag_name}

        elif action == "remove_tag" and contact:
            tag_name = step.get("tag_name", "")
            if tag_name:
                result = await db.execute(select(Tag).where(Tag.name == tag_name))
                tag = result.scalar_one_or_none()
                if tag and tag in contact.tags:
                    contact.tags.remove(tag)
            return {"success": True, "action": "remove_tag", "tag_name": tag_name}

        elif action == "update_field" and contact:
            field = step.get("field", "")
            value = step.get("value", "")
            if field and hasattr(contact, field) and field not in ("id", "email", "created_at"):
                setattr(contact, field, value)
            return {"success": True, "action": "update_field", "field": field, "value": value}

        elif action == "send_email":
            # In production, this would send via the email service
            # For now, we log the intent
            return {
                "success": True,
                "action": "send_email",
                "subject": step.get("subject", ""),
                "to": contact.email if contact else "unknown",
                "queued": True,
            }

        elif action == "unsubscribe" and contact:
            contact.subscribed = False
            return {"success": True, "action": "unsubscribe"}

        elif action == "subscribe" and contact:
            contact.subscribed = True
            return {"success": True, "action": "subscribe"}

        else:
            return {"success": False, "action": action, "error": "Unknown action or no contact"}

    except Exception as e:
        logger.error(f"Action execution failed: {e}")
        return {"success": False, "action": action, "error": str(e)}
