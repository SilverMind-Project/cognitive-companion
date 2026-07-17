"""Webhook trigger endpoint.

External systems (Home Assistant automations, IFTTT, n8n, custom scripts) can
trigger pipeline executions by POSTing to ``/api/v1/webhooks/{rule_id}``.

Security: each webhook-enabled rule has an auto-generated HMAC secret. The
caller must include the secret in the ``X-Webhook-Secret`` header.
"""

from __future__ import annotations

import hmac
import secrets
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session, joinedload

from backend.core.auth import require_permission
from backend.core.database import get_db
from backend.core.logging import get_logger
from backend.models.rule import Rule
from backend.schemas.misc_responses import WebhookSecretOut, WebhookTriggerOut
from backend.steps.base import TriggerContext

logger = get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def generate_webhook_secret() -> str:
    """Generate a 32-character URL-safe secret."""
    return secrets.token_urlsafe(24)


def verify_webhook_secret(provided: str, expected: str) -> bool:
    """Constant-time comparison of webhook secrets."""
    return hmac.compare_digest(provided, expected)


@router.post("/{rule_id}", status_code=202, response_model=WebhookTriggerOut)
async def trigger_webhook(
    rule_id: int,
    request: Request,
    payload: dict[str, Any] | None = None,
    db: Session = Depends(get_db),
    x_webhook_secret: str | None = Header(None),
):
    """Trigger a rule's pipeline via webhook.

    The rule must have ``trigger_type`` set to ``"webhook"`` and a
    ``webhook_secret`` in its config.
    """
    rule = (
        db.query(Rule)
        .options(joinedload(Rule.steps))
        .filter(Rule.id == rule_id, Rule.enabled.is_(True), Rule.filter_active())
        .first()
    )
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found or disabled")

    if "webhook" not in rule.trigger_types:
        raise HTTPException(
            status_code=400,
            detail="Rule is not configured for webhook triggers",
        )

    # Validate webhook secret
    webhook_config = rule.webhook_config or {}
    expected_secret = webhook_config.get("secret", "")
    if not expected_secret:
        raise HTTPException(status_code=400, detail="Rule has no webhook secret configured")

    if not x_webhook_secret or not verify_webhook_secret(x_webhook_secret, expected_secret):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    # Build trigger context with webhook payload
    trigger = TriggerContext(
        trigger_type="webhook",
        sensor_id=rule.primary_sensor_id,
        webhook_payload=payload or {},
    )

    # Gather media from primary sensor if available
    if rule.primary_sensor_id and hasattr(request.app.state, "event_aggregator"):
        media_paths = await request.app.state.event_aggregator.get_recent_images(
            rule.primary_sensor_id, limit=3
        )
        trigger.media_paths = media_paths

    pipeline_executor = request.app.state.pipeline_executor
    execution = await pipeline_executor.execute(rule, trigger, db)

    logger.info(
        "webhook_triggered",
        rule_id=rule_id,
        rule_name=rule.name,
        execution_id=execution.id,
    )

    return {
        "execution_id": execution.id,
        "status": execution.status,
    }


@router.post(
    "/{rule_id}/generate-secret",
    dependencies=[Depends(require_permission("rules:write"))],
    response_model=WebhookSecretOut,
)
async def regenerate_webhook_secret(
    rule_id: int,
    db: Session = Depends(get_db),
):
    """Generate or regenerate the webhook secret for a rule."""
    rule = db.query(Rule).filter(Rule.id == rule_id, Rule.filter_active()).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found or is a gate rule")

    new_secret = generate_webhook_secret()
    if not rule.webhook_config:
        rule.webhook_config = {}
    rule.webhook_config = {**rule.webhook_config, "secret": new_secret}
    db.commit()

    return {"secret": new_secret}
