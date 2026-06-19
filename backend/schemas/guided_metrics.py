"""Guided-task metrics response envelopes."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GuidedMetricsWindow(BaseModel):
    model_config = ConfigDict(frozen=True)

    person_id: str
    routine_id: int | None = None
    since: datetime
    until: datetime


class GuidedOutcomeCount(BaseModel):
    model_config = ConfigDict(frozen=True)

    outcome: str
    count: int = Field(ge=0)


class GuidedCompletionSummaryEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True)

    window: GuidedMetricsWindow
    started: int = Field(ge=0)
    completed: int = Field(ge=0)
    completion_rate: float = Field(ge=0.0, le=1.0)
    outcomes: list[GuidedOutcomeCount]


class GuidedStepAttemptMetric(BaseModel):
    model_config = ConfigDict(frozen=True)

    step_ord: int
    average_attempts: float = Field(ge=0.0)
    max_attempts: int = Field(ge=0)
    retry_events: int = Field(ge=0)


class GuidedAttemptsPerStepEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True)

    window: GuidedMetricsWindow
    items: list[GuidedStepAttemptMetric]


class GuidedRoutineDurationMetric(BaseModel):
    model_config = ConfigDict(frozen=True)

    routine_id: int
    sessions: int = Field(ge=0)
    average_seconds: float = Field(ge=0.0)
    median_seconds: float = Field(ge=0.0)


class GuidedTimeToCompleteEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True)

    window: GuidedMetricsWindow
    items: list[GuidedRoutineDurationMetric]


class GuidedReasonCount(BaseModel):
    model_config = ConfigDict(frozen=True)

    reason: str
    count: int = Field(ge=0)


class GuidedAbandonmentEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True)

    window: GuidedMetricsWindow
    abandoned: int = Field(ge=0)
    started: int = Field(ge=0)
    abandonment_rate: float = Field(ge=0.0, le=1.0)
    reasons: list[GuidedReasonCount]


class GuidedEscalationMetric(BaseModel):
    model_config = ConfigDict(frozen=True)

    reason: str
    emergency: bool
    count: int = Field(ge=0)


class GuidedEscalationBreakdownEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True)

    window: GuidedMetricsWindow
    total: int = Field(ge=0)
    emergency_total: int = Field(ge=0)
    items: list[GuidedEscalationMetric]


class GuidedVisionAgreementEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True)

    window: GuidedMetricsWindow
    total: int = Field(ge=0)
    agreed: int = Field(ge=0)
    uncertain: int = Field(ge=0)
    agreement_rate: float = Field(ge=0.0, le=1.0)


class GuidedTimeOfDayBucket(BaseModel):
    model_config = ConfigDict(frozen=True)

    hour: int = Field(ge=0, le=23)
    started: int = Field(ge=0)
    completed: int = Field(ge=0)
    abandoned: int = Field(ge=0)


class GuidedTimeOfDayEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True)

    window: GuidedMetricsWindow
    timezone: str
    buckets: list[GuidedTimeOfDayBucket]


class GuidedWatchSummaryEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True)

    window: GuidedMetricsWindow
    total_runs: int = Field(ge=0)
    auto_advances: int = Field(ge=0)
    agreement_rate: float = Field(ge=0.0, le=1.0)
    average_model_calls: float = Field(ge=0.0)
    average_frames: float = Field(ge=0.0)
    average_latency_ms: float = Field(ge=0.0)


class GuidedGateCostMetric(BaseModel):
    model_config = ConfigDict(frozen=True)

    model_calls: int = Field(ge=0)
    frames: int = Field(ge=0)
    latency_ms: float = Field(ge=0.0)


class GuidedGateCostSummaryEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True)

    window: GuidedMetricsWindow
    confirm_cost: GuidedGateCostMetric
    watch_cost: GuidedGateCostMetric
    total_cost: GuidedGateCostMetric


class GuidedMetricsDashboardEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True)

    completion: GuidedCompletionSummaryEnvelope
    attempts_per_step: GuidedAttemptsPerStepEnvelope
    time_to_complete: GuidedTimeToCompleteEnvelope
    abandonment: GuidedAbandonmentEnvelope
    escalation_breakdown: GuidedEscalationBreakdownEnvelope
    vision_agreement: GuidedVisionAgreementEnvelope
    time_of_day: GuidedTimeOfDayEnvelope
    watch_summary: GuidedWatchSummaryEnvelope
    gate_cost_summary: GuidedGateCostSummaryEnvelope
