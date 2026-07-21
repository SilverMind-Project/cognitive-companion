"""Composition-root wiring pin + import-purity gate (M20).

The lifespan in ``backend/main.py`` (moving to ``backend/bootstrap/`` under
M20) wires ~60 services onto ``app.state``. A refactor that silently drops
one assignment turns into a runtime 503 (or an uncaught ``AttributeError``)
the first time a router reads that attribute -- exactly the C2/C3/C17
failure class this wave exists to close. This test boots the *real*
lifespan (not a hand-built ``ServiceContainer``) against a throwaway
Postgres testcontainer and pins the resulting ``app.state`` attribute set
against the frozen inventory in ``backend/bootstrap/README.md``.

Program-rule-7 correction: the M20 milestone file assumed
``tests/integration/test_service_container_integration.py`` already boots
the lifespan and could be reused. It does not -- it hand-constructs a
``ServiceContainer`` and never touches ``backend.main``. Nothing in this
repository exercised the real lifespan end-to-end before this test.

Configuration used here: ``cts.enabled=false`` and every optional
integration (Home Assistant, Telegram, TTS, person-id, scene-analysis,
semantic-memory, realtime LLM) left unconfigured -- the default posture of a
dev checkout with no secrets in the environment, and the only posture that
avoids needing a live Redis and orchestrator alongside Postgres. Booting
with ``cts.enabled=true`` would additionally require faking CTSRuntime's
internal Redis stream consumer, which reaches into implementation detail
this test has no business knowing.

**Known pre-existing gap surfaced while writing this test (not fixed
here -- fixing it is a behavior change, out of scope for a
behavior-preserving refactor):** three ``app.state`` attributes --
``presence``, ``ha_state_cache``, ``scene_sample_subscriber`` -- are only
ever assigned inside the ``cts.enabled`` branch. The ``else`` branch mirrors
every *other* CTS-gated attribute down to ``None`` but misses these three,
so with CTS disabled they do not exist on ``app.state`` at all.
``backend/routers/cts_presence.py`` reads ``request.app.state.presence`` and
``request.app.state.ha_state_cache`` with direct attribute access (no
``getattr`` default) -- on a deployment with ``cts.enabled=false`` those
routes would raise ``AttributeError`` instead of a clean 503. Filed as a
follow-up, tracked alongside C17 in the M11 overview.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs
from testcontainers.postgres import PostgresContainer

pytestmark = pytest.mark.integration

# Frozen from the bootstrap inventory (backend/bootstrap/README.md).
# Attributes assigned only inside the cts.enabled branch (see module
# docstring) are deliberately excluded: this test runs with cts disabled.
# ``telegram_trigger`` is also excluded: it is only assigned when
# ``telegram_client.configured`` (a bot token is set), which is not the case
# in this test's environment. Update this set *and* the README together
# whenever a phase gains or loses an attribute.
EXPECTED_APP_STATE_ATTRS = frozenset(
    {
        "activity_service",
        "activity_session_service",
        "activity_timeline_service",
        "camera_source_resolver",
        "companion_surface_service",
        "config_minio_client",
        "conversation_manager",
        "cts_runtime",
        "daily_report_service",
        "dementia_signal_subscriber",
        "eink_renderer",
        "event_aggregator",
        "gait_trend_service",
        "gate_runner",
        "gemini_adapter",
        "guided_metrics_service",
        "guided_task_service",
        "ha_client",
        "ha_state_cache",
        "identity_correction_service",
        "identity_revision_subscriber",
        "image_pipeline",
        "ingress_admin_client",
        "interactive_response_service",
        "keyframe_read_service",
        "knowledge_content_gen",
        "knowledge_delivery",
        "knowledge_ingestion",
        "knowledge_query",
        "layout_registry",
        "llm_model_registry",
        "media_observability",
        "memory_query",
        "minio_client",
        "notification_dispatcher",
        "occupancy_read_model",
        "orchestrator_client",
        "person_id_client",
        "person_location_service",
        "person_tracking",
        "ph_enrichment_service",
        "pipeline_executor",
        "pipeline_run_service",
        "pipeline_ws_manager",
        "presence",
        "realtime_provider",
        "recamera_location_ingest",
        "reid_review_service",
        "scene_analysis_client",
        "scene_intel",
        "scene_sample_subscriber",
        "scheduler",
        "semantic_memory_client",
        "sensor_polling",
        "service_container",
        "signals",
        "signals_feed",
        "source_authority",
        "telegram_client",
        "tracking_event_subscriber",
        "tts_client",
        "visitor_admin_service",
        "voice_instructions",
        "workflow",
        "ws_manager",
        "zone_service",
    }
)


@pytest.fixture(scope="module")
def wiring_postgres():
    """A dedicated, empty Postgres container for a real Alembic-migrated boot.

    Deliberately not the shared ``db_engine`` fixture from ``conftest.py``:
    that fixture creates its schema via ``Base.metadata.create_all``, but
    this test needs ``backend.main``'s own ``init_db()`` to run the real
    Alembic migration chain against a database it has never seen, the same
    as a fresh deployment.
    """
    image = os.environ.get("CC_TEST_POSTGRES_IMAGE", "timescale/timescaledb-ha:pg18")
    container = PostgresContainer(
        image,
        username="cc_wiring_test",
        password="cc_wiring_test",
        dbname="cc_wiring_test",
    ).with_name(f"cc-test-wiring-{uuid.uuid4().hex[:12]}")
    container.start()
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="module")
def wiring_minio():
    """A real MinIO container: ``get_minio_client()`` calls ``ensure_bucket()``

    (a ``head_bucket``/``create_bucket`` round trip) eagerly during
    construction, so unlike the other integration clients it is not lazy --
    lifespan startup genuinely cannot proceed without a reachable endpoint.
    """
    container = (
        DockerContainer("minio/minio:latest")
        .with_exposed_ports(9000)
        .with_env("MINIO_ROOT_USER", "cc_wiring_test")
        .with_env("MINIO_ROOT_PASSWORD", "cc_wiring_test_secret")
        .with_command("server /data")
    )
    container.start()
    wait_for_logs(container, "API:", timeout=30)
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture
def cts_disabled_config_dir(tmp_path: Path) -> Path:
    """A copy of ``config/`` with ``cts.enabled`` flipped to ``false``.

    ``Settings.reload()`` (which ``lifespan()`` calls unconditionally on
    every boot) re-reads YAML from disk, so disabling CTS for this boot
    means pointing the config directory at a modified copy -- there is no
    env-var override for a plain YAML boolean the way there is for the
    ``${...}``-interpolated DB/Redis URLs.
    """
    from backend.core.config import DEFAULT_CONFIG_DIR

    real_settings_yaml = (DEFAULT_CONFIG_DIR / "settings.yaml").read_text(encoding="utf-8")
    marker = "cts:\n  enabled: true"
    assert marker in real_settings_yaml, (
        "config/settings.yaml's cts.enabled marker text changed; update this test's substitution"
    )
    patched = real_settings_yaml.replace(marker, "cts:\n  enabled: false", 1)

    tmp_path.joinpath("settings.yaml").write_text(patched, encoding="utf-8")
    for filename in ("auth.yaml", "notifications.yaml"):
        tmp_path.joinpath(filename).write_text(
            (DEFAULT_CONFIG_DIR / filename).read_text(encoding="utf-8"), encoding="utf-8"
        )
    return tmp_path


def test_lifespan_wires_exactly_the_frozen_app_state_attributes(
    wiring_postgres: PostgresContainer,
    wiring_minio: DockerContainer,
    cts_disabled_config_dir: Path,
) -> None:
    """Boot the real lifespan and pin the resulting app.state attribute set.

    A moved-but-lost assignment during the M20 bootstrap-package split fails
    here. A deliberate future addition must extend
    ``EXPECTED_APP_STATE_ATTRS`` (and the README inventory) to pass.
    """
    from backend.core.config import settings
    from backend.core.database import reset_default_database

    env_vars = {
        "POSTGRES_USER": "cc_wiring_test",
        "POSTGRES_PASSWORD": "cc_wiring_test",
        "POSTGRES_HOST": wiring_postgres.get_container_host_ip(),
        "POSTGRES_PORT": str(wiring_postgres.get_exposed_port(5432)),
        "POSTGRES_DB": "cc_wiring_test",
        "MINIO_ENDPOINT": (
            f"{wiring_minio.get_container_host_ip()}:{wiring_minio.get_exposed_port(9000)}"
        ),
        "MINIO_ACCESS_KEY": "cc_wiring_test",
        "MINIO_SECRET_KEY": "cc_wiring_test_secret",
        # Not empty is all this needs: TritonEmbeddingClient is constructed
        # lazily and never connects during lifespan startup.
        "EMBEDDING_TRITON_URL": "http://wiring-test.invalid:8001",
    }
    original_env = {k: os.environ.get(k) for k in env_vars}
    original_config_dir = settings.config_dir

    os.environ.update(env_vars)
    settings._config_dir = cts_disabled_config_dir
    reset_default_database()

    # Work around cross-test pollution of a real, pre-existing global
    # registry, not introduced here: require_permission() permanently adds
    # to `backend.core.auth._DECLARED_TOKENS` at call time, and
    # `test_auth.py::test_...` (elsewhere in this suite) declares a
    # `Depends(require_permission("secret:read"))` test-only route with a
    # token that deliberately does not exist in `config/auth.yaml`. Running
    # the real lifespan, as this test does and nothing previously did, is
    # what turns that pre-existing pollution into a spurious failure here.
    # Filter it out for the duration of this boot rather than fixing the
    # shared registry (a behavior change, out of scope for this milestone).
    import backend.core.auth as auth_module

    original_declared_tokens = set(auth_module._DECLARED_TOKENS)
    known_tokens = auth_module._ensure_keystore().known_tokens()
    auth_module._DECLARED_TOKENS.intersection_update(
        t for t in original_declared_tokens if " " in t or t in known_tokens
    )

    try:
        import backend.main as main_module

        with TestClient(main_module.app) as client:
            resp = client.get("/api/v1/health")
            assert resp.status_code == 200

            actual = set(main_module.app.state)

            missing = EXPECTED_APP_STATE_ATTRS - actual
            extra = actual - EXPECTED_APP_STATE_ATTRS
            drift_message = (
                f"app.state attribute set drifted from the frozen inventory.\n"
                f"missing (dropped during a move): {sorted(missing)}\n"
                f"extra (added but not pinned): {sorted(extra)}"
            )
            assert not missing, drift_message
            assert not extra, drift_message

            # PersonLocationService is un-gated from cts.enabled --
            # this boot runs with cts.enabled=false, so a None here would mean
            # the un-gating regressed back to CTS-only construction.
            assert main_module.app.state.person_location_service is not None, (
                "person_location_service must be constructed even with cts.enabled=false"
            )
    finally:
        auth_module._DECLARED_TOKENS.clear()
        auth_module._DECLARED_TOKENS.update(original_declared_tokens)
        for k, v in original_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        settings._config_dir = original_config_dir
        reset_default_database()
        settings.reload()


def test_import_backend_main_performs_no_io() -> None:
    """``import backend.main`` must not attempt any DB/network connection.

    Run in a subprocess with Postgres/Redis pointed at unroutable addresses:
    if the import path triggered a connection attempt (rather than only
    building the FastAPI app object and its router table), this hangs or
    raises instead of returning immediately.
    """
    env = os.environ.copy()
    env.update(
        {
            "POSTGRES_USER": "unroutable",
            "POSTGRES_PASSWORD": "unroutable",
            "POSTGRES_HOST": "192.0.2.1",  # TEST-NET-1 (RFC 5737): guaranteed unroutable
            "POSTGRES_PORT": "5432",
            "POSTGRES_DB": "unroutable",
            "REDIS_URL": "redis://192.0.2.1:6379/0",
        }
    )
    result = subprocess.run(
        [sys.executable, "-c", "import backend.main"],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"import backend.main failed or attempted I/O:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
