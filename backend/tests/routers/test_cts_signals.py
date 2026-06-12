"""Integration tests for the CTS signals router."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.config import Settings
from backend.core.database import get_db
from backend.core.exceptions import register_exception_handlers
from backend.routers.cts_signals import _get_signal_store, router
from backend.services.cts.signal_store import SignalStore

_BASE_SIGNAL = {
    "person_id": "grandma",
    "signal_type": "pacing",
    "severity": "warning",
    "window_start": "2026-04-23T10:00:00+00:00",
    "window_end": "2026-04-23T10:30:00+00:00",
    "value": 7.0,
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _missing_db_factory():
    raise RuntimeError("CTS signal store was used without a database fixture")


def _build_app(db_factory=None, cts_enabled: bool = True):
    """Return (TestClient, SignalStore) backed by the shared PostgreSQL fixture."""
    cfg = Settings.from_dict({"cts": {"enabled": cts_enabled}})
    store = SignalStore(db_factory=db_factory or _missing_db_factory)

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="tester", permissions=["*"]
    )
    app.dependency_overrides[_get_signal_store] = lambda: store
    if db_factory is not None:

        def _override_get_db():
            db = db_factory()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = _override_get_db

    patcher = patch("backend.routers.cts_deps.settings", cfg)
    patcher.start()
    return TestClient(app), store, patcher


@pytest.fixture
def client_and_store(db_factory):
    c, s, p = _build_app(db_factory=db_factory, cts_enabled=True)
    yield c, s
    p.stop()


@pytest.fixture
def client_off(db_factory):
    c, _, p = _build_app(db_factory=db_factory, cts_enabled=False)
    yield c
    p.stop()


# ---------------------------------------------------------------------------
# CTS disabled guard
# ---------------------------------------------------------------------------


class TestCTSDisabledGuard:
    def test_list_signals_disabled(self, client_off: TestClient):
        r = client_off.get("/api/v1/cts/signals")
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "cts.disabled"

    def test_ack_disabled(self, client_off: TestClient):
        r = client_off.post("/api/v1/cts/signals/1/ack")
        assert r.status_code == 404

    def test_summary_disabled(self, client_off: TestClient):
        r = client_off.get("/api/v1/cts/signals/summary")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /cts/signals
# ---------------------------------------------------------------------------


class TestListSignals:
    def test_empty_list(self, client_and_store):
        client, _ = client_and_store
        r = client.get("/api/v1/cts/signals")
        assert r.status_code == 200
        body = r.json()
        assert body["signals"] == []
        assert body["count"] == 0

    def test_returns_inserted_signal(self, client_and_store):
        client, store = client_and_store
        asyncio.run(store.insert(_BASE_SIGNAL))
        r = client.get("/api/v1/cts/signals")
        assert r.status_code == 200
        assert r.json()["count"] == 1

    def test_filter_by_person_id(self, client_and_store):
        client, store = client_and_store
        asyncio.run(store.insert(_BASE_SIGNAL))
        asyncio.run(store.insert({**_BASE_SIGNAL, "person_id": "dad"}))
        r = client.get("/api/v1/cts/signals", params={"person_id": "grandma"})
        assert r.status_code == 200
        assert all(s["person_id"] == "grandma" for s in r.json()["signals"])

    def test_invalid_window_hours_rejected(self, client_and_store):
        client, _ = client_and_store
        r = client.get("/api/v1/cts/signals", params={"window_hours": 0})
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# POST /cts/signals/{signal_id}/ack
# ---------------------------------------------------------------------------


_EXPERIMENTAL_SIGNAL = {
    **_BASE_SIGNAL,
    "signal_type": "agitation_index",
    "evidence_grade": "experimental",
}


class TestAcknowledgeSignal:
    def test_ack_existing_signal(self, client_and_store):
        client, store = client_and_store
        sid = asyncio.run(store.insert(_BASE_SIGNAL))
        r = client.post(f"/api/v1/cts/signals/{sid}/ack")
        assert r.status_code == 200
        assert r.json()["acknowledged"] is True
        assert r.json()["signal_id"] == sid

    def test_ack_nonexistent_returns_404(self, client_and_store):
        client, _ = client_and_store
        r = client.post("/api/v1/cts/signals/99999/ack")
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "signal.not_found"

    def test_ack_with_feedback_round_trip(self, client_and_store):
        client, store = client_and_store
        sid = asyncio.run(store.insert(_EXPERIMENTAL_SIGNAL))
        r = client.post(f"/api/v1/cts/signals/{sid}/ack", json={"feedback": "accurate"})
        assert r.status_code == 200
        assert r.json()["acknowledged"] is True
        rows, _ = asyncio.run(store.list_recent())
        assert rows[0]["feedback"] == "accurate"

    def test_feedback_ignored_for_non_experimental(self, client_and_store):
        client, store = client_and_store
        sid = asyncio.run(store.insert(_BASE_SIGNAL))
        r = client.post(f"/api/v1/cts/signals/{sid}/ack", json={"feedback": "accurate"})
        assert r.status_code == 200
        rows, _ = asyncio.run(store.list_recent())
        assert rows[0]["feedback"] is None

    def test_invalid_feedback_rejected(self, client_and_store):
        client, store = client_and_store
        sid = asyncio.run(store.insert(_EXPERIMENTAL_SIGNAL))
        r = client.post(f"/api/v1/cts/signals/{sid}/ack", json={"feedback": "yes_please"})
        assert r.status_code == 422
        assert r.json()["detail"]["code"] == "signal.invalid_feedback"

    def test_ack_without_feedback_body_still_works(self, client_and_store):
        client, store = client_and_store
        sid = asyncio.run(store.insert(_BASE_SIGNAL))
        r = client.post(f"/api/v1/cts/signals/{sid}/ack", json={})
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# GET /cts/signals/unacknowledged
# ---------------------------------------------------------------------------


class TestListUnacknowledged:
    def test_returns_unacknowledged(self, client_and_store):
        client, store = client_and_store
        asyncio.run(store.insert(_BASE_SIGNAL))
        r = client.get("/api/v1/cts/signals/unacknowledged")
        assert r.status_code == 200
        assert r.json()["count"] == 1

    def test_excludes_acknowledged(self, client_and_store):
        client, store = client_and_store
        sid = asyncio.run(store.insert(_BASE_SIGNAL))
        asyncio.run(store.acknowledge(sid))
        r = client.get("/api/v1/cts/signals/unacknowledged")
        assert r.status_code == 200
        assert r.json()["count"] == 0


# ---------------------------------------------------------------------------
# GET /cts/signals/summary
# ---------------------------------------------------------------------------


class TestGetSummary:
    def test_empty_summary(self, client_and_store):
        client, _ = client_and_store
        r = client.get("/api/v1/cts/signals/summary")
        assert r.status_code == 200
        assert r.json()["total_signals"] == 0

    def test_summary_after_insert(self, client_and_store):
        client, store = client_and_store
        asyncio.run(store.insert(_BASE_SIGNAL))
        r = client.get("/api/v1/cts/signals/summary")
        assert r.status_code == 200
        assert r.json()["total_signals"] == 1


# ---------------------------------------------------------------------------
# GET /cts/signals/trend/{person_id}
# ---------------------------------------------------------------------------


class TestGetTrend:
    def test_trend_returns_days(self, client_and_store):
        client, _ = client_and_store
        r = client.get("/api/v1/cts/signals/trend/grandma", params={"days": 3})
        assert r.status_code == 200
        body = r.json()
        assert body["person_id"] == "grandma"
        assert len(body["trend"]) == 3

    def test_invalid_days_rejected(self, client_and_store):
        client, _ = client_and_store
        r = client.get("/api/v1/cts/signals/trend/grandma", params={"days": 0})
        assert r.status_code == 422
