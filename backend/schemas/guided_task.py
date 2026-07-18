"""Guided-task routine CRUD and caregiver takeover schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Routine CRUD
# ---------------------------------------------------------------------------


class RoutineStepIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ord: int = Field(ge=0)
    prompt_template: str = Field(min_length=1)
    completion_gate: dict[str, Any] = Field(default_factory=lambda: {"kinds": ["response"]})
    skip_condition: dict[str, Any] | None = None
    camera_ids: list[str] | None = None
    zone_id: int | None = None
    min_duration_s: int | None = Field(default=None, ge=0)
    step_timeout_s_override: int | None = Field(default=None, ge=1)
    max_step_attempts_override: int | None = Field(default=None, ge=1)
    is_safety_critical: bool = False

    @field_validator("completion_gate", mode="before")
    @classmethod
    def validate_completion_gate(cls, v: Any) -> Any:
        if not isinstance(v, dict):
            return v

        v = dict(v)
        vision = v.get("vision") or v.get("vision_confirm")
        if isinstance(vision, dict):
            legacy_keys = []
            if "camera_ids" in vision:
                legacy_keys.append("camera_ids")
            if "description" in vision:
                legacy_keys.append("description")

            if legacy_keys:
                import logging

                logging.getLogger("backend.schemas.guided_task").warning(
                    f"legacy_vision_gate_keys_ignored: {legacy_keys}"
                )
                for k in legacy_keys:
                    vision.pop(k, None)

            new_vision = {}
            if "gate_graph_rule_id" in vision:
                new_vision["gate_graph_rule_id"] = vision["gate_graph_rule_id"]

            confirm = vision.get("confirm")
            if isinstance(confirm, dict):
                new_vision["confirm"] = {
                    "window_s": confirm.get("window_s"),
                    "max_frames": confirm.get("max_frames"),
                    "min_confidence": confirm.get("min_confidence"),
                    "min_interval_s": confirm.get("min_interval_s"),
                    "model_id": confirm.get("model_id"),
                    "max_disagreements": confirm.get("max_disagreements"),
                    "on_max_disagreements": confirm.get("on_max_disagreements"),
                }
            elif "confirm" in vision:
                new_vision["confirm"] = confirm

            watch = vision.get("watch")
            if isinstance(watch, dict):
                new_vision["watch"] = {
                    "enabled": watch.get("enabled"),
                    "tick_s": watch.get("tick_s"),
                    "window_s": watch.get("window_s"),
                    "max_frames": watch.get("max_frames"),
                    "model_id": watch.get("model_id"),
                    "auto_advance": watch.get("auto_advance"),
                    "auto_advance_k": watch.get("auto_advance_k"),
                }
            elif "watch" in vision:
                new_vision["watch"] = watch

            for k, val in vision.items():
                if k not in {"confirm", "watch", "gate_graph_rule_id", "camera_ids", "description"}:
                    new_vision[k] = val

            v["vision"] = new_vision
            if "vision_confirm" in v:
                v.pop("vision_confirm", None)

        return v


class RoutineStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    routine_id: int
    ord: int
    prompt_template: str
    completion_gate: dict[str, Any]
    skip_condition: dict[str, Any] | None
    camera_ids: list[str] | None
    zone_id: int | None
    min_duration_s: int | None
    step_timeout_s_override: int | None
    max_step_attempts_override: int | None
    is_safety_critical: bool


class RoutineCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=256)
    person_id: str = Field(min_length=1, max_length=64)
    is_enabled: bool = True
    language_override: str | None = Field(default=None, max_length=16)
    voice_override: str | None = Field(default=None, max_length=64)
    system_instruction_override: str | None = None
    step_timeout_s_override: int | None = Field(default=None, ge=1)
    max_step_attempts_override: int | None = Field(default=None, ge=1)
    resume_grace_s_override: int | None = Field(default=None, ge=0)
    escalation_channels_override: list[str] | None = None
    summon_channels_override: list[str] | None = None
    rephrase_via_override: str | None = Field(default=None, max_length=16)


class RoutineUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=256)
    is_enabled: bool | None = None
    language_override: str | None = Field(default=None, max_length=16)
    voice_override: str | None = Field(default=None, max_length=64)
    system_instruction_override: str | None = None
    step_timeout_s_override: int | None = Field(default=None, ge=1)
    max_step_attempts_override: int | None = Field(default=None, ge=1)
    resume_grace_s_override: int | None = Field(default=None, ge=0)
    escalation_channels_override: list[str] | None = None
    summon_channels_override: list[str] | None = None
    rephrase_via_override: str | None = Field(default=None, max_length=16)


class RoutineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    person_id: str
    is_enabled: bool
    language_override: str | None
    voice_override: str | None
    system_instruction_override: str | None
    step_timeout_s_override: int | None
    max_step_attempts_override: int | None
    resume_grace_s_override: int | None
    escalation_channels_override: list[str] | None
    summon_channels_override: list[str] | None
    rephrase_via_override: str | None
    created_at: datetime
    updated_at: datetime
    step_count: int = 0


class RoutineDetailOut(BaseModel):
    routine: RoutineOut
    steps: list[RoutineStepOut]


class RoutineListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[RoutineOut]
    total: int


class RoutineStepsReplaceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: list[RoutineStepIn]


class RoutineTestRunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    surface_id: str | None = None


class GuidedSessionListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[GuidedSessionOut]
    total: int


class GuidedSessionSayIn(BaseModel):
    model_config = {"extra": "forbid"}

    text: str = Field(min_length=1, max_length=2000)


class GuidedSessionActionOut(BaseModel):
    status: str
    session_id: int


class GuidedSessionAdvanceOut(BaseModel):
    advanced: bool
    done: bool = False
    reason: str
    next_step: dict[str, Any] | None = None


class GuidedSessionTurnOut(BaseModel):
    actor: str
    content: str
    timestamp: str | None = None
    metadata: dict[str, Any] | None = None


class GuidedSessionEventOut(BaseModel):
    id: int
    at: datetime
    kind: str
    step_ord: int | None = None
    actor: str | None = None
    detail: dict[str, Any] | None = None


class GuidedSessionStepOut(BaseModel):
    ord: int
    prompt_text: str
    completion_gate: dict[str, Any]
    is_safety_critical: bool


class GuidedSessionOut(BaseModel):
    id: int
    routine_id: int
    person_id: str
    execution_id: int | None = None
    surface_id: str | None = None
    conversation_session_id: int | None = None
    status: str
    current_step_ord: int
    attempts: int
    started_at: datetime
    last_activity_at: datetime
    completed_at: datetime | None = None
    outcome: str | None = None


class GuidedSessionDetailOut(BaseModel):
    session: GuidedSessionOut
    current_step: GuidedSessionStepOut | None = None
    recent_events: list[GuidedSessionEventOut]
    recent_transcript: list[GuidedSessionTurnOut]
