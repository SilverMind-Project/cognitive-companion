"""Response schemas for small single-endpoint surfaces.

These are endpoints whose one response shape does not justify a module of its own: device
ingest, webhook acks, image render acks, conversation turns, and the liveness probe.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from backend.schemas.common import OutSchema

# -- Health ------------------------------------------------------------------


class LivenessOut(OutSchema):
    """Root liveness probe. Must answer before auth config is trusted."""

    status: str
    version: str


# -- Device ingest -----------------------------------------------------------


class RecameraUploadOut(OutSchema):
    """Ack for a reCamera frame upload.

    ``object_name`` is absent when the frame was dropped by the label filter, in which case
    ``status`` is "filtered" and ``reason`` explains why.
    """

    status: str = Field(description='"accepted" | "filtered"')
    object_name: str | None = None
    reason: str | None = None


# -- Webhooks ----------------------------------------------------------------


class WebhookTriggerOut(OutSchema):
    """Ack for an inbound webhook that started a rule execution."""

    execution_id: int
    status: str


class WebhookSecretOut(OutSchema):
    """A freshly generated per-rule webhook secret. Shown once."""

    secret: str


# -- Image / e-ink -----------------------------------------------------------


class ImageRenderOut(OutSchema):
    """Ack for a render/reset against one or more e-ink devices."""

    status: str
    sensor_ids: list[str] = []


class TemplateImageUpdateOut(OutSchema):
    status: str
    template_id: int


class FontListOut(OutSchema):
    """Font files available to the e-ink renderer."""

    fonts: list[str] = []


# -- Conversations -----------------------------------------------------------


class RecentTurnsOut(OutSchema):
    """Recent conversation turns.

    ``session_id`` and ``message`` are optional: the endpoint omits the former and adds the
    latter when no session is available or supplied.
    """

    turns: list[dict[str, Any]] = []
    session_id: str | None = None
    message: str | None = None


# -- Pipeline image sources --------------------------------------------------


class SampleImageOut(OutSchema):
    """A sample frame for the image-crop step config UI."""

    image_url: str | None = None
    object_name: str
    source_type: str = Field(description='"recamera" | "cts"')
    source_id: str
    width: int | None = None
    height: int | None = None


# -- Interactive responses ---------------------------------------------------


class InteractiveResponseOut(OutSchema):
    """One recorded interactive response, with latency derived when both stamps exist."""

    id: int
    execution_id: int | None = None
    step_id: int | None = None
    channel: str
    action: str
    timestamp: str | None = None
    created_at: str | None = None
    raw_response_json: dict[str, Any] | None = None
    latency_ms: int | None = None
