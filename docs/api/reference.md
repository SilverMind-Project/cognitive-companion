# API Reference

All HTTP endpoints are served under `/api/v1`. Endpoints require authentication unless a router explicitly documents a device or webhook auth path.

Authentication is resolved from API keys, device keys, or route-specific secrets. Authorization uses named D4 `<resource>:<action>` permission tokens enforced by pure role membership against `config/auth.yaml` `roles:`. See the generated [Permission Token Reference](permissions.md) for the complete route, WebSocket, and role access matrix.

## Execution observability

`GET /workflows/{execution_id}/detail` is the canonical execution-detail contract for the UI. `GET /pipeline/runs` and `GET /pipeline/runs/{execution_id}` are lightweight list and dashboard envelopes.

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/workflows` | List executions. Query: `rule_id`, `status`, `limit` |
| `GET` | `/workflows/{execution_id}` | Return the raw workflow execution and full `pipeline_data_json` |
| `GET` | `/workflows/{execution_id}/detail` | Return the rich inspector model with graph and timeline |
| `POST` | `/workflows/{execution_id}/cancel` | Cancel a `running` or `waiting` execution |
| `POST` | `/workflows/{execution_id}/rerun` | Start a new execution from the original trigger |
| `GET` | `/pipeline/runs` | List recent runs. `status=active` returns `running` and `waiting` runs |
| `GET` | `/pipeline/runs/{execution_id}` | Return one lightweight run envelope |
| `GET` | `/pipeline/ingest/activity` | Return recent frame and rule-trigger activity |
| `WS` | `/ws/pipeline` | Stream live pipeline lifecycle events |

### ExecutionDetailOut

| Field | Type | Description |
| --- | --- | --- |
| `id` | integer | Workflow execution ID |
| `rule_id` | integer | Rule that ran |
| `status` | string | `running`, `waiting`, `completed`, `failed`, or `cancelled` |
| `started_at` | datetime or null | Execution start time |
| `completed_at` | datetime or null | Execution completion time |
| `rule_name` | string | Rule display name |
| `trigger_type` | string | Trigger type stored in `pipeline_data.trigger.type` |
| `trigger_summary` | string | Short server-computed trigger summary |
| `graph` | object or null | Immutable graph snapshot captured at execution start |
| `timeline` | list | Per-step timeline entries, including skipped graph nodes |
| `cooloff_triggered` | boolean | Whether this run consumed the rule cool-off window |
| `error` | string or null | Execution error |
| `can_cancel` | boolean | Whether cancel is allowed |
| `can_rerun` | boolean | Whether rerun is allowed |

### Timeline entry

| Field | Type | Description |
| --- | --- | --- |
| `step_id` | integer or null | Pipeline step ID when known |
| `label` | string | Step label |
| `step_type` | string | Step type name |
| `icon` | string | Material Design icon from step metadata |
| `category` | string | Step category |
| `status` | string | `success`, `failed`, `skipped`, `in_progress`, or `cancelled` |
| `elapsed_seconds` | number or null | Step duration |
| `output_port` | string | Runtime output port, usually `main` |
| `resolved_config` | object or null | Config after template resolution |
| `outputs` | object or null | Outputs written by the step |
| `logs` | list[string] | Step log messages when available |
| `error` | string or null | Step error |
| `cancellation_observed` | boolean | Whether this step observed a cancel request |

### PipelineRunEnvelope

| Field | Type | Description |
| --- | --- | --- |
| `execution_id` | integer | Workflow execution ID |
| `rule_id` | integer | Rule ID |
| `rule_name` | string | Rule display name |
| `status` | string | Execution status |
| `started_at` | datetime | Start time |
| `completed_at` | datetime or null | Completion time |
| `error` | string or null | Error summary |
| `nodes` | list | DAG nodes with `id`, `label`, `step_type`, `status` |
| `edges` | list | DAG edges with `source`, `source_handle`, `target`, `target_handle` |

### PipelineExecutionEvent

WebSocket events use `type: "pipeline_event"` and include:

| Field | Type | Description |
| --- | --- | --- |
| `event_type` | string | `pipeline_started`, `step_started`, `step_completed`, `pipeline_waiting`, `pipeline_completed`, `pipeline_failed`, or `pipeline_cancelled` |
| `execution_id` | integer | Workflow execution ID |
| `rule_id` | integer | Rule ID |
| `rule_name` | string | Rule display name |
| `step_id` | string or null | Step ID for step events |
| `step_name` | string or null | Step label for step events |
| `step_type` | string or null | Step type for step events |
| `status` | string | Current status |
| `started_at` | datetime or null | Event start time |
| `finished_at` | datetime or null | Event finish time |
| `output_port` | string or null | Port activated by a step |
| `elapsed_ms` | integer or null | Step elapsed time |
| `sequence` | integer | Monotonic sequence number per connection manager |

## Rules and pipeline authoring

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/rules` | List rules with recent execution counts |
| `POST` | `/rules` | Create a rule |
| `GET` | `/rules/{rule_id}` | Return a rule with steps, contexts, dependencies, and cron triggers |
| `PUT` | `/rules/{rule_id}` | Update a rule |
| `DELETE` | `/rules/{rule_id}` | Delete a rule and related executions |
| `POST` | `/rules/{rule_id}/execute` | Manually execute a rule |
| `GET` | `/rules/{rule_id}/export` | Export a portable rule bundle |
| `POST` | `/rules/import/preview` | Validate a bundle without writing |
| `POST` | `/rules/import` | Import a rule bundle |

### Rule fields

| Field | Type | Description |
| --- | --- | --- |
| `name` | string | Rule name |
| `description` | string or null | Optional description |
| `enabled` | boolean | Whether the rule can run |
| `trigger_types` | list[string] | Trigger types. Current values include `sensor_event`, `cron`, `manual`, `webhook`, `telegram`, `occupancy_duration`, `cts_window`, and `dementia_signal` |
| `cron_trigger_ids` | list[integer] | Shared cron trigger IDs |
| `primary_sensor_id` | string or null | Sensor used as a fallback for context and manual media lookup |
| `cool_off_minutes` | integer | Minimum time between completed cool-off-worthy runs |
| `max_daily_triggers` | integer | Daily execution cap |
| `max_concurrent_executions` | integer | Concurrent execution cap |
| `execution_timeout_minutes` | integer | Execution timeout |
| `webhook_config` | object or null | Webhook secret and settings |
| `occupancy_config` | object or null | Occupancy duration settings |
| `telegram_trigger_config` | object or null | Telegram command settings |

### Pipeline steps and edges

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/rules/{rule_id}/steps` | List steps ordered by deterministic `order` |
| `POST` | `/rules/{rule_id}/steps` | Add a step and auto-generate a label when omitted |
| `PUT` | `/rules/{rule_id}/steps/{step_id}` | Update step type, label, config, enabled flag, or canvas position |
| `DELETE` | `/rules/{rule_id}/steps/{step_id}` | Delete a step and cascade connected edges |
| `PUT` | `/rules/{rule_id}/steps/positions` | Batch update canvas positions |
| `GET` | `/rules/{rule_id}/edges` | List graph edges |
| `PUT` | `/rules/{rule_id}/edges` | Replace all graph edges atomically |
| `POST` | `/rules/{rule_id}/validate` | Validate templates and graph structure |

### PipelineStepOut

| Field | Type | Description |
| --- | --- | --- |
| `id` | integer | Step ID |
| `rule_id` | integer | Parent rule |
| `order` | integer | Stable ordering and graph tiebreaker |
| `step_type` | string | Registered step type |
| `label` | string or null | Slug label used by templates |
| `config_json` | object | Step-specific config |
| `enabled` | boolean | Whether the executor may run this step |
| `position_x` | number | Canvas x-coordinate |
| `position_y` | number | Canvas y-coordinate |

### PipelineEdgeCreate

| Field | Type | Description |
| --- | --- | --- |
| `source_step_id` | integer | Source step |
| `source_port` | string | Source output port, defaults to `main` |
| `target_step_id` | integer | Target step |
| `target_port` | string | Target input port, defaults to `main` |

The graph validator rejects unknown step IDs, unknown source ports, cycles that cannot execute safely, and duplicate outgoing edges for the same source port.

## Contexts, dependencies, and cron triggers

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/rules/{rule_id}/contexts` | List context filters |
| `POST` | `/rules/{rule_id}/contexts` | Add a context filter |
| `DELETE` | `/rules/{rule_id}/contexts/{context_id}` | Delete a context filter |
| `GET` | `/rules/{rule_id}/dependencies` | List dependencies |
| `POST` | `/rules/{rule_id}/dependencies` | Add a dependency on another rule |
| `DELETE` | `/rules/{rule_id}/dependencies/{dependency_id}` | Delete a dependency |
| `GET` | `/cron-triggers` | List shared cron triggers |
| `POST` | `/cron-triggers` | Create a cron trigger |
| `PUT` | `/cron-triggers/{trigger_id}` | Update a cron trigger |
| `DELETE` | `/cron-triggers/{trigger_id}` | Delete a cron trigger |

## Pipeline metadata

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/pipeline/step-types` | Registered step metadata |
| `GET` | `/pipeline/channel-types` | Registered channel metadata |
| `GET` | `/pipeline/filter-types` | Registered context filter metadata |
| `GET` | `/pipeline/llm-models` | LLM model registry entries |
| `GET` | `/pipeline/data-keys` | Template autocomplete variables and step output schemas |
| `POST` | `/pipeline/cron/preview` | Validate a cron expression and return upcoming run times |

`StepTypeOut` includes `config_schema`, `default_config`, `schema_version`, `ui_hints`, `output_schema`, tags, and `output_ports`.

## Device and integration endpoints

| Resource | Representative endpoints |
| --- | --- |
| Rooms | `GET /rooms`, `POST /rooms`, `PUT /rooms/{id}`, `DELETE /rooms/{id}` |
| Sensors | `GET /sensors`, `POST /sensors`, `PUT /sensors/{id}`, `DELETE /sensors/{id}` |
| Device ingest | reCamera and reTerminal device routers using device-key authentication |
| Home Assistant sync | `POST /ha/sync/rooms`, `POST /ha/sync/sensors`, `GET /ha/entities`, `GET /ha/media-players` |
| Webhooks | `POST /webhooks/{rule_id}`, `POST /webhooks/{rule_id}/generate-secret` |

## Companion surfaces and the companion socket

`/ws/audio` is the resident's companion socket. It requires a key holding `companion.audio:act` (`x-api-key` header, or from a browser the `Sec-WebSocket-Protocol` header, which the server echoes on accept). Optional query parameters:

| Parameter | Meaning |
| --- | --- |
| `surface_id` | The registered, enabled companion surface this screen is; it then receives its room's deliveries. Unknown or disabled: closed with 1008 `unknown_surface`. |
| `platform` | `web`, `android_tablet`, or `android_tv` (logged). |

Resident content for a surface goes only to that surface while it is connected, else to every companion screen. `surface_hardware_command` (`lease_owner`, `wake_screen`, `enable_microphone`, `enable_camera`, `volume_min_pct`, `attention_chime`, `lease_seconds`) goes only to its surface and is never broadcast. Leases are per `lease_owner` (one delivery): the device keeps the screen awake while any lease is live and the microphone (camera) open while any live lease asks for it; `lease_seconds: 0` ends only that owner's lease, and capture closes on the device when a lease runs out unrenewed. A `surface_id` that is unknown or disabled connects without room routing. A surface may send `surface_attention_state` (`face_present`, `head_yaw_deg`, `head_pitch_deg`, `timestamp`); any other field, such as an image, is rejected.

`POST /companion-surfaces/{id}/heartbeat` also accepts `platform`, `mic_active`, `camera_active`, and `screen_awake`; an omitted field keeps its last value. `GET /guided-sessions/resident-state?surface_id=` shows a screen the routine the broadcast would send it. Surface kinds are `tablet`, `speaker`, `display`, and `tv`.

## Media observability

Both endpoints require the admin permission.

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/media/buffer` | Paginated reCamera media buffers. Query: `sensor_id`, `limit`, `offset` |
| `GET` | `/media/aggregators` | Live state for reCamera and CTS aggregators. Query: `origin`, `camera_id`, `room_name`, `q`, `limit`, `offset` |

`GET /media/buffer` returns `{items, total}`. Each camera item includes
`sensor_id`, `sensor_name`, `room_name`, `buffer_pending`,
`cooldown_remaining_seconds`, and retained `images` with refreshed presigned
URLs.

`GET /media/aggregators` returns `{items, total}` after filtering and stable
pagination. Each item includes the camera origin (`recamera` or `cts`) and
identity, `buffer_kind` (`sliding_window` for the CTS recent-events lookback
deque, `batch` for the reCamera flush buffer), buffer depth and capacity,
pending flush and cooldown state, rate ceiling and available tokens,
`images_eligible_total` and `images_dropped_total` (images refused by the
per-camera image rate limiter for AI analysis; tracking still uses every
frame), and the latest event timestamp.

## Daily Living health

Requires the `admin:read` permission.

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/admin/daily-living-health` | Semantic-memory write recency and activity-ledger population (DL-M01) |

Returns `{semantic_memory, activity_ledger}`. `semantic_memory` includes `reachable`,
`last_observation_at`, `last_movement_at`, a 14-day `observations_by_day` breakdown by source,
`total_observations`, `total_movements`, and `stale` (last write older than
`daily_living.health.memory_stale_hours`). `activity_ledger` includes per-`activity_type`
counts and last-write times over the same lookback, and `stale` (no write across any type
older than `daily_living.health.ledger_stale_hours`). An unreachable upstream semantic-memory
service is a degraded `200` (`reachable=False`, `stale=True`), not an error; a `503` means the
health service itself is unwired.

## People, presence, and CTS

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/persons` | List household members (includes optional `height_cm`) |
| `POST` | `/persons` | Create a household member (accepts optional `height_cm` in `[90, 220]`) |
| `GET` | `/persons/heights` | Minimal member standing-height sync feed for CTS (`persons.heights:read`; granted to `cts_ingress` and `admin`, reads local `household_members` only) |
| `GET` | `/persons/{person_id}` | Get a member |
| `GET` | `/persons/{person_id}/height-profile` | Combined operator-entered `height_cm` and effective CTS standing height profile (`learned` or `operator`, sample/camera counts, uncertainty; degrades cleanly with `cts_available: false` if CTS is unreachable) |
| `PATCH` | `/persons/{person_id}` | Update a member (including optional `height_cm` in `[90, 220]` or `null` to clear) |
| `DELETE` | `/persons/{person_id}` | Delete a member |
| `POST` | `/persons/{person_id}/enroll` | Upload face enrollment photos |
| `GET` | `/persons/{person_id}/enrollment` | Get enrollment status |
| `DELETE` | `/persons/{person_id}/enrollment` | Delete enrollment |
| `GET` | `/persons/{person_id}/prototypes` | List pose-binned face prototypes for one member (`face_prototypes:read`; presigns aligned-crop URLs, never returns raw keys) |
| `POST` | `/persons/{person_id}/prototypes/rebuild` | Rebuild pose-binned face prototypes for one member (`face_prototypes:write`) |
| `DELETE` | `/persons/{person_id}/prototypes/{prototype_id}` | Remove a face prototype and its underlying embedding(s), bumping `gallery_revision` (`face_prototypes:write`, 204; 409 if it would remove the last embedding) |
| `GET` | `/persons/roster-health` | Roster health: active, non-guest members with fewer than `roster.min_face_embeddings` enrolled face embeddings, plus the count of recurring visitor clusters awaiting review. Upstream failures return 502 rather than an empty roster |
| `GET` | `/identity/targets` | The household members every identity decision picks from (`identity_targets:read`, caregiver roles): active members by name with `is_guest`, `face_enrolled` (null when person identification is down), and optional ReID gallery counts. Not gated on CTS. Every admin selector reads it through the `identityTargets` store |
| `GET` | `/identity/review-vocabulary` | What each identity review decision changes (`identity_review:read`, caregiver roles): per surface (`visitors`, `face_calibration`, `reid_review`) its `guarantee` and its verdicts, each with the `effect` sentence (may contain `member_placeholder`), `needs_target`, `needs_enrolled_face`, and `batch`, plus `wearable_revocation_effect` for confirming wearable teaching revocation. Static text from `backend/services/identity_review/vocabulary.py`; the browser previews these sentences and batch responses report the same ones. No identity data |
| `GET` | `/identity/readiness` | Identity setup readiness (`identity_readiness:read`): eleven ordered steps (`roster`, `ingest`, `floor_frame`, `capture`, `labeling`, `artifact`, `face_policy`, `templates`, `body_gallery`, and optional `wearables` and `wearable_learners`), each with a `state` (`ready`, `attention`, `blocked`, `unknown`), a one-sentence `detail`, a closed `next_action`, and `optional`; plus `blocking_step`, the first required step that is blocked, and `review_queues`: `{surface, waiting}` for Visitors (surfaced clusters), Face calibration (unlabeled captures), and the ReID Review Queue (pending samples), `waiting` null when that owner could not be read. Read-only. A source that cannot be read (person-id, the tracking orchestrator's `GET /internal/identity/readiness`, rtsp-ingress) marks only its steps `unknown`; the route still answers 200. Counts only, never an identity id |
| `GET` | `/persons/{person_id}/location` | Current fused location envelope |
| `GET` | `/persons/locations` | Current fused locations for all tracked members |
| `GET` | `/persons/{person_id}/presence-history` | Presence history |
| `GET` | `/rooms/{room_id}/occupants` | Current room occupants |
| `GET` | `/persons/{person_id}/dwell` | Dwell summary |
| `GET` | `/occupancy` | Live room occupancy from the unified read-model (world tracker plus HA sensors); each room carries `person_ids`, `unknown_count`, and a `source` tag |
| `GET` | `/occupancy/history` | Smoothed occupancy time series for one room from Home Assistant. Query: `room_name` (required), `hours` (default `2.0`) |
| `GET` | `/signals/feed` | Unified caregiver signals feed: CTS dementia signals plus pipeline-rule notifications, each as a `SignalEnvelope` with `source`, `severity`, `room_name`, `created_at`, and `resolved` |

The occupancy read-model, the signals feed, roster health, and identity readiness each use one service function exposed through both the router and the matching MCP tool (`get_room_occupancy`, `get_signals_feed`, `get_roster_health`, `get_identity_readiness`). Room occupancy is keyed on PersonHypothesis with a short TTL, so unknown people are counted without a household identity. The legacy `emergency_alerts` table and `/alerts` endpoints were removed; caregiver alerts now flow through the signals feed.

### Visitors

Proxies person-identification-service's visitor clustering API. Naming
is a two-system transaction (face-service member, then a CC household member with `is_guest=true`)
orchestrated by `VisitorAdminService`. Permission: `visitors:review`, a named D4 grant
separate from the broad `caregiver`/`caregiver_admin` `GET /api/v1/*` globs, the same pattern as
`cts.identity.gallery_review`. No MCP tool: naming/dismissing/merging a visitor cluster is a
caregiver-admin action, not agent-facing (see `test_no_mcp_tool_for_visitor_mutations`).

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/visitors/clusters` | List visitor clusters. Query: `status` (`candidate`\|`surfaced`\|`named`\|`dismissed`\|`attributed`); an attributed cluster carries `attributed_person_id`, `reviewed_by`, `reviewed_at` |
| `GET` | `/visitors/clusters/{cluster_id}` | Cluster detail with recent sightings |
| `POST` | `/visitors/clusters/{cluster_id}/name` | Name a cluster: creates the face-service member and the CC household member |
| `POST` | `/visitors/clusters/review` | Decide about several clusters at once (`VisitorReviewRequest`: `cluster_ids`, `verdict`, `target_identity_id`). `is_member` attributes them to an active member with enrolled faces (422 otherwise); `not_enrolled` and `not_usable` dismiss them. Never enrolls anything. Returns `BatchReviewResponse`: one `{id, ok, error_code}` per cluster, `reviewed`, `failed`, and the `effect` sentence (the same one `/identity/review-vocabulary` serves, with the member's name). The actor is the API key's name |
| `POST` | `/visitors/clusters/{cluster_a}/merge/{cluster_b}` | Merge two clusters (same physical person split across two clusters) |

A 409 from any mutation means visitor clustering is disabled upstream (`visitors.clustering_enabled:
false` in person-identification-service); `GET /visitors/clusters` still serves whatever was already
surfaced. A 502 with `code: "visitors.partial_failure"` on `/name` means the face-service member was
created but the CC household member insert failed; the face-service call is idempotent on
`person_id`, so retrying the same request is safe.

### Face calibration

Proxies person-identification-service's calibration review API: an admin labels the faces
person-id sampled from tracker identify calls, which the offline `fit-v2` command then fits on.
Permission: `face_calibration:review`, a named D4 grant held only by
`caregiver_admin`. The labeler and promoter actor are the authenticated caller (`actor_from_auth`),
never a request field. person-id returns MinIO crop keys; the router presigns them into `crop_url`
(one hour) and sends no key or embedding to the browser. A label never changes the gallery; only
explicit promotion, an operator action, does. The only MCP tool is the read-only
`get_face_calibration_summary`; labeling, rejecting, deleting, and promoting are BFF-only.

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/face-calibration/candidates` | Captures, newest first. Query: `state` (`unlabeled` default \| `labeled` \| `rejected`), `limit` (1 to 200, default 50), `cursor` |
| `POST` | `/face-calibration/candidates/{candidate_id}/label` | Label a capture. Body: `label_kind` (`member` \| `not_enrolled` \| `not_a_face`), `label_identity_id` (required for `member` only; must be enrolled, else 422) |
| `POST` | `/face-calibration/candidates/review` | Label several captures at once (`FaceCalibrationReviewRequest`: `candidate_ids`, `verdict` `not_enrolled` \| `not_usable`, stored as `not_a_face`). Member labels are refused (one face at a time). Returns `BatchReviewResponse` with the effect sentence |
| `POST` | `/face-calibration/candidates/{candidate_id}/reject` | Mark a capture unusable; it is purged with unlabeled ones after 30 days |
| `POST` | `/face-calibration/candidates/{candidate_id}/promote` | Explicitly promote an eligible labeled `member` capture into that person's face gallery, rebuilding prototypes and advancing `gallery_revision` (no MCP tool) |
| `DELETE` | `/face-calibration/candidates/{candidate_id}` | Delete a capture and its crop (204). If already promoted, the promoted embedding stays in the gallery while the thumbnail reference is cleared |
| `GET` | `/face-calibration/summary` | Counts by state, label kind, quality decile, and camera; labeled faces and walks per resident against the target; promotable counts by identity and pose bin |

person-id's 404 (unknown capture) and 422 (bad label, unenrolled identity, bad cursor) pass
through; a person-id 5xx, timeout, unreachable service, or malformed envelope is a 502.

CTS routers expose camera admin, calibration, live data, PH identity review, presence configuration, signals, trajectories, overlap groups, and CTS window trigger definitions. These endpoints require CTS to be enabled through the shared `cts_enabled` dependency.

### CTS floor frame: calibration, shared views, learned transitions

Three different camera relationships, each with one owner. The tracking orchestrator reads the first two on every CC config sync, so a change reaches tracking within one sync interval.

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/cts/calibration/homography` | Fit and save one camera's homography (pixel to floor-plan metres). Permission: `cts.calibrate` |
| `DELETE` | `/cts/calibration/homography/{camera_id}` | Remove a camera's calibration, its visibility polygon, and its drift reference; keeps the floor region and marker. 404 `cts.calibration.no_homography` when there is none. Permission: `cts.calibrate` |
| `GET` | `/cts/calibration/health` | Per camera: `severity` (`ok`, `info`, `warning`, `error`) and `code` (`not_calibrated`, `elevated_residual`, `high_residual`, `runtime_matrix_missing`, `db_matrix_missing`) |
| `GET`, `POST` | `/cts/overlap_groups` | Shared views: sets of cameras that see the same floor area at the same time. Create rejects unknown or repeated camera ids with 422. Permissions: `cts.cameras.read`, `cts.cameras.write` |
| `DELETE` | `/cts/overlap_groups/{group_id}` | Delete a shared view; 404 when absent |
| `GET` | `/cts/overlap_groups/suggested` | Groups suggested from calibrated cameras whose visibility polygons overlap (coverage IoU at least 0.05), each with `declared` when an existing group already covers it, plus `uncalibrated_camera_ids`. Nothing is saved |
| `GET` | `/cts/topology/transitions` | Read-only handoffs CTS learned per ordered camera pair (`observation_count`, and `mean_transit_s`/`std_transit_s` of the delay between the earlier track's close and the new sighting, which is not a walk time); 503 when the orchestrator is unreachable |

There is no operator-edited adjacency graph: cameras that overlap are declared as shared views, and cameras along a walking route need no configuration.

### CTS analytics

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/cts/analytics/heatmap` | Aggregated floor-plan heatmap for a person. Query: `person_id`, `start_time`, `end_time`, optional `start_hour`/`end_hour` (0-23, UTC) for time-of-day filtering. Returns `HeatmapEnvelope` with `person_id` and `bins` (each with `x_m`, `y_m`, `weight`). Permission: `cts.analytics.heatmap.view`. Same service call as the `get_heatmap` MCP tool. |

## Knowledge and resident content

| Resource | Representative endpoints |
| --- | --- |
| Knowledge documents | `POST /knowledge/documents`, `GET /knowledge/documents`, `GET /knowledge/documents/{doc_id}`, `PATCH /knowledge/documents/{doc_id}`, approval, archive, restore, delete, re-embed |
| Knowledge images | `POST /knowledge/documents/{doc_id}/images`, `PATCH /knowledge/documents/{doc_id}/images/{img_id}`, `DELETE /knowledge/documents/{doc_id}/images/{img_id}` |
| Info cards | CRUD, approve, archive, restore, suggest, voice-instruction suggest (`info_cards:write`), and slot update endpoints under `/info-cards` |
| Quizzes | CRUD, approve, archive, restore, question CRUD, reorder, whole-list replace (`PUT /quizzes/{quiz_id}/questions`), voice-instruction suggest, and question image endpoints under `/quizzes` |
| Interactions | `GET /knowledge-interactions/queries`, `/quiz-sessions`, and `/info-card-deliveries` return `{items, total}`; `GET /knowledge/analytics/tags` (counts exclude archived items; the score pools graded answers of every quiz with the tag) |

- List filters: `GET /knowledge/documents`, `/info-cards`, and `/quizzes` take a repeatable `tag` parameter; an item matches when it carries any of the given tags.
- `POST /quizzes` accepts `questions` and creates them with the quiz in one transaction. `PATCH /quizzes/{quiz_id}` with `questions` saves the details and the whole list in one transaction (the editor's save); without `questions` it changes details only. `PUT /quizzes/{quiz_id}/questions` replaces the ordered question list atomically: listed ids are updated, items without an id are created, unlisted questions are deleted (409, nothing changed, if one has recorded answers; 403 without `quizzes:delete`). `POST /quizzes/{quiz_id}/questions/reorder` takes the complete order (every question once, ords `0..N-1`; 422 otherwise).
- A multiple-choice choice id must be non-blank and unique within its question (422 otherwise); drafted choices are given ids server-side.

Lifecycle rules the endpoints enforce:

- A new or edited document is chunked and embedded after it is saved; it reports `status: chunked` once its chunks exist. `POST .../reembed` re-embeds unchanged content and keeps an approved document approved (503 when the embedding service is unavailable, 409 when archived). Only text that differs sends a document back to review; editing an archived document keeps it archived until it is restored. The 10-minute retry job also re-embeds chunked or approved documents that have text but no chunks.
- Deleting an info card or quiz that any rule step references (enabled or disabled), or that has delivery or session history, returns 409; archive it instead. Deleting a quiz question that has recorded responses returns 409. Deleting a document referenced by a non-archived card or quiz returns 409.
- Approving a quiz requires at least one question, question text, two or more choices with one correct choice on multiple-choice questions, and an expected answer on open-ended questions (409 otherwise).
- Changing an approved info card to a layout whose `min_images` its slots cannot meet returns 409; slots the new layout has no position for are removed.
- Rejected image uploads (type, size, undecodable, pixel count) return 422.
- Interaction `date_from`/`date_to` are inclusive household calendar days in `app.timezone`.
- MCP parity: `list_senior_knowledge_queries`, `list_quiz_sessions_history`, and `get_quiz_tag_analytics` call the same `KnowledgeInteractionService` methods under `knowledge.interactions:read`.


## CTS camera profiles and optics

Hardware-neutral camera profiles live on `/cts/cameras` (`role`, `face_id_enabled`, `face_id_min_raw_similarity`, `horizontal_fov_deg`, `mounting_height_m`, `tilt_deg`, `ir_capable`, read-only `frame_natural_width` and `frame_natural_height`). The placement calculator routes delegate all pinhole math and interocular pixel band bounds to `cts_contracts.optics`.

| Method | Path | Permission | Description |
| --- | --- | --- | --- |
| `GET` | `/cts/cameras/{camera_id}/optics` | `cts.cameras.read` | Derived pinhole focal length, 24 px range, and expected interocular pixels at 1 to 5 m for a stored camera; syncs observed stream dimensions from CTS `/internal/calibration/status` when reachable |
| `POST` | `/cts/cameras/optics-preview` | `cts.cameras.read` | Stateless placement calculator preview for unsaved `horizontal_fov_deg` and `frame_natural_width` values |


## Wearables and RF nodes

Hardware-neutral registry of wearable tags, time-bounded consented member bindings, fixed RF nodes on the household floor plan, and wearable teaching revocation. Endpoints use D4 permission tokens (`wearables:read`, `wearables:write`, `wearables.teaching:write`, `wearables.site_config:read`). Two read-only MCP tools (`get_wearable_assignments`, `get_wearable_device_status`) call the same service methods as the router and share `wearables:read`; mutations (including teaching revocation and resume) are BFF-only and never exposed as MCP tools.

| Method | Path | Permission | Description |
| --- | --- | --- | --- |
| `GET` | `/wearables/devices` | `wearables:read` | List registered wearable devices with optional `active_only` filter and current active binding |
| `POST` | `/wearables/devices` | `wearables:manage` | Register a wearable device (`tag_id`, `device_kind`, `label`, `adapter_id`, `hardware_key`) |
| `PATCH` | `/wearables/devices/{device_id}` | `wearables:manage` | Update device label, active flag, adapter ID, or hardware key |
| `GET` | `/wearables/devices/{device_id}/bindings` | `wearables:read` | List chronological binding history (`valid_from`, `valid_to`, consent attribution) for one device |
| `POST` | `/wearables/devices/{device_id}/bind` | `wearables:manage` | Bind a device to an active household member; requires `consent_confirmed=true` and non-empty `consent_recorded_by`; closes any prior open binding on the device |
| `POST` | `/wearables/devices/{device_id}/unbind` | `wearables:manage` | Close the device's open binding (`valid_to = now()`) |
| `GET` | `/wearables/assignments` | `wearables:read` | Members grouped with all their currently bound devices (supporting multiple devices per member), plus unbound devices; shares one service call with MCP `get_wearable_assignments` |
| `GET` | `/wearables/nodes` | `wearables:read` | List fixed RF nodes (BLE receivers, UWB anchors, dual-radio nodes) |
| `POST` | `/wearables/nodes` | `wearables:manage` | Place a fixed RF node on the active calibrated floor plan (`x_m`, `y_m`, `z_m`, `role`, `technology`, optional UWB FiRa fields) |
| `PATCH` | `/wearables/nodes/{node_id}` | `wearables:manage` | Move or update a fixed RF node; validates coordinates against active floor-plan bounds |
| `DELETE` | `/wearables/nodes/{node_id}` | `wearables:manage` | Delete a fixed RF node (204) |
| `POST` | `/wearables/nodes/survey-check` | `wearables:read` | Compare a tape-measured distance between two nodes against their Euclidean distance on the floor plan; warns when discrepancy exceeds 0.15 m |
| `GET` | `/wearables/devices/{device_id}/associations` | `wearables:read` | List recent wearable-to-PH teaching segments for one device with taught counts (gallery rows, attested faces, live backfill ranges) and current tag teaching-hold status |
| `POST` | `/wearables/associations/{segment_id}/revoke` | `wearables:revoke_teaching` | Caregiver-admin only (`actor_from_auth(auth)`): demote `auto_verified` gallery rows from this segment, revoke its attested face captures in person-id, compensate live inferred backfill ranges, and pause further teaching on the tag |
| `POST` | `/wearables/tags/{tag_id}/resume-teaching` | `wearables:revoke_teaching` | Caregiver-admin only (`actor_from_auth(auth)`): clear an open teaching hold for a tag so future attested periods may teach again |
| `GET` | `/wearables/site-config` | `wearables.site_config:read` | Live site configuration (active nodes, devices, and open bindings in metres on the active floor plan) polled by CTS `CCConfigSyncService` and RF ingress adapters; granted to `cts_ingress` and `admin`, denied to `caregiver` |

Deleting a household member (`DELETE /persons/{person_id}`) closes any open wearable bindings for that member before removing the person row and preserves historical binding intervals with `member_id = null`.

## MCP endpoint

`/mcp` serves the Model Context Protocol (streamable HTTP) for external agents. Every
registered tool is listed; what a caller may invoke is decided per tool.

- **Key.** `X-API-Key` or `Authorization: Bearer <key>` only; a key in the query string is
  rejected (401).
- **Reaching the endpoint** requires the `mcp.tools:read` token (held by `mcp_readonly`; `admin`'s
  `*` covers everything).
- **Calling a tool.** Each `tools/call` is authorized against the tool's token before it runs
  (`MCPAuthMiddleware`, tokens registered in `backend/mcp/server.py`). Read tools need
  `mcp.tools:read`. State-changing tools need their own token:

  | Tool | Token | Granted to |
  | --- | --- | --- |
  | `import_rule_bundle` | `rules:import` | the agent key (via `rules:write_via_mcp`), admin |
  | `trigger_rule` | `rules:execute` | admin |
  | `acknowledge_dementia_signal` | `cts.signals:acknowledge` | admin |
  | `propose_identity_correction` | `cts.identity:propose` | admin |
  | resident session tools (quiz answers, guided steps, preferences, `submit_user_response`) | `resident_session:act` | no API key; voice companion only |

- **Denials.** A missing token answers 403 with a JSON-RPC error (code -32003); an unknown tool
  answers 404 (code -32004); a body over 1 MiB answers 413. A batch with one denied call is
  denied whole. Denials log `mcp_tool_denied` with the tool and the key's configured name.
- **Voice companion.** The in-process voice agent may declare and call exactly the tools named in
  `mcp.gemini_tools` (`config/settings.yaml`); an empty list grants none.

## Errors

Application errors are returned by the global exception handler as JSON. Common statuses:

| Status | Meaning |
| --- | --- |
| `400` | Invalid operation for the current resource state |
| `401` | Missing or invalid authentication |
| `403` | Authenticated key lacks permission |
| `404` | Resource not found |
| `409` | Conflict, such as a duplicate rule or step label |
| `422` | Validation error, including template and graph validation failures |
| `503` | Required service unavailable |
