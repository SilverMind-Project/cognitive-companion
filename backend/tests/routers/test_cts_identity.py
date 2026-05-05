"""Integration tests for the CTS identity corrections router."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

import backend.models  # noqa: F401
from backend.core.auth import AuthContext, get_auth_context
from backend.core.config import Settings
from backend.core.database import reset_default_database
from backend.core.exceptions import register_exception_handlers
from backend.models.person import HouseholdMember, PersonLocationHistory


def _build_app(db_engine: Engine, cts_enabled: bool = True, orchestrator=None):
    cfg = Settings.from_dict({"cts": {"enabled": cts_enabled}})

    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)

    def _session():
        return Session()

    from backend.routers import cts_identity as cts_identity_mod

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(cts_identity_mod.router, prefix="/api/v1")
    app.state.orchestrator_client = orchestrator
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="tester", permissions=["*"]
    )

    settings_patch = patch.object(cts_identity_mod, "settings", cfg)
    session_patch = patch.object(cts_identity_mod, "get_session", _session)
    settings_patch.start()
    session_patch.start()
    patchers = (settings_patch, session_patch)
    return TestClient(app), Session, patchers


@pytest.fixture(autouse=True)
def _reset_db():
    yield
    reset_default_database()


class TestCTSDisabledGuard:
    def test_global_tracks_disabled(self, db_engine):
        client, _, patchers = _build_app(db_engine, cts_enabled=False)
        try:
            r = client.get("/api/v1/cts/identity/global_tracks")
            assert r.status_code == 404
            assert r.json()["detail"]["code"] == "cts.disabled"
        finally:
            for p in patchers:
                p.stop()

    def test_correction_disabled(self, db_engine):
        client, _, patchers = _build_app(db_engine, cts_enabled=False)
        try:
            r = client.post(
                "/api/v1/cts/identity/corrections",
                json={"global_track_id": "gt-1", "new_identity_id": None},
            )
            assert r.status_code == 404
        finally:
            for p in patchers:
                p.stop()


class TestGlobalTracksProxy:
    def test_forwards_to_orchestrator(self, db_engine):
        orchestrator = AsyncMock()
        orchestrator.get_global_tracks = AsyncMock(
            return_value=[
                {
                    "global_track_id": "gt-1",
                    "current_identity_id": "grandma",
                    "camera_ids": ["kitchen-1"],
                }
            ]
        )
        client, _, patchers = _build_app(db_engine, cts_enabled=True, orchestrator=orchestrator)
        try:
            r = client.get("/api/v1/cts/identity/global_tracks")
            assert r.status_code == 200
            body = r.json()
            assert body["count"] == 1
            assert body["tracks"][0]["global_track_id"] == "gt-1"
        finally:
            for p in patchers:
                p.stop()


class TestCorrectionProxy:
    def test_apply_correction_calls_override(self, db_engine):
        orchestrator = AsyncMock()
        orchestrator.manual_identity_override = AsyncMock(
            return_value={
                "revision_id": "rev-1",
                "global_track_id": "gt-1",
                "previous_identity_id": "grandma",
                "new_identity_id": "grandpa",
                "applied_at": datetime.now(UTC).isoformat(),
            }
        )
        client, _, patchers = _build_app(db_engine, cts_enabled=True, orchestrator=orchestrator)
        try:
            r = client.post(
                "/api/v1/cts/identity/corrections",
                json={
                    "global_track_id": "gt-1",
                    "new_identity_id": "grandpa",
                    "reason": "manual",
                },
            )
            assert r.status_code == 200
            assert r.json()["revision_id"] == "rev-1"
            orchestrator.manual_identity_override.assert_awaited_once()
            call = orchestrator.manual_identity_override.call_args
            assert call.kwargs["global_track_id"] == "gt-1"
            assert call.kwargs["new_identity_id"] == "grandpa"
            assert call.kwargs["actor"] == "tester"
        finally:
            for p in patchers:
                p.stop()

    def test_merge_uses_override_with_merge_reason(self, db_engine):
        orchestrator = AsyncMock()
        orchestrator.manual_identity_override = AsyncMock(
            return_value={"revision_id": "rev-m", "applied_at": "x"}
        )
        client, _, patchers = _build_app(db_engine, cts_enabled=True, orchestrator=orchestrator)
        try:
            r = client.post(
                "/api/v1/cts/identity/merges",
                json={
                    "global_track_id": "gt-1",
                    "from_identity_id": "guest_a",
                    "to_identity_id": "grandma",
                },
            )
            assert r.status_code == 200
            call = orchestrator.manual_identity_override.call_args
            assert call.kwargs["new_identity_id"] == "grandma"
            assert call.kwargs["evidence"] == {
                "merge_from": "guest_a",
                "merge_to": "grandma",
            }
        finally:
            for p in patchers:
                p.stop()


class TestRevisionsAuditLog:
    def test_aggregates_rewritten_rows_by_revision(self, db_engine):
        orchestrator = AsyncMock()
        client, Session, patchers = _build_app(
            db_engine, cts_enabled=True, orchestrator=orchestrator
        )
        try:
            db = Session()
            try:
                db.add(HouseholdMember(id="grandma", name="Grandma"))
                now = datetime.now(UTC)
                db.add(
                    PersonLocationHistory(
                        person_id="grandma",
                        room_name="kitchen",
                        entered_at=now - timedelta(minutes=10),
                        source="cts",
                        global_track_id="gt-1",
                        superseded_by_revision_id="rev-1",
                    )
                )
                db.add(
                    PersonLocationHistory(
                        person_id="grandma",
                        room_name="kitchen",
                        entered_at=now - timedelta(minutes=5),
                        source="cts",
                        global_track_id="gt-1",
                        superseded_by_revision_id="rev-1",
                    )
                )
                db.commit()
            finally:
                db.close()

            r = client.get("/api/v1/cts/identity/revisions")
            assert r.status_code == 200
            body = r.json()
            assert body["count"] == 1
            assert body["revisions"][0]["revision_id"] == "rev-1"
            assert body["revisions"][0]["rewritten_rows"] == 2
        finally:
            for p in patchers:
                p.stop()
