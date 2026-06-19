"""Guided-task metrics endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from backend.core.auth import AuthContext, require_permission
from backend.routers.dependencies import get_guided_metrics_service
from backend.schemas.guided_metrics import (
    GuidedAbandonmentEnvelope,
    GuidedAttemptsPerStepEnvelope,
    GuidedCompletionSummaryEnvelope,
    GuidedEscalationBreakdownEnvelope,
    GuidedGateCostSummaryEnvelope,
    GuidedMetricsDashboardEnvelope,
    GuidedTimeOfDayEnvelope,
    GuidedTimeToCompleteEnvelope,
    GuidedVisionAgreementEnvelope,
    GuidedWatchSummaryEnvelope,
)
from backend.services.guided_task.metrics_service import GuidedMetricsService

router = APIRouter(prefix="/guided-metrics", tags=["guided-metrics"])


@router.get("/completion", response_model=GuidedCompletionSummaryEnvelope)
def get_guided_completion_summary(
    person_id: str = Query(min_length=1),
    routine_id: int | None = Query(default=None, ge=1),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    svc: GuidedMetricsService = Depends(get_guided_metrics_service),
    _auth: AuthContext = Depends(require_permission("guided_metrics:read")),
) -> GuidedCompletionSummaryEnvelope:
    return svc.completion_summary(
        person_id=person_id,
        routine_id=routine_id,
        since=since,
        until=until,
    )


@router.get("/attempts-per-step", response_model=GuidedAttemptsPerStepEnvelope)
def get_guided_attempts_per_step(
    person_id: str = Query(min_length=1),
    routine_id: int | None = Query(default=None, ge=1),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    svc: GuidedMetricsService = Depends(get_guided_metrics_service),
    _auth: AuthContext = Depends(require_permission("guided_metrics:read")),
) -> GuidedAttemptsPerStepEnvelope:
    return svc.attempts_per_step(
        person_id=person_id,
        routine_id=routine_id,
        since=since,
        until=until,
    )


@router.get("/time-to-complete", response_model=GuidedTimeToCompleteEnvelope)
def get_guided_time_to_complete(
    person_id: str = Query(min_length=1),
    routine_id: int | None = Query(default=None, ge=1),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    svc: GuidedMetricsService = Depends(get_guided_metrics_service),
    _auth: AuthContext = Depends(require_permission("guided_metrics:read")),
) -> GuidedTimeToCompleteEnvelope:
    return svc.time_to_complete(
        person_id=person_id,
        routine_id=routine_id,
        since=since,
        until=until,
    )


@router.get("/abandonment", response_model=GuidedAbandonmentEnvelope)
def get_guided_abandonment(
    person_id: str = Query(min_length=1),
    routine_id: int | None = Query(default=None, ge=1),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    svc: GuidedMetricsService = Depends(get_guided_metrics_service),
    _auth: AuthContext = Depends(require_permission("guided_metrics:read")),
) -> GuidedAbandonmentEnvelope:
    return svc.abandonment(person_id=person_id, routine_id=routine_id, since=since, until=until)


@router.get("/escalation-breakdown", response_model=GuidedEscalationBreakdownEnvelope)
def get_guided_escalation_breakdown(
    person_id: str = Query(min_length=1),
    routine_id: int | None = Query(default=None, ge=1),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    svc: GuidedMetricsService = Depends(get_guided_metrics_service),
    _auth: AuthContext = Depends(require_permission("guided_metrics:read")),
) -> GuidedEscalationBreakdownEnvelope:
    return svc.escalation_breakdown(
        person_id=person_id,
        routine_id=routine_id,
        since=since,
        until=until,
    )


@router.get("/vision-agreement", response_model=GuidedVisionAgreementEnvelope)
def get_guided_vision_agreement(
    person_id: str = Query(min_length=1),
    routine_id: int | None = Query(default=None, ge=1),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    svc: GuidedMetricsService = Depends(get_guided_metrics_service),
    _auth: AuthContext = Depends(require_permission("guided_metrics:read")),
) -> GuidedVisionAgreementEnvelope:
    return svc.vision_agreement(
        person_id=person_id,
        routine_id=routine_id,
        since=since,
        until=until,
    )


@router.get("/time-of-day", response_model=GuidedTimeOfDayEnvelope)
def get_guided_time_of_day(
    person_id: str = Query(min_length=1),
    routine_id: int | None = Query(default=None, ge=1),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    svc: GuidedMetricsService = Depends(get_guided_metrics_service),
    _auth: AuthContext = Depends(require_permission("guided_metrics:read")),
) -> GuidedTimeOfDayEnvelope:
    return svc.time_of_day(person_id=person_id, routine_id=routine_id, since=since, until=until)


@router.get("/dashboard", response_model=GuidedMetricsDashboardEnvelope)
def get_guided_metrics_dashboard(
    person_id: str = Query(min_length=1),
    routine_id: int | None = Query(default=None, ge=1),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    svc: GuidedMetricsService = Depends(get_guided_metrics_service),
    _auth: AuthContext = Depends(require_permission("guided_metrics:read")),
) -> GuidedMetricsDashboardEnvelope:
    return svc.dashboard(person_id=person_id, routine_id=routine_id, since=since, until=until)


@router.get("/watch-summary", response_model=GuidedWatchSummaryEnvelope)
def get_guided_watch_summary(
    person_id: str = Query(min_length=1),
    routine_id: int | None = Query(default=None, ge=1),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    svc: GuidedMetricsService = Depends(get_guided_metrics_service),
    _auth: AuthContext = Depends(require_permission("guided_metrics:read")),
) -> GuidedWatchSummaryEnvelope:
    return svc.watch_summary(person_id=person_id, routine_id=routine_id, since=since, until=until)


@router.get("/gate-cost-summary", response_model=GuidedGateCostSummaryEnvelope)
def get_guided_gate_cost_summary(
    person_id: str = Query(min_length=1),
    routine_id: int | None = Query(default=None, ge=1),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    svc: GuidedMetricsService = Depends(get_guided_metrics_service),
    _auth: AuthContext = Depends(require_permission("guided_metrics:read")),
) -> GuidedGateCostSummaryEnvelope:
    return svc.gate_cost_summary(person_id=person_id, routine_id=routine_id, since=since, until=until)
