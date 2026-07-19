# `backend/bootstrap/` -- composition-root wiring inventory

M20 (closing finding C15 in `codebase-hardening-m11-cc-wave2-overview-and-findings.md`)
moved every service construction out of `backend/main.py`'s 1099-line
`lifespan` into this package, one module per phase, in the exact order the
original code ran. This file is the review artifact for that move: every
`app.state.<name> = ...` assignment that existed in `main.py`, which phase
now constructs it, and what it depends on.

**This is a strictly behavior-preserving refactor.** Every function body
below is a verbatim copy of the corresponding slice of the old
`lifespan()`; nothing was renamed, reordered, or "improved" in the move.
`backend/tests/test_bootstrap_wiring.py` pins the resulting `app.state`
attribute set (and was written and confirmed green against the
*pre-refactor* `main.py` first, specifically so it proves preservation
rather than assuming it).

## Call order (`bootstrap/lifespan.py`)

```
core_services.wire_boot_preamble          (settings reload, DB init, device-key upsert, plugin discovery)
core_services.wire_core_services          (integration clients, WS managers, LLM registry, conversation mgr, e-ink)
knowledge.wire_knowledge                  (knowledge services + notification dispatcher)
pipeline.wire_service_container           (ServiceContainer + RulesEngine)  -> container, rules_engine
perception.wire_perception                (person/scene/memory/tracking/activity/signals/occupancy services)
pipeline.wire_executor_and_workflow       (executor, media observability, workflow, sensor polling, activity timeline)
mcp.wire_mcp                              (MCP tool registry + Gemini adapter)
pipeline.wire_scheduler                   (APScheduler instance + scheduler bridge)   -> scheduler_bridge
guided_task.wire_guided_task              (safety watch, gate runner, GuidedTaskService, all scheduler.add_job, scheduler.start())  -> guided_camera_topology
if cts.enabled:
    cts.wire_cts                          (orchestrator clients, PH/keyframe/identity/ReID services, CTSRuntime)  -> cts_runtime
        -> presence.wire_presence         (called from inside wire_cts, not from lifespan.py -- see below)
else:
    cts.wire_cts_disabled
[inline] auth token check, ServiceContainer completeness gate, MCP session manager, yield, shutdown
```

## Deviations from the milestone's prescribed shape (and why)

The milestone's template signature is `wire_<phase>(app, settings, container) -> None`
for every phase, called once each from `lifespan.py` in source order. The
actual dependency graph in the original `main.py` does not partition that
cleanly; forcing it to would have required reordering statements, which a
behavior-preserving refactor may not do. Concretely:

1. **`perception` runs *between* two `pipeline` calls, not after `pipeline`.**
   `ServiceContainer` and `RulesEngine` must exist before perception can
   populate container fields, but the pipeline executor (which needs those
   populated fields) is constructed later still. So `pipeline.py` exports
   three functions (`wire_service_container`, `wire_executor_and_workflow`,
   `wire_scheduler`) with `perception.wire_perception` and `mcp.wire_mcp`
   called in between, matching the original interleaving exactly.
2. **`presence.wire_presence` is called from inside `cts.wire_cts`, not
   from `lifespan.py`.** In the original source, presence construction is
   nested *inside* the `if cts.enabled:` branch, between
   `await cts_runtime.start()` and the MCP-runtime surfacing step -- it is
   not a top-level lifespan step. Making it a lifespan.py-level call would
   mean either duplicating the `if cts.enabled:` check or reordering
   `wire_cts`'s internals; instead `cts.py` imports and calls
   `presence.wire_presence` at the exact point the original code ran it.
   Presence therefore stays its own file (matching the milestone's list)
   without pretending it is an independent lifespan phase.
3. **`guided_task.wire_guided_task` also owns every `scheduler.add_job`
   call, the telegram trigger service, and `scheduler.start()`** -- not
   just the guided-task-specific pieces the milestone's bullet for
   `pipeline.py` implied ("scheduler bridge wiring, telegram trigger").
   In the source, job registrations for guided-task, HA sensor polling,
   person-tracking polling, conversation pruning, the telegram trigger,
   and knowledge re-embed are one textually contiguous, interleaved block
   that depends on `guided_task_service` (constructed at the top of that
   same block) -- splitting it apart by service would reorder statements.
   `pipeline.wire_scheduler` stops after constructing the APScheduler
   instance and the scheduler/interactive-response bridges; everything
   that calls `scheduler.add_job` or `scheduler.start()` lives in
   `guided_task.py`.
4. **The MCP `/mcp` ASGI mount and its auth middleware stay in
   `backend/main.py`'s `create_app()`**, not in `bootstrap/mcp.py`.
   FastAPI mounts are part of building the ASGI app graph and must be
   registered synchronously during app construction, not from the async
   lifespan. `bootstrap/mcp.py` only builds the MCP tool registry and the
   Gemini adapter (the parts that really did run during lifespan startup).
5. **A `BootstrapContext` was considered and rejected in favor of plain
   return values.** Only three locals cross a phase-function boundary
   without already living on `app.state` or the shared `ServiceContainer`:
   `rules_engine` (stays inside `pipeline.py`, never actually crosses --
   see the table), `scheduler_bridge` (`pipeline.wire_scheduler` ->
   `guided_task.wire_guided_task`), `guided_camera_topology`
   (`guided_task.wire_guided_task` -> `cts.wire_cts`), and `cts_runtime`
   (`cts.wire_cts` -> `presence.wire_presence`, threaded as a direct
   parameter since that call is nested, not top-level). Three plain
   return values threaded through `lifespan.py`'s own local scope, typed
   in each function signature, are more explicit and no more invasive than
   introducing a generic context object for three fields.

## Attribute inventory

Every `app.state.<name>` assignment in the original `main.py`, by
constructing phase, in source order within each phase. "Depends on" lists
the other `app.state`/container inputs the construction reads, not import
dependencies.

### `core_services.wire_boot_preamble` / `wire_core_services`

No `container` parameter -- runs before `ServiceContainer` exists.

| Attribute | Depends on |
| --- | --- |
| `minio_client` | -- |
| `config_minio_client` | -- |
| `ha_client` | -- |
| `telegram_client` | -- |
| `tts_client` | -- |
| `ws_manager` | -- |
| `pipeline_ws_manager` | -- |
| `realtime_provider` | -- |
| `llm_model_registry` | -- |
| `conversation_manager` | -- |
| `eink_renderer` | `config_minio_client` |

### `knowledge.wire_knowledge`

| Attribute | Depends on |
| --- | --- |
| `layout_registry` | -- |
| `voice_instructions` | -- |
| `image_pipeline` | `minio_client`, `layout_registry` |
| `knowledge_ingestion` | `minio_client`, `image_pipeline` |
| `knowledge_query` | `llm_model_registry` |
| `knowledge_content_gen` | `llm_model_registry` |
| `knowledge_delivery` | `ws_manager`, `minio_client`, `eink_renderer`, `voice_instructions`, `knowledge_content_gen` |
| `notification_dispatcher` | `telegram_client`, `ws_manager`, `tts_client`, `eink_renderer`, `minio_client`, `ha_client` |

### `pipeline.wire_service_container`

| Attribute | Depends on |
| --- | --- |
| `service_container` | `notification_dispatcher`, `ha_client`, `llm_model_registry`, `minio_client`, `knowledge_delivery` |

`rules_engine` is built here too but is never assigned to `app.state`; it
is a plain return value consumed later in this same module (`setup_scheduler`).

### `perception.wire_perception`

Also assigns `container.scene_analysis_client`, `.semantic_memory_client`,
`.memory_query`, `.scene_intel`, `.person_tracking`, `.event_aggregator`,
`.activity`, `.daily_report_service`, `.interactive_response_service`,
`.signals`, `.person_location` (M38 Part A).

| Attribute | Depends on |
| --- | --- |
| `person_id_client` | -- |
| `scene_analysis_client` | -- |
| `semantic_memory_client` | -- (`None` if unconfigured/unreachable) |
| `memory_query` | `semantic_memory_client` |
| `scene_intel` | `scene_analysis_client`, `semantic_memory_client` |
| `source_authority` | -- |
| `person_location_service` | -- (`get_session` only; M38 Part A un-gated this from `cts.enabled` -- previously constructed in `cts.wire_cts`) |
| `recamera_location_ingest` | `person_location_service`; its `IdentityAssertionPublisher` half is real only when `redis.url` is configured (M38 Part D) |
| `person_tracking` | `person_id_client`, `ha_client`, `ws_manager`, `source_authority`, `recamera_location_ingest`, `person_location_service` (M38 Part E: HA correlation reads/writes the SSOT) |
| `event_aggregator` | `minio_client` |
| `activity_session_service` | -- |
| `activity_service` | `person_tracking`, `activity_session_service` |
| `daily_report_service` | `person_location_service` |
| `interactive_response_service` | -- (`scheduler` injected later by `pipeline.wire_scheduler`) |
| `signals` | -- |
| `companion_surface_service` | `person_location_service` |
| `zone_service` | `person_location_service` |
| `signals_feed` | -- |
| `occupancy_read_model` | -- |

### `pipeline.wire_executor_and_workflow`

Also assigns `container.camera_source_resolver`.

| Attribute | Depends on |
| --- | --- |
| `pipeline_run_service` | -- |
| `camera_source_resolver` | -- |
| `pipeline_executor` | `container` (as of this point), `rules_engine`, `pipeline_ws_manager` |
| `media_observability` | `event_aggregator`, `pipeline_executor`, `minio_client` |
| `workflow` | `rules_engine`, `pipeline_executor` |
| `sensor_polling` | `ha_client`, `workflow` |
| `activity_timeline_service` | `person_location_service` (constructed by `perception.wire_perception`, which runs before this phase) |

### `mcp.wire_mcp`

| Attribute | Depends on |
| --- | --- |
| `gemini_adapter` | (indirectly) every service passed to `init_services`: `event_aggregator`, `sensor_polling`, `ha_client`, `person_tracking`, `occupancy_read_model`, `signals_feed`, `activity_timeline_service`, `activity_session_service`, `daily_report_service`, `interactive_response_service`, `semantic_memory_client`, `ws_manager`, `knowledge_query`, `knowledge_delivery` |

### `pipeline.wire_scheduler`

| Attribute | Depends on |
| --- | --- |
| `scheduler` | `event_aggregator`, `pipeline_executor`, `rules_engine` |

Also injects `scheduler_bridge` into `pipeline_executor._scheduler` and
`interactive_response_service.scheduler` (not new `app.state` attributes).
Returns `scheduler_bridge` for `guided_task.wire_guided_task`.

### `guided_task.wire_guided_task`

Also assigns `container.guided_task`. `telegram_trigger` is conditional on
`telegram_client.configured` (a bot token being set) -- absent from
`app.state` entirely when Telegram is not configured, same as in the
original source.

| Attribute | Depends on |
| --- | --- |
| `gate_runner` | `container` |
| `guided_task_service` | `scheduler_bridge`, `pipeline_executor`, `person_location_service`, `zone_service`, `llm_model_registry`, `activity_service`, `signals`, `scene_analysis_client`, `companion_surface_service`, `ws_manager`, `pipeline_ws_manager`, `notification_dispatcher`, `conversation_manager`, `semantic_memory_client`, `memory_query`, `voice_instructions`, `gate_runner`, `camera_source_resolver`, `event_aggregator` |
| `guided_metrics_service` | -- |
| `telegram_trigger` (conditional) | `telegram_client`, `pipeline_executor` |

This phase also registers the `person_location_tick` scheduler job (M38 Part
A: inferred-dwell timeout + per-source quiet-gap segment closure), moved
here from an asyncio task that `CTSRuntime` used to own only when
`cts.enabled` -- this module already owns every unconditional
`scheduler.add_job` call.

Returns `guided_camera_topology` for `cts.wire_cts`.

### `cts.wire_cts` (only when `cts.enabled`) / `cts.wire_cts_disabled`

Also assigns `container.presence` (via `presence.wire_presence`).
`container.person_location` is assigned unconditionally by
`perception.wire_perception` instead (M38 Part A); this phase only reads
`app.state.person_location_service` to wire it into the CTS subscribers.

| Attribute | Enabled | Disabled |
| --- | --- | --- |
| `ingress_admin_client` | constructed | `None` |
| `orchestrator_client` | constructed | `None` |
| `ph_enrichment_service` | constructed | `None` |
| `keyframe_read_service` | constructed | `None` |
| `identity_correction_service` | constructed | `None` |
| `reid_review_service` | constructed | `None` |
| `gait_trend_service` | constructed | `None` |
| `cts_runtime` | constructed | `None` |
| `dementia_signal_subscriber` | constructed | `None` |
| `tracking_event_subscriber` | constructed | `None` |
| `identity_revision_subscriber` | constructed | `None` |
| `scene_sample_subscriber` | constructed | **absent** (see gap below) |
| `ha_state_cache` (via `presence.wire_presence`) | constructed | **absent** (see gap below) |
| `presence` (via `presence.wire_presence`) | constructed | **absent** (see gap below) |

`person_location_service` is **not** in this table any more: it is
constructed once by `perception.wire_perception`, unconditionally, and
neither `wire_cts` nor `wire_cts_disabled` touches it.

### `presence.wire_presence` (called from inside `cts.wire_cts`)

| Attribute | Depends on |
| --- | --- |
| `ha_state_cache` | `ha_client` |
| `presence` | `ha_state_cache`, `cts_runtime` (for its private `_db_factory`, an existing reach-in kept verbatim) |

## Known pre-existing gap, surfaced by writing the wiring-pin test, not fixed here

`cts.wire_cts_disabled` mirrors every CTS-gated attribute to `None` except
three: `scene_sample_subscriber`, `ha_state_cache`, and `presence`. When
`cts.enabled=false`, those three attributes do not exist on `app.state` at
all -- confirmed empirically by running the real lifespan under
`backend/tests/test_bootstrap_wiring.py` (it also confirmed a *second*
consequence: `main.py`'s shutdown block does
`if app.state.ha_state_cache is not None`, no `hasattr` guard, so a
`cts.enabled=false` deployment's shutdown raises `AttributeError` instead
of exiting cleanly -- the test works around this by setting
`app.state.ha_state_cache = None` itself right after capturing the real
attribute set, since fixing the underlying bug is a behavior change and
this milestone is strictly behavior-preserving). `backend/routers/cts_presence.py`
reads `request.app.state.presence` and `request.app.state.ha_state_cache`
with direct attribute access (no `getattr` default), so those routes would
also raise `AttributeError` rather than a clean 503 on such a deployment.
Filed as a follow-up finding alongside C17 in the M11 overview; not fixed
by M20.

## Import boundary

`backend.bootstrap` may import anything except `backend.routers` (wiring
never reaches into HTTP handlers). No module outside `backend.main` and
`backend.bootstrap` itself may import `backend.bootstrap` (wiring is not an
API). Both are import-linter contracts in `backend/pyproject.toml`.
