"""Boot-time completeness check for :class:`ServiceContainer`.

The container is built once in the lifespan and shared by reference with the
executor, the gate runner, and the rules engine. Late-phase services (CTS,
presence) are assigned onto fields of that same instance as their subsystems
come up. If a field a running feature set depends on is still ``None`` once
startup finishes, the dependent steps/filters would silently degrade instead
of failing -- for a dementia-care system that is worse than a boot-time
crash, so this module turns it into one.
"""

from __future__ import annotations

from collections.abc import Iterable

from backend.steps.base import ServiceContainer

# Fields that main.py constructs and assigns unconditionally, regardless of
# which optional feature flags are enabled. A container missing one of these
# indicates a wiring bug, not a disabled feature.
ALWAYS_REQUIRED: frozenset[str] = frozenset(
    {
        "db_factory",
        "person_tracking",
        "notification_dispatcher",
        "ha_client",
        "event_aggregator",
        "scheduler",
        "llm_model_registry",
        "scene_analysis_client",
        "daily_report_service",
        "interactive_response_service",
        "memory_query",
        "scene_intel",
        "activity",
        "signals",
        "knowledge_delivery",
        "minio_client",
        "guided_task",
        "camera_source_resolver",
        # M38 Part A: PersonLocationService is constructed unconditionally by
        # perception.wire_perception (depends only on get_session), so it is
        # no longer gated behind cts.enabled.
        "person_location",
    }
)

# Fields only wired when a given feature flag is enabled. Keys match the
# feature-flag names main.py already branches on (currently just "cts").
#
# `semantic_memory_client` is intentionally absent from both maps: it is
# allowed to be `None` when the semantic-memory service is unreachable or
# unconfigured, and the dependent features are documented to degrade
# gracefully in that case.
REQUIRED_WHEN: dict[str, frozenset[str]] = {
    "cts": frozenset({"presence", "bucketizer"}),
}


def assert_container_complete(container: ServiceContainer, enabled: Iterable[str]) -> None:
    """Raise ``RuntimeError`` listing every unexpectedly-``None`` field.

    Args:
        container: The shared :class:`ServiceContainer` after lifespan startup.
        enabled: Feature-flag names that are turned on for this process
            (e.g. ``{"cts"}`` when ``cts.enabled`` is true).
    """
    enabled_set = set(enabled)
    missing = [field for field in ALWAYS_REQUIRED if getattr(container, field) is None]
    for feature, fields in REQUIRED_WHEN.items():
        if feature in enabled_set:
            missing.extend(field for field in fields if getattr(container, field) is None)

    if missing:
        raise RuntimeError(
            f"ServiceContainer incomplete at end of startup, missing: {sorted(missing)}"
        )
