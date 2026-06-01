# API Reference

All HTTP endpoints are served under `/api/v1`. Endpoints require authentication unless a router explicitly documents a device or webhook auth path.

Authentication is resolved from API keys, device keys, or route-specific secrets. Authorization is enforced through `config/auth.yaml` permission patterns.

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

## People, presence, and CTS

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/persons` | List household members |
| `POST` | `/persons` | Create a household member |
| `GET` | `/persons/{person_id}` | Get a member |
| `PATCH` | `/persons/{person_id}` | Update a member |
| `DELETE` | `/persons/{person_id}` | Delete a member |
| `POST` | `/persons/{person_id}/enroll` | Upload face enrollment photos |
| `GET` | `/persons/{person_id}/enrollment` | Get enrollment status |
| `DELETE` | `/persons/{person_id}/enrollment` | Delete enrollment |
| `GET` | `/persons/{person_id}/location` | Current fused location envelope |
| `GET` | `/persons/locations` | Current fused locations for all tracked members |
| `GET` | `/persons/{person_id}/presence-history` | Presence history |
| `GET` | `/rooms/{room_id}/occupants` | Current room occupants |
| `GET` | `/persons/{person_id}/dwell` | Dwell summary |

CTS routers expose camera admin, calibration, live data, PH identity review, presence configuration, signals, trajectories, overlap groups, and CTS window trigger definitions. These endpoints require CTS to be enabled through the shared `cts_enabled` dependency.

## Knowledge and resident content

| Resource | Representative endpoints |
| --- | --- |
| Knowledge documents | `POST /knowledge`, `GET /knowledge`, `GET /knowledge/{doc_id}`, `PATCH /knowledge/{doc_id}`, approval, archive, restore, delete, re-embed |
| Knowledge images | `POST /knowledge/{doc_id}/images`, `PATCH /knowledge/{doc_id}/images/{img_id}`, `DELETE /knowledge/{doc_id}/images/{img_id}` |
| Info cards | CRUD, approve, archive, restore, suggest, and slot update endpoints under `/info-cards` |
| Interactions | `GET /knowledge-interactions/queries`, `/quiz-sessions`, and `/info-card-deliveries` |

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
