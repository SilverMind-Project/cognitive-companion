"""Unit tests for the unified SignalsFeedService."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.signals.feed import SignalsFeedService, _extract_notification


def test_extract_notification_reads_notification_step_outputs():
    snapshot = {
        "steps": {
            "Notify caregiver": {
                "step_id": 7,
                "step_type": "notification",
                "outputs": {
                    "notification_dispatched": True,
                    "notification_severity": "emergency",
                    "notification_message": "Fall detected in bathroom",
                    "notification_room_name": "bathroom",
                },
            },
            "Some logic": {"step_type": "condition", "outputs": {"result": True}},
        }
    }
    notif = _extract_notification(snapshot)
    assert notif == {
        "severity": "emergency",
        "message": "Fall detected in bathroom",
        "room_name": "bathroom",
    }


def test_notification_step_output_survives_apply_step_result_to_feed():
    """End-to-end contract: the notification step's result_data, merged via the
    canonical apply_step_result into the persisted pipeline snapshot, is
    recoverable by the feed's _extract_notification.

    This is the join the per-link tests don't cover: step_type must be
    "notification" and the outputs key names must match across both ends.
    """
    from backend.services.pipeline_data_manager import apply_step_result

    # The exact shape NotificationHandler.execute returns on dispatch.
    result_data = {
        "notification_dispatched": True,
        "notification_channels": {"telegram": True},
        "notification_severity": "emergency",
        "notification_message": "Fall detected in bathroom",
        "notification_room_name": "bathroom",
    }
    snapshot: dict = {}
    apply_step_result(
        snapshot,
        step_id=1,
        step_type="notification",
        label="Notify caregiver",
        result_data=result_data,
    )

    notif = _extract_notification(snapshot)
    assert notif == {
        "severity": "emergency",
        "message": "Fall detected in bathroom",
        "room_name": "bathroom",
    }


def test_extract_notification_none_when_not_dispatched():
    snapshot = {
        "steps": {
            "Notify": {
                "step_type": "notification",
                "outputs": {"notification_dispatched": False},
            }
        }
    }
    assert _extract_notification(snapshot) is None
    assert _extract_notification(None) is None
    assert _extract_notification({"steps": {}}) is None


@pytest.mark.asyncio
async def test_list_feed_unions_and_sorts_by_recency():
    # Pipeline-rule EventLog row that fired a notification.
    event_log = SimpleNamespace(
        id=42,
        rule_name="Bathroom watch",
        room_name="bathroom",
        timestamp=datetime(2026, 6, 3, 10, 0, tzinfo=UTC),
        pipeline_data_json={
            "steps": {
                "Notify": {
                    "step_type": "notification",
                    "outputs": {
                        "notification_dispatched": True,
                        "notification_severity": "warning",
                        "notification_message": "Long dwell",
                        "notification_room_name": "bathroom",
                    },
                }
            }
        },
    )
    db = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = [event_log]
    db.query.return_value.filter.return_value.all.return_value = []  # display names

    svc = SignalsFeedService(db_factory=lambda: db)

    cts_rows = [
        {
            "id": 1,
            "signal_id": "sig-1",
            "person_id": "alice",
            "signal_type": "bathroom_dwell_anomaly",
            "severity": "emergency",
            "context_json": {"room_name": "bathroom"},
            "received_at": "2026-06-03T11:00:00+00:00",
            "window_end": "2026-06-03T11:00:00+00:00",
            "acknowledged_at": None,
        }
    ]
    with patch(
        "backend.services.signals.feed.SignalStore.list_recent",
        new=AsyncMock(return_value=(cts_rows, 1)),
    ):
        feed = await svc.list_feed(window_hours=24, limit=50)

    assert [e.source for e in feed] == ["cts", "pipeline_rule"]  # cts is more recent
    cts, rule = feed
    assert cts.id == "cts:1"
    assert cts.severity == "emergency"
    assert cts.can_acknowledge is True
    assert rule.id == "rule:42"
    assert rule.source == "pipeline_rule"
    assert rule.severity == "warning"
    assert rule.kind == "Bathroom watch"
    assert rule.can_acknowledge is False


@pytest.mark.asyncio
async def test_severity_min_filters_lower_severities():
    db = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = []
    db.query.return_value.filter.return_value.all.return_value = []
    svc = SignalsFeedService(db_factory=lambda: db)

    cts_rows = [
        {
            "id": 1,
            "person_id": None,
            "signal_type": "x",
            "severity": "info",
            "context_json": {},
            "received_at": "2026-06-03T11:00:00+00:00",
            "window_end": None,
            "acknowledged_at": None,
        },
        {
            "id": 2,
            "person_id": None,
            "signal_type": "y",
            "severity": "emergency",
            "context_json": {},
            "received_at": "2026-06-03T11:30:00+00:00",
            "window_end": None,
            "acknowledged_at": None,
        },
    ]
    with patch(
        "backend.services.signals.feed.SignalStore.list_recent",
        new=AsyncMock(return_value=(cts_rows, 2)),
    ):
        feed = await svc.list_feed(severity_min="warning")

    assert [e.id for e in feed] == ["cts:2"]
