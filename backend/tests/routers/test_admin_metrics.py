"""U6-T3 + U6-T5: admin_metrics — converted endpoint must return 503 on failure.

U6b converted admin_metrics from:
  _sum_counter: except Exception → return 0.0   (fake zero)
to:
  _sum_counter: no except        (raises)
  cts_metrics_endpoint: except → HTTPException(503)

Verifies:
- T3: failure path raises the typed error (503), never returns a fabricated 0.0
- T5: on dependency failure, the endpoint returns an explicit unavailable state
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.exceptions import register_exception_handlers
from backend.routers.admin_metrics import _sum_counter, router

# ---------------------------------------------------------------------------
# T3: _sum_counter raises on failure (no fabricated zero)
# ---------------------------------------------------------------------------


class TestSumCounterNeverFabricatesZero:
    def test_raises_on_counter_collect_failure(self):
        """Rule 15: _sum_counter must raise on failure, not return 0.0."""
        bad_counter = MagicMock()
        bad_counter.collect.side_effect = RuntimeError("prometheus broken")

        with pytest.raises(RuntimeError, match="prometheus broken"):
            _sum_counter(bad_counter)

    def test_returns_real_value_on_success(self):
        """Sanity: a healthy counter returns its actual value."""
        good_counter = MagicMock()
        sample = MagicMock()
        sample.samples = [MagicMock(value=42.0)]
        good_counter.collect.return_value = [sample]

        result = _sum_counter(good_counter)

        assert result == 42.0


# ---------------------------------------------------------------------------
# T5: endpoint returns 503 on dependency failure, not {"count": 0}
# ---------------------------------------------------------------------------


def _build_app() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="admin", permissions=["*"]
    )
    return TestClient(app, raise_server_exceptions=False)


class TestCtsMetricsEndpoint503OnFailure:
    def test_503_when_prometheus_counter_fails(self):
        """T5: endpoint must return 503, never a response with all zeros."""
        tc = _build_app()

        with patch(
            "backend.routers.admin_metrics.cts_metrics",
            MagicMock(
                cts_signals_received=MagicMock(
                    collect=MagicMock(side_effect=RuntimeError("counter broken"))
                )
            ),
        ):
            resp = tc.get("/api/v1/admin/cts-metrics")

        assert resp.status_code == 503
        body = resp.json()
        # The error body must not look like a valid metrics response.
        assert "signals_received" not in body
        assert "unavailable" in body.get("detail", "").lower()

    def test_200_on_success(self):
        """Sanity: endpoint returns 200 with real metrics when prometheus is healthy."""
        tc = _build_app()

        fake_counter = MagicMock()
        sample = MagicMock()
        sample.samples = [MagicMock(value=5.0)]
        fake_counter.collect.return_value = [sample]

        with patch(
            "backend.routers.admin_metrics.cts_metrics",
            MagicMock(
                cts_signals_received=fake_counter,
                cts_signals_persisted=fake_counter,
                cts_signals_decode_errors=fake_counter,
                cts_signals_dropped=fake_counter,
                cts_events_received=fake_counter,
                cts_events_persisted=fake_counter,
                cts_events_decode_errors=fake_counter,
                cts_events_dropped=fake_counter,
                cts_revisions_received=fake_counter,
                cts_revisions_persisted=fake_counter,
                cts_revisions_decode_errors=fake_counter,
                cts_revisions_dropped=fake_counter,
            ),
        ):
            resp = tc.get("/api/v1/admin/cts-metrics")

        assert resp.status_code == 200
        body = resp.json()
        assert body["signals_received"] == 5.0
