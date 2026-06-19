"""Tests for callable (gate-only) rule exclusion across all touchpoints."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.core.auth import AuthContext, get_auth_context
from backend.core.database import get_db
from backend.mcp.server import get_rules, list_rules, trigger_rule
from backend.models.rule import Rule
from backend.routers.rules import router as rules_router
from backend.routers.webhooks import router as webhooks_router
from backend.schemas.rule_bundle import RuleBundle
from backend.services.rule_importer import bundle_to_rule
from backend.services.rules_engine import RulesEngine
from backend.services.telegram_trigger import TelegramTriggerService


def test_is_callable_property():
    r1 = Rule(name="Rule 1", trigger_types=["sensor_event"])
    assert r1.is_callable is False

    r2 = Rule(name="Rule 2", trigger_types=[])
    assert r2.is_callable is True


def test_callable_rule_not_in_default_rules_list(db_session: Session):
    # 1. Create a regular active rule
    active_rule = Rule(name="Active Rule", trigger_types=["sensor_event"])
    # 2. Create a callable rule
    callable_rule = Rule(name="Callable Gate Rule", trigger_types=[])

    db_session.add(active_rule)
    db_session.add(callable_rule)
    db_session.commit()

    # Set up client to request /rules
    app = FastAPI()
    async def override_get_db():
        yield db_session
    async def override_auth():
        return AuthContext(key="test", name="Test", permissions=["*"])

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_auth_context] = override_auth
    app.include_router(rules_router)
    client = TestClient(app)

    # Fetch default list (should exclude callable rule)
    resp = client.get("/rules")
    assert resp.status_code == 200
    names = [r["name"] for r in resp.json()]
    assert "Active Rule" in names
    assert "Callable Gate Rule" not in names

    # Fetch active only (should exclude callable rule)
    resp = client.get("/rules?callable=false")
    assert resp.status_code == 200
    names = [r["name"] for r in resp.json()]
    assert "Active Rule" in names
    assert "Callable Gate Rule" not in names

    # Fetch callable only (should return only the callable rule)
    resp = client.get("/rules?callable=true")
    assert resp.status_code == 200
    names = [r["name"] for r in resp.json()]
    assert "Active Rule" not in names
    assert "Callable Gate Rule" in names


def test_callable_rule_not_scheduled(db_session: Session):
    # Tests that scheduler doesn't query or schedule callable rules
    # Scheduler loads rules linked to cron trigger. We need to assert Rule.filter_active() excludes it.
    from backend.models.cron_trigger import CronTrigger, RuleCronTrigger

    # First insert the cron_triggers row so foreign key is satisfied
    ct = CronTrigger(id=1, name="Every minute", expression="* * * * *")
    db_session.add(ct)
    db_session.commit()

    callable_rule = Rule(name="Callable Cron Rule", trigger_types=[], enabled=True)
    db_session.add(callable_rule)
    db_session.commit()

    # Even if somehow linked to a cron trigger (which shouldn't happen, but test exclusion)
    link = RuleCronTrigger(rule_id=callable_rule.id, cron_trigger_id=1)
    db_session.add(link)
    db_session.commit()

    rule_ids = [row[0] for row in db_session.query(RuleCronTrigger.rule_id).filter(RuleCronTrigger.cron_trigger_id == 1).all()]
    assert callable_rule.id in rule_ids

    # Query using active rules filter
    rules = db_session.query(Rule).filter(Rule.id.in_(rule_ids), Rule.enabled.is_(True), Rule.filter_active()).all()
    assert len(rules) == 0


def test_callable_rule_not_matched_by_rules_engine(db_session: Session):
    # Rule with dementia_signal trigger type
    r1 = Rule(name="Active Rule 1", trigger_types=["dementia_signal"], enabled=True)
    # Callable rule (empty trigger_types)
    r2 = Rule(name="Callable Rule 1", trigger_types=[], enabled=True)
    db_session.add(r1)
    db_session.add(r2)
    db_session.commit()

    engine = RulesEngine(tz_name="America/New_York")

    # Generic rules evaluation
    matched = engine.get_matching_rules_for_event(
        event={"kind": "dementia_signal", "payload": {}},
        trigger_type="dementia_signal",
        db=db_session,
    )
    names = [r.name for r in matched]
    assert "Active Rule 1" in names
    assert "Callable Rule 1" not in names


def test_callable_rule_not_telegram_or_webhook_target(db_session: Session):
    # 1. Webhook trigger test
    callable_rule = Rule(
        name="Callable Webhook Rule",
        trigger_types=[],
        enabled=True,
        webhook_config={"secret": "my-secret"},
    )
    db_session.add(callable_rule)
    db_session.commit()

    app = FastAPI()
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    app.include_router(webhooks_router)
    client = TestClient(app)

    # Try to trigger webhook (should fail as not found/callable)
    resp = client.post(
        f"/{callable_rule.id}/trigger",
        headers={"X-Webhook-Secret": "my-secret"},
        json={},
    )
    assert resp.status_code == 404

    # Try to regenerate secret (should fail as not found/callable)
    resp = client.post(f"/{callable_rule.id}/generate-secret")
    assert resp.status_code == 404

    # 2. Telegram trigger test
    # Even if rule is enabled, because it has trigger_types = [], it shouldn't load in TelegramTriggerService
    trigger_service = TelegramTriggerService(
        telegram_client=MagicMock(),
        pipeline_executor=MagicMock(),
        db_session_factory=lambda: db_session,
    )
    loaded = trigger_service._load_telegram_rules()
    assert all(r.id != callable_rule.id for r in loaded)


def test_rule_importer_preserves_empty_trigger_types(db_session: Session):
    bundle_data = {
        "schema_version": 2,
        "app_version": "2.0.0",
        "rule": {
            "name": "Imported Gate Rule",
            "enabled": True,
            "trigger_types": [],  # empty trigger types
            "cool_off_minutes": 5,
            "max_daily_triggers": 3,
            "max_concurrent_executions": 1,
            "execution_timeout_minutes": 5,
        },
        "steps": [],
        "edges": [],
        "contexts": [],
        "dependencies": [],
    }

    bundle = RuleBundle(**bundle_data)
    report = bundle_to_rule(bundle, db_session, app_version="2.0.0")
    assert report.rule_id is not None

    db_session.commit()
    rule = db_session.get(Rule, report.rule_id)
    assert rule is not None
    assert rule.trigger_types == []
    assert rule.is_callable is True


@pytest.mark.asyncio
async def test_mcp_rule_tools_exclude_callable(db_session: Session, monkeypatch):
    # Mock MCP server's _svc.db_factory to return our db_session
    mock_svc = MagicMock()
    mock_svc.db_factory.return_value = db_session
    monkeypatch.setattr("backend.mcp.server._svc", mock_svc)

    # Mock the pipeline executor module-level attribute in scheduler.py
    monkeypatch.setattr("backend.services.scheduler._pipeline_executor", MagicMock())

    callable_rule = Rule(name="Callable MCP Rule", trigger_types=[], enabled=True)
    db_session.add(callable_rule)
    db_session.commit()

    # Call get_rules MCP tool
    rules = await get_rules(enabled_only=False)
    assert all(r["id"] != callable_rule.id for r in rules)

    # Call list_rules MCP tool
    rules_list = await list_rules()
    assert all(r["id"] != callable_rule.id for r in rules_list)

    # Call trigger_rule MCP tool (should return error)
    res = await trigger_rule(rule_id=callable_rule.id)
    assert "error" in res
    assert "not found" in res["error"]
