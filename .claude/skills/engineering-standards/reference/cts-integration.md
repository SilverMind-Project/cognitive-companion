# CTS integration

Read before changing code under `backend/services/cts/`, CTS routers, or the CTS WebSocket. Part of the `engineering-standards` skill; the rules summary is in `../SKILL.md`.

## CTS-specific standards

These apply to all code under `backend/services/cts/`, `backend/routers/cts*.py`, and `backend/websocket/connection_manager.py`.

### Shared utilities (do not duplicate)

Three files are the single authoritative source for previously-duplicated functions:

| Utility | Import from | Replaces |
| --- | --- | --- |
| `ns_to_iso()` | `backend.services.cts._time` | 4 identical copies across subscriber files |
| `parse_ts()` | `backend.services.cts._time` | 3 divergent copies across service files |
| `ensure_aware()` | `backend.services.cts._time` | 1 copy in source_authority |
| `cts_enabled()` | `backend.routers.cts_deps` | 8 identical copies across router files |
| Aggregation primitives | `backend.services.aggregation` | Per-camera token buckets, cooldown math, and uniform buffer-state snapshots |

If you need one of these, import it. Never redefine it.
Import `PerCameraRateLimiter`, `CooldownTracker`, and `CameraBufferState` from
`backend.services.aggregation`; do not reimplement per-camera token buckets or
cooldown deadline math.

### Protocol-based dependency injection

CTS subscribers and services accept their dependencies through `__init__`. Use the protocol types from `backend.services.cts._types`, never `Any`:

```python
from backend.services.cts._types import ConnectionManager, PipelineExecutor, DBSessionFactory

class TrackingEventSubscriber(StreamConsumer[dict[str, Any]]):
    def __init__(
        self,
        redis_url: str,
        consumer_id: str,
        ws_manager: ConnectionManager | None = None,      # not Any
        pipeline: PipelineExecutor | None = None,          # not Any
    ) -> None:
        ...
```

`DBSessionFactory` is `Callable[[], Session]`. Use it for `db_factory` parameters.

### StreamConsumer contract

All four CTS subscribers extend `StreamConsumer[T]`. The `decode()` and `handle()` signatures must match the base class exactly. The `decode` parameter `fields` uses `dict[bytes | str, bytes | str]` because Redis returns bytes keys and values when `decode_responses=False`.

### CTS isolation

- CTS tables (`dementia_signals`, `cts_cameras`) are written only inside `services/cts/`.
- **The location single source of truth is `PersonLocationService`** (`presence_segments` / `location_observations`); the four CTS filters (`room`, `room_transition`, `person_presence`, `scene_trend`) read it. The legacy tables (`person_location_state`, `person_location_history`, `person_sightings`), the step-level write flags (`record_presence`, `record_sightings`), and `LocationWriter` no longer exist; no code may reference them.
- **Person location has one read API: `PersonLocationService`** (`where_is`, `where_is_everyone`, `presence_history`, `room_segments`, `observations`, `recent_observations`, `latest_observation`, `latest_floor_point`, envelopes). Never query `location_observations` / `presence_segments` directly from services or steps, and never reintroduce a second location store or a second query path for the same data. A same-room repeat observation refreshes the open segment's `last_observed_at`/`confidence`/`quality` (the state machine's refresh branch, not a no-op), so `where_is()`'s segment is never frozen at entry time; `latest_observation()` remains the observation-level freshness/staleness signal regardless of segment state, and still answers after a segment has closed or quiet-timed-out. Segments age out per source (`PersonLocationConfig.quiet_gap_s`): a dense source (`world_tracker`) ages out fast, a sparse rule-driven source (`face_sighting`) stays credible far longer, and `manual` never ages. The presence provider `LocationServiceProvider` (`location_service`) uses a per-source freshness matrix (`ttl_seconds_by_source`) matching the SSOT quiet gaps so reCamera face sightings and sensors retain presence credibility when camera tracking is offline. `PresenceService` is un-gated from CTS and runs unconditionally in lifespan. `OccupancyReadModel` accepts `face_sighting` presence for identified persons and named guests under stable hypothesis key `f"face_{person_id}"`.
- **`PersonLocationService` is constructed unconditionally** (`perception.wire_perception`): it depends only on `get_session`, not on `cts.enabled`. reCamera identification (`services/person_tracking.py` via `FaceSightingIngest`, `services/person_location/face_sighting_ingest.py`) and HA presence correlation (`PersonTrackingService._correlate_presence_sensor`) write to it directly, independent of CTS. **Every location source writes through `PersonLocationService.ingest_*`.** Source vocabulary is `world_tracker`, `face_sighting`, `sensor`, `manual` (SourceTags name evidence pathways, not hardware). A new source gets a `SourceTag`, an arbitration priority (`services/person_location/source_arbitration.py`), and a quiet gap (`PersonLocationConfig`); it never gets a second store, a second writer service, or a step-level write flag. Observation rows are unarbitrated history (`ingest_observation` always inserts one); segments are the arbitrated present (`source_arbitration.arbitrate` gates only a room-*changing* observation against the open segment's `last_source`/`last_observed_at`, with an out-of-order guard that never lets a lagged event move evidence backward).
- **One `image_source` vocabulary via shared resolver.** Perception steps (`image_crop`, `person_identification`, `scene_analysis`, `llm_call`) declare a single consolidated `image_source` vocabulary resolved by `ImageSourceResolver`. The deprecated `cts_window` and `cts_frames_path` options are removed.
- **Signal vocabularies derive from `cts_contracts`.** `ALL_SIGNAL_KINDS` in `signal_config.py` derives dynamically from `cts_contracts.DementiaSignalKind` plus `CC_LOCAL_SIGNAL_KINDS`. Preset profile memberships (`_PRESENCE_KINDS` etc.) carry guard tests asserting every member is in `ALL_SIGNAL_KINDS`.
- **`observations()` is per-frame, not per-event.** `world_tracker` can call `ingest_observation()` several times a second (tracking-orchestrator publishes at up to 3Hz per camera); the legacy `PersonSighting` table it replaced for the activity timeline's "sighting" source was written once per identification run (sparse). Event-grade consumers use `bucketed_observations()` (one representative row per room per time bucket, deduped by a SQL window function **before** LIMIT applies, so wide windows keep their early history), never raw `observations()` per-row: see `ActivityTimelineService._get_sighting_events`. A client-side throttle over a LIMITed raw query is the known-wrong shape (it silently drops old history once raw rows exceed the limit).
- **Seed location state through the service's ingest methods, never raw repo inserts.** Tests (and any backfill/tooling) create presence state via `ingest_observation` / `ingest_room_transition` so the segment state machine enforces the one-open-segment-per-person invariant; two raw-inserted "open" segments make `get_open`/`where_is` return an arbitrary one (a real bug, since fixed). Closed historical segments written by a sanctioned backfill path are the one exception, and they go through a dedicated service method, not repo calls from outside the package.
- `_upstream_base` is imported only by CTS integration clients (`ingress_admin_client`, `tracking_orchestrator_client`).
- Redis Stream subscriptions (`tracking.events`, `tracking.revisions`, `tracking.signals`, `scene.samples`) are created only inside `CTSRuntime`.
- All browser and MCP traffic to `rtsp-ingress` or `tracking-orchestrator` goes through CC routers. No direct access.
- The `CtsEventBucketizer` (in-memory per-camera recent-frame buffer) is built by `CTSRuntime` and fed by `TrackingEventSubscriber.ingest` from the `tracking.events` stream (no new stream, no DB read, so it respects the isolation boundary). It reaches the `media_window_poll` step (CTS source) via `ServiceContainer.bucketizer`, injected **after** CTS bootstrap through the `PipelineExecutor.bucketizer` property (the executor is constructed before `CTSRuntime`; `backend/bootstrap/cts.py` sets `pipeline_executor.bucketizer = cts_runtime.bucketizer`). This is the same post-construction injection pattern as `_scheduler`. Steps read it via typed direct access (`services.bucketizer`), never `getattr`.

### Per-camera image rate limiting

- Rate limiting gates images only. CTS metadata remains full fidelity for trigger evaluation, location state, live views, and summaries.
- Mark CTS frames with `image_eligible`; image consumers filter to eligible frames before per-rule downsampling.
- Count every rate-limit rejection in `cc_aggregator_images_dropped_total`. Drops must never be silent.
- Apply `sample_period_s` after the aggregator ceiling. Effective image rate is the minimum of the system ceiling and rule intent.
- Keep CTS frame references in memory. Never persist CTS-owned frame references to `MediaCache`.
- Cognitive Companion deletes only its own reCamera objects. It never deletes CTS-owned MinIO objects.

### WebSocket security

- The `/ws/cts` WebSocket reads the API key from `sec-websocket-protocol` header, not from a query parameter.
- Frame image URLs (`GET /api/v1/cts/frames/{key}`) use query-param auth as a known limitation (browser `<img>` tags cannot set headers).
- Nginx uses `location ^~ /api/` and `location ^~ /ws` to prevent regex static-cache locations from stealing proxied URLs.

## CTS integration design principles

### Severity-transition contract

The orchestrator's hysteresis guarantees idempotent DB rows but does not guarantee idempotent alerts. The CC must enforce the consumer side of the contract:

- **New `signal_id`** (first time seen): actionable. Persist, fire pipeline event, allow notifications.
- **Same `signal_id`, higher severity**: actionable escalation. Update row, fire pipeline event with `action="escalation"`.
- **Same `signal_id`, equal or lower severity**: update row only. Do not fire pipeline events. Do not re-alert caregivers.

`SignalStore.upsert()` enforces this contract. The `DementiaSignalSubscriber.handle()` method gates pipeline event firing on the `action` returned by upsert. The `DementiaSignalFilter` should honor this as a second line of defense.

### Projection supersession scoping

Projection supersession is always bounded: operator revisions by their `range_start`/
`range_end`, automatic revisions by `cts.revision_horizon_s` (mirror of CTS
`resolver.revision_horizon_s`; change both together). A replacement row derived from a
superseded row must re-derive any identity-scoped stable ID (`derive_signal_id`); never
copy an ID that encodes the old identity.

### Authority vocabulary

CTS `IdentityDecision.authority` (received over the wire, e.g. `bbox.authority` in
`keyframe_read_service.py`) is a bounded vocabulary produced by CTS
(`operator | direct_face | posterior | temporal_prior | none`, plus `reid_gallery` reserved and
`unknown` / `height_proxy` legacy members the current CTS producer never emits),
never an identity id. CTS validates it at its own repository boundary
(`validate_identity_authority()`); CC receives it already validated and must not re-derive or
guess it client-side: branch on the string verbatim (`bbox.authority == "direct_face"`, not
`decision_source == "arcface_authority"`, a removed workaround). Do not
confuse it with the unrelated `SourceAuthority` class (`backend/services/cts/source_authority.py`),
which governs CTS-vs-non-CTS location-write precedence. See
`.claude/skills/cts-identity-admin/SKILL.md` for the badge-rendering mapping and the distinct
`IdentityRevisionRange.authority` (`RevisionAuthority`) vocabulary, which must never be normalized
through the same fallback path as decision `authority`.

### Algorithm version tracking

Every signal carries `algorithm_version` from the orchestrator. The CC persists this value and surfaces it in `CTSSignalsView`. The `get_24h_summary` and `list_recent` endpoints should allow filtering out signals from stale detector generations.

### Signal identity across services

The orchestrator computes deterministic signal IDs via UUID5. The CC stores these as `signal_id` on the `DementiaSignal` model. This is the cross-service identity for deduplication. Do not use the auto-increment `id` for dedup logic.

### Proto evolution

Additive proto fields (new tag numbers) are wire-compatible. The CC subscriber uses `message.algorithm_version if message.algorithm_version else None` to gracefully handle old orchestrators that do not set the field. Regenerate bindings in both repos after every proto change via `make proto-py` from the continuous-tracking repo.

### CTS WebSocket payload rule

**All WebSocket broadcasts must use `Pydantic model.model_dump(mode="json")`**, never manual dict literals. This prevents the payload schema drifting from the Pydantic definition without a type error.

```python
# CORRECT
from backend.schemas.cts_ph_ws import PHUpdateEvent

event = PHUpdateEvent(ph_id=..., ...)
await self._ws_manager.broadcast(event.model_dump(mode="json"))

# WRONG: raw dict will silently drift from the schema
await self._ws_manager.broadcast({
    "type": "cts_ph_update",
    "ph_id": ph_id,
    ...
})
```

WS event schemas live in a dedicated module named `backend/schemas/<domain>_ws.py`. The module for PH events is `backend/schemas/cts_ph_ws.py`. Never define WS event schemas inside a router file.

### CTS WebSocket debounce rule

High-frequency WS events (those driven by every tracking frame) must be debounced server-side per entity. The pattern:

```python
async def _schedule_broadcast(self, entity_id: str, event: BaseModel) -> None:
    self._pending[entity_id] = event
    existing = self._debounce_tasks.get(entity_id)
    if existing and not existing.done():
        existing.cancel()
    task = asyncio.create_task(self._delayed_broadcast(entity_id))
    task.add_done_callback(lambda t: self._debounce_tasks.pop(entity_id, None))
    self._debounce_tasks[entity_id] = task

async def _delayed_broadcast(self, entity_id: str) -> None:
    await asyncio.sleep(self._debounce_interval)  # 0.200s for PH updates
    event = self._pending.pop(entity_id, None)
    if event is not None and self._ws_manager is not None:
        await self._ws_manager.broadcast(event.model_dump(mode="json"))
```

Always cancel and await pending debounce tasks in `stop()`.

### CTS router pattern

All CTS routers follow the same pattern:
1. Import `cts_enabled` from `backend.routers.cts_deps`.
2. All routes have `dependencies=[Depends(cts_enabled)]`.
3. Proxy requests through the typed client (`OrchestratorClient` or `IngressAdminClient`), never raw `httpx`.
4. Return 503 when the upstream client is not available; return 502 on upstream errors.

### Testing CTS services

- `SignalStore` tests use the conftest `db_factory` that returns a plain `Session`. Never use context-manager form.
- `DementiaSignalSubscriber` tests test `decode()` and `handle()` directly. No real Redis required.
- The severity-transition logic must be tested with three cases: new signal_id, same signal_id with escalation, same signal_id with equal severity. Assert pipeline event firing only in the first two cases.
