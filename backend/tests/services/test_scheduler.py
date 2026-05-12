"""Tests for the ``Scheduler`` class and the legacy module-level facade.

We avoid starting APScheduler's event loop: every test either inspects the
jobs added to ``scheduler.apscheduler`` synchronously, or invokes the
callback methods directly with awaited coroutines.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.cron_trigger import CronTrigger, RuleCronTrigger
from backend.models.pipeline import WorkflowExecution
from backend.models.rule import Rule
from backend.services import scheduler as scheduler_module
from backend.services.scheduler import (
    Scheduler,
    SchedulerBridge,
    reload_scheduled_rules,
    reset_default_scheduler,
    setup_scheduler,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def aggregator() -> MagicMock:
    agg = MagicMock()
    agg.cleanup_expired_media = AsyncMock()
    agg.get_recent_images = AsyncMock(return_value=["/tmp/frame.jpg"])
    return agg


@pytest.fixture
def pipeline_executor(aggregator) -> MagicMock:
    pe = MagicMock()
    pe.execute = AsyncMock()
    pe.resume = AsyncMock()
    pe._services = MagicMock()
    pe._services.event_aggregator = aggregator
    pe.event_aggregator = aggregator  # set directly for scheduler access
    return pe


@pytest.fixture(autouse=True)
def _reset_module_facade():
    yield
    reset_default_scheduler()


def _make_rule(db, **kwargs) -> Rule:
    defaults = {
        "name": kwargs.pop("name", "r"),
        "enabled": True,
        "trigger_types": kwargs.pop("trigger_types", ["sensor_event"]),
        "cool_off_minutes": 0,
        "max_daily_triggers": 0,
    }
    defaults.update(kwargs)
    rule = Rule(**defaults)
    db.add(rule)
    db.flush()
    return rule


def _make_cron_trigger(db, rule=None, **kwargs) -> CronTrigger:
    """Create a CronTrigger, optionally linked to *rule* via RuleCronTrigger."""
    ct = CronTrigger(
        name=kwargs.pop("name", "test-cron"),
        expression=kwargs.pop("expression", "*/5 * * * *"),
        timezone=kwargs.pop("timezone", "UTC"),
        enabled=kwargs.pop("enabled", True),
        **kwargs,
    )
    db.add(ct)
    db.flush()
    if rule is not None:
        db.add(RuleCronTrigger(rule_id=rule.id, cron_trigger_id=ct.id))
        db.flush()
    return ct


# ---------------------------------------------------------------------------
# Scheduler.configure()
# ---------------------------------------------------------------------------


def test_configure_adds_maintenance_job(db_factory, aggregator, pipeline_executor) -> None:
    s = Scheduler(aggregator, db_factory, pipeline_executor)
    s.configure()
    job_ids = {j.id for j in s.apscheduler.get_jobs()}
    assert "cleanup_expired_media" in job_ids


def test_configure_loads_rule_jobs(db_session, db_factory, aggregator, pipeline_executor) -> None:
    rule = _make_rule(db_session, name="rule-a")
    ct = _make_cron_trigger(db_session, rule=rule, expression="*/10 * * * *")
    db_session.commit()

    s = Scheduler(aggregator, db_factory, pipeline_executor)
    s.configure()
    job_ids = {j.id for j in s.apscheduler.get_jobs()}
    assert f"cron_{ct.id}" in job_ids


def test_configure_skips_invalid_cron(
    db_session, db_factory, aggregator, pipeline_executor
) -> None:
    rule = _make_rule(db_session, name="bad")
    ct = _make_cron_trigger(db_session, rule=rule, expression="not a cron")
    db_session.commit()

    s = Scheduler(aggregator, db_factory, pipeline_executor)
    s.configure()
    job_ids = {j.id for j in s.apscheduler.get_jobs()}
    assert f"cron_{ct.id}" not in job_ids


def test_configure_schedules_pending_resumes(
    db_session, db_factory, aggregator, pipeline_executor
) -> None:
    rule = _make_rule(db_session)
    execution = WorkflowExecution(
        rule_id=rule.id,
        status="waiting",
        resume_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(execution)
    db_session.commit()

    s = Scheduler(aggregator, db_factory, pipeline_executor)
    s.configure()
    job_ids = {j.id for j in s.apscheduler.get_jobs()}
    assert f"resume_{execution.id}" in job_ids


# ---------------------------------------------------------------------------
# Scheduler.reload_rules()
# ---------------------------------------------------------------------------


def test_reload_rules_removes_and_readds(
    db_session, db_factory, aggregator, pipeline_executor
) -> None:
    rule1 = _make_rule(db_session, name="r1")
    ct1 = _make_cron_trigger(db_session, rule=rule1)
    db_session.commit()

    s = Scheduler(aggregator, db_factory, pipeline_executor)
    s.configure()
    assert f"cron_{ct1.id}" in {j.id for j in s.apscheduler.get_jobs()}

    # Disable cron trigger 1 and add a new rule + trigger
    ct1.enabled = False
    rule2 = _make_rule(db_session, name="r2")
    ct2 = _make_cron_trigger(db_session, rule=rule2, expression="0 * * * *")
    db_session.commit()

    s.reload_rules()
    job_ids = {j.id for j in s.apscheduler.get_jobs()}
    assert f"cron_{ct1.id}" not in job_ids
    assert f"cron_{ct2.id}" in job_ids


# ---------------------------------------------------------------------------
# Scheduler.schedule_workflow_resume()
# ---------------------------------------------------------------------------


def test_schedule_workflow_resume_adds_job(db_factory, aggregator, pipeline_executor) -> None:
    s = Scheduler(aggregator, db_factory, pipeline_executor)
    s.schedule_workflow_resume(42, datetime.now(UTC) + timedelta(hours=1))
    assert "resume_42" in {j.id for j in s.apscheduler.get_jobs()}


# ---------------------------------------------------------------------------
# execute_periodic_rule
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_periodic_rule_noop_without_executor(db_factory, aggregator) -> None:
    s = Scheduler(aggregator, db_factory, pipeline_executor=None)
    await s.execute_periodic_rule(1)  # no-op, no crash


@pytest.mark.asyncio
async def test_execute_periodic_rule_missing_rule(
    db_factory, aggregator, pipeline_executor
) -> None:
    s = Scheduler(aggregator, db_factory, pipeline_executor)
    await s.execute_periodic_rule(9999)
    pipeline_executor.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_periodic_rule_disabled(
    db_session, db_factory, aggregator, pipeline_executor
) -> None:
    rule = _make_rule(db_session, enabled=False)
    ct = _make_cron_trigger(db_session, rule=rule)
    db_session.commit()

    s = Scheduler(aggregator, db_factory, pipeline_executor)
    await s.execute_periodic_rule(ct.id)
    pipeline_executor.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_periodic_rule_success(
    db_session, db_factory, aggregator, pipeline_executor
) -> None:
    rule = _make_rule(db_session, primary_sensor_id="cam1")
    ct = _make_cron_trigger(db_session, rule=rule)
    db_session.commit()

    s = Scheduler(aggregator, db_factory, pipeline_executor)
    await s.execute_periodic_rule(ct.id)
    pipeline_executor.execute.assert_awaited_once()
    trigger = pipeline_executor.execute.await_args.args[1]
    assert trigger.trigger_type == "cron"
    assert trigger.sensor_id == "cam1"
    assert trigger.media_paths == ["/tmp/frame.jpg"]


@pytest.mark.asyncio
async def test_execute_periodic_rule_skips_aggregator_fetch_without_sensor(
    db_session, db_factory, aggregator, pipeline_executor
) -> None:
    rule = _make_rule(db_session, primary_sensor_id=None)
    ct = _make_cron_trigger(db_session, rule=rule)
    db_session.commit()

    s = Scheduler(aggregator, db_factory, pipeline_executor)
    await s.execute_periodic_rule(ct.id)
    aggregator.get_recent_images.assert_not_awaited()
    pipeline_executor.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_periodic_rule_swallows_exception(
    db_session, db_factory, aggregator, pipeline_executor
) -> None:
    rule = _make_rule(db_session, primary_sensor_id="cam1")
    ct = _make_cron_trigger(db_session, rule=rule)
    db_session.commit()
    pipeline_executor.execute.side_effect = RuntimeError("boom")

    s = Scheduler(aggregator, db_factory, pipeline_executor)
    # Must not raise.
    await s.execute_periodic_rule(ct.id)


# ---------------------------------------------------------------------------
# resume_workflow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_workflow_noop_without_executor(db_factory, aggregator) -> None:
    s = Scheduler(aggregator, db_factory, pipeline_executor=None)
    await s.resume_workflow(1)


@pytest.mark.asyncio
async def test_resume_workflow_calls_executor(db_factory, aggregator, pipeline_executor) -> None:
    s = Scheduler(aggregator, db_factory, pipeline_executor)
    await s.resume_workflow(7)
    pipeline_executor.resume.assert_awaited_once()
    assert pipeline_executor.resume.await_args.args[0] == 7


@pytest.mark.asyncio
async def test_resume_workflow_swallows_exception(
    db_factory, aggregator, pipeline_executor
) -> None:
    pipeline_executor.resume.side_effect = RuntimeError("boom")
    s = Scheduler(aggregator, db_factory, pipeline_executor)
    await s.resume_workflow(7)  # must not raise


# ---------------------------------------------------------------------------
# SchedulerBridge
# ---------------------------------------------------------------------------


def test_bridge_wraps_scheduler_instance(db_factory, aggregator, pipeline_executor) -> None:
    s = Scheduler(aggregator, db_factory, pipeline_executor)
    bridge = SchedulerBridge(s)
    bridge.schedule_workflow_resume(11, datetime.now(UTC) + timedelta(minutes=5))
    assert "resume_11" in {j.id for j in s.apscheduler.get_jobs()}


def test_bridge_wraps_raw_apscheduler(db_factory, aggregator, pipeline_executor) -> None:
    s = Scheduler(aggregator, db_factory, pipeline_executor)
    bridge = SchedulerBridge(s.apscheduler)  # legacy path
    bridge.schedule_workflow_resume(12, datetime.now(UTC) + timedelta(minutes=5))
    assert "resume_12" in {j.id for j in s.apscheduler.get_jobs()}


# ---------------------------------------------------------------------------
# Module-level facade
# ---------------------------------------------------------------------------


def test_setup_scheduler_returns_apscheduler_and_populates_globals(
    db_session, db_factory, aggregator, pipeline_executor
) -> None:
    rule = _make_rule(db_session, name="facade")
    ct = _make_cron_trigger(db_session, rule=rule, expression="*/1 * * * *")
    db_session.commit()

    ap = setup_scheduler(aggregator, db_factory, pipeline_executor)
    assert scheduler_module._default_scheduler is not None
    assert scheduler_module._pipeline_executor is pipeline_executor
    assert scheduler_module._db_session_factory is db_factory
    job_ids = {j.id for j in ap.get_jobs()}
    assert f"cron_{ct.id}" in job_ids


def test_reload_scheduled_rules_delegates_to_default(
    db_session, db_factory, aggregator, pipeline_executor
) -> None:
    rule1 = _make_rule(db_session, name="fac-a")
    _make_cron_trigger(db_session, rule=rule1, expression="*/1 * * * *")
    db_session.commit()
    ap = setup_scheduler(aggregator, db_factory, pipeline_executor)

    rule2 = _make_rule(db_session, name="fac-b")
    ct2 = _make_cron_trigger(db_session, rule=rule2, expression="0 * * * *")
    db_session.commit()
    reload_scheduled_rules(ap, db_factory)

    assert f"cron_{ct2.id}" in {j.id for j in ap.get_jobs()}


def test_reload_scheduled_rules_legacy_path_without_default(
    db_session, db_factory, aggregator
) -> None:
    """When no default Scheduler is set, reload_scheduled_rules should still
    rebuild jobs against the bare apscheduler passed in.
    """
    rule = _make_rule(db_session, name="legacy")
    ct = _make_cron_trigger(db_session, rule=rule, expression="*/7 * * * *")
    db_session.commit()

    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    bare = AsyncIOScheduler()
    reload_scheduled_rules(bare, db_factory)
    assert f"cron_{ct.id}" in {j.id for j in bare.get_jobs()}


@pytest.mark.asyncio
async def test_module_execute_periodic_rule_delegates(
    db_session, db_factory, aggregator, pipeline_executor
) -> None:
    rule = _make_rule(db_session, primary_sensor_id="cam1")
    ct = _make_cron_trigger(db_session, rule=rule)
    db_session.commit()

    setup_scheduler(aggregator, db_factory, pipeline_executor)
    await scheduler_module.execute_periodic_rule(ct.id, db_factory)
    pipeline_executor.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_module_resume_callback_delegates(db_factory, aggregator, pipeline_executor) -> None:
    setup_scheduler(aggregator, db_factory, pipeline_executor)
    await scheduler_module._resume_workflow_callback(5)
    pipeline_executor.resume.assert_awaited_once()


@pytest.mark.asyncio
async def test_module_resume_callback_without_setup_is_noop(db_factory) -> None:
    reset_default_scheduler()
    # No default, no globals: should log and return, not raise.
    await scheduler_module._resume_workflow_callback(1)


def test_reset_default_scheduler_clears_state(db_factory, aggregator, pipeline_executor) -> None:
    setup_scheduler(aggregator, db_factory, pipeline_executor)
    assert scheduler_module._default_scheduler is not None
    reset_default_scheduler()
    assert scheduler_module._default_scheduler is None
    assert scheduler_module._pipeline_executor is None
    assert scheduler_module._db_session_factory is None


def test_pipeline_executor_property(db_factory, aggregator) -> None:
    s = Scheduler(aggregator, db_factory, pipeline_executor=None)
    assert s.pipeline_executor is None
    fake = object()
    s.pipeline_executor = fake
    assert s.pipeline_executor is fake


# ---------------------------------------------------------------------------
# Timezone-aware cron scheduling
# ---------------------------------------------------------------------------


def test_cron_trigger_uses_app_timezone(
    db_session, db_factory, aggregator, pipeline_executor
) -> None:
    """CronTrigger must be created with the configured app timezone.

    Cron expressions entered by operators should fire at the local wall-clock
    time, not at the server's system timezone or UTC.  We verify this by
    checking the timezone attached to the APScheduler job's trigger.
    """
    rule = _make_rule(db_session, name="tz-rule")
    _make_cron_trigger(db_session, rule=rule, expression="0 8 * * *", timezone="")
    db_session.commit()

    with patch(
        "backend.services.scheduler.settings.get",
        side_effect=lambda key, default=None: (
            "America/New_York" if key == "app.timezone" else default
        ),
    ):
        s = Scheduler(aggregator, db_factory, pipeline_executor)
        s.configure()

    jobs = {j.id: j for j in s.apscheduler.get_jobs()}
    job = next((j for jid, j in jobs.items() if jid.startswith("cron_")), None)
    assert job is not None, "cron trigger job was not registered"
    trigger = job.trigger
    # APScheduler stores the timezone on CronTrigger as ``timezone`` attribute.
    assert str(trigger.timezone) == "America/New_York", (
        f"Expected trigger timezone 'America/New_York', got '{trigger.timezone}'"
    )


def test_cron_trigger_uses_utc_when_configured(
    db_session, db_factory, aggregator, pipeline_executor
) -> None:
    """When app.timezone is UTC the trigger should also use UTC."""
    rule = _make_rule(db_session, name="utc-rule")
    _make_cron_trigger(db_session, rule=rule, expression="30 12 * * *", timezone="")
    db_session.commit()

    with patch(
        "backend.services.scheduler.settings.get",
        side_effect=lambda key, default=None: "UTC" if key == "app.timezone" else default,
    ):
        s = Scheduler(aggregator, db_factory, pipeline_executor)
        s.configure()

    jobs = {j.id: j for j in s.apscheduler.get_jobs()}
    job = next((j for jid, j in jobs.items() if jid.startswith("cron_")), None)
    assert job is not None
    assert str(job.trigger.timezone) == "UTC"


def test_reload_rules_preserves_app_timezone(
    db_session, db_factory, aggregator, pipeline_executor
) -> None:
    """reload_rules() must also apply the app timezone to new CronTriggers."""
    rule1 = _make_rule(db_session, name="r-initial")
    _make_cron_trigger(db_session, rule=rule1, expression="*/5 * * * *", timezone="")
    db_session.commit()

    with patch(
        "backend.services.scheduler.settings.get",
        side_effect=lambda key, default=None: (
            "America/Chicago" if key == "app.timezone" else default
        ),
    ):
        s = Scheduler(aggregator, db_factory, pipeline_executor)
        s.configure()
        # Add a second rule and reload.
        r2 = _make_rule(db_session, name="r-reload")
        ct2 = _make_cron_trigger(db_session, rule=r2, expression="0 9 * * 1", timezone="")
        db_session.commit()
        s.reload_rules()

    jobs = {j.id: j for j in s.apscheduler.get_jobs()}
    job = jobs.get(f"cron_{ct2.id}")
    assert job is not None
    assert str(job.trigger.timezone) == "America/Chicago"
