"""Pydantic wire models for webhook endpoints."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class WebhookPayload(BaseModel):
    """Arbitrary JSON payload from the webhook caller."""

    model_config = ConfigDict(extra="allow")
