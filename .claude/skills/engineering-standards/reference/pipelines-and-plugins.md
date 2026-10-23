# Pipelines, plugins, and domain recipes

Read before adding a step, channel, or filter, consuming a new CTS signal kind, or touching guided tasks, CC-local signals, or inference load. Part of the `engineering-standards` skill; the rules summary is in `../SKILL.md`.

## Consuming a new CTS signal kind

The producer-side recipe is `/home/sriram/code/nanai/continuous-tracking/.claude/skills/cts-signals/SKILL.md`. On the CC side, start with a grep inventory rather than assuming signal kinds have one registry:

```bash
grep -rn "stillness_anomaly" backend/ frontend/ \
  --include='*.py' --include='*.js' --include='*.ts' --include='*.vue' -l
grep -rn "signal_kind\|signal_type\|knownSignalKinds" backend/ frontend/ \
  --include='*.py' --include='*.js' --include='*.ts' --include='*.vue'
```

Check each of these touchpoints:

| Touchpoint | Current location and rule |
|---|---|
| Protobuf subscriber validation | `backend/services/cts/subscriber.py::_PROTO_KIND_TO_STR`. A protobuf enum not mapped here is rejected by `decode`; add the enum-to-string mapping and a decode/persist round-trip test |
| Alert profiles | `backend/services/cts/signal_config.py` and any profile controls in `frontend/src/views/admin/PersonsView.vue` |
| Pydantic enums or Literals | Search `backend/schemas/`; current signal envelopes use `str`, but any future `Literal` must be extended |
| Rule filter choices | `backend/filters/builtin/dementia_signal.py` and `frontend/src/components/pipeline/steps/index.js` |
| Narrative and feed | `backend/services/cts/signal_narratives.py`, `backend/services/signals/feed.py`, and `backend/schemas/cts_envelopes.py` |
| Frontend labels/icons | Search kind arrays/maps in Tracking, signal, keyframe, profile, and rule views; add i18n entries if that surface uses i18n |

**Forward-compatibility rule.** Unknown string kinds already stored or returned by an API must render generically, not crash. Backend fallbacks convert `my_future_kind` to a human-readable label in `SignalsFeedService` and `DementiaSignalEnvelope.from_dict`. Frontend surfaces use underscore-to-space labels and must use a generic icon or severity icon when a kind-specific icon map misses. Never index a map and then call a method on the possibly missing value.

Required tests for a new kind:

1. Subscriber protobuf decode and persistence round trip in `backend/tests/services/test_dementia_signal_subscriber.py`.
2. `dementia_signal` filter match and non-match in `backend/tests/filters/test_dementia_signal_filter.py`.
3. Unified feed or envelope rendering in `backend/tests/services/signals/test_feed.py` or the nearest feed test.
4. Frontend kind label/icon plus unknown-kind fallback under `frontend/tests/`.
5. MCP/BFF parity and `config/auth.yaml` coverage if an envelope or endpoint changes.

## Plugin development

### Adding a step, channel, or filter

Three rules apply to all plugin types:

1. **Single file, no wiring.** Drop a file into the `builtin/` directory. The `@*Registry.register` decorator handles discovery.
2. **Metadata is mandatory.** `StepMetadata`, `ChannelMetadata`, or `FilterMetadata` must be complete: display name, description, icon (for steps), config schema, default config.
3. **Zero-config by default.** `default_config` must produce a working handler without any user overrides.

Image-space geometry questions (person in a part of the frame) use the
`region_presence` step over `scene_detections`; never spend a model call on a
geometry question. `region_presence` coordinates are normalized image space;
floor-space `RoomZone` meters are a different space and the two are never
mixed.

Channel and notification-dispatch code that emits links in outbound messages
(Telegram, email, any channel a remote caregiver reads on a phone) resolves them
against `app.public_base_url` in `config/settings.yaml` (empty by default, which
keeps relative links for in-app surfaces that do not need an absolute origin).
`FullEscalator._takeover_url` in
`backend/services/guided_task/escalation/full.py` is the reference implementation:
prefix when the base is configured, strip its trailing slash, keep the relative
form when empty. No base configured is a degrade, not an error.

When consolidating duplicate handlers into one, prefer a single canonical step
type. `media_window_poll` is the canonical example: it serves both the CTS and
reCamera sources through one handler, selected by its `source` config (`auto`,
`cts`, `recamera`). The former `cts_window_poll` and `recamera_media_poll` step
types were removed once no stored rules referenced them.

Rule matching (`RulesEngine`) is async end-to-end: a context filter's
`evaluate` may be sync or async, and the engine awaits it on the caller's
running loop. **Never bridge a coroutine with `run_until_complete` inside
request/loop context anywhere in this codebase** -- every production trigger
path already runs on the event loop, and `run_until_complete` raises there.
`RulesEngine` receives the shared `ServiceContainer` at construction; a new
filter that needs a service adds the field to the container (with
`assert_container_complete` and consumer-guard coverage per the note below)
rather than importing a service module directly. Every builtin filter must
have a through-the-engine test (`tests/filters/test_filters_through_engine.py`)
proving both its match and its fail-closed behavior.

### Step handler contract

```python
@StepRegistry.register
class YourStepHandler(StepHandler):
    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="your_step",          # snake_case, unique across all steps
            display_name="Your Step",       # human-readable
            category="action",              # perception | reasoning | action | state | flow
            icon="mdi-star",
            description="What this does.",
            config_schema={"type": "object", "properties": {}},  # JSONSchema
            default_config={},
        )

    async def execute(
        self,
        step: PipelineStep,
        execution: WorkflowExecution,
        pipeline_data: dict,
        trigger: TriggerContext,
        services: ServiceContainer,
    ) -> StepResult:
        return StepResult(data={"output_key": value})
```

- Access only the `ServiceContainer` fields your step uses. Don't reference fields that might be `None` without checking.
- Return `StepResult(success=True, data={...})` on success.
- Return `StepResult(success=False, data={"error": "..."})` on expected failure.
- Let unexpected exceptions bubble; `PipelineExecutor` handles them.
- `ServiceContainer` is built exactly once in the lifespan and shared by reference with the
  executor, the gate runner, and the rules engine. Late-phase services are assigned onto the
  shared instance (never onto a private copy, never via `executor._services`).
  `assert_container_complete` (`backend/services/container_wiring.py`) runs at the end of
  startup and must be extended when a new field or feature flag is added. Every container field
  must have a consumer in `steps/` or `filters/` (`tests/steps/test_container_field_consumers.py`);
  a field without a consumer is deleted, not kept for later.

### Pipeline DAG execution contract

Pipelines are directed graphs, not ordered lists. A single output port may
**fan out** to multiple target steps, and a step may **fan in** (join) from
multiple parents. There is no unique constraint on `(source_step_id, source_port)`.

- `build_adjacency(edges)` returns `{source_step_id: {source_port: [target_step_id, ...]}}` (targets are a list, in edge-insertion order). Anything consuming adjacency must iterate the list, never index a single target.
- The executor (`_run_steps`) is **in-degree gated**, not a plain BFS. Each outgoing edge resolves as *live* (the source activated that port) or *dead* (the source took another branch). A node runs once all incoming edges are resolved and at least one is live; a node whose incoming edges are all dead is **skipped**, and the skip propagates to its descendants. A join therefore runs exactly once, after every parent. The only step that produces dead edges today is `condition` (it emits `true` xor `false`); every other step emits `main`.
- `wait` / `interactive_prompt` inside a **parallel branch** is not supported: pausing serializes the run and resume only rebuilds work downstream of the paused step, so a sibling branch would be silently dropped. The executor detects this (`abandoned = run_set - resolved - descendants(waiting_step)`) and **fails loudly** with a `ValidationError` rather than losing a branch. Keep waits on a linear segment. (Resuming all branches across a wait is a future enhancement; persist the traversal frontier if you implement it.)

**Authoring-time vs execution-time graph validation.** `validate_graph(..., check_entry=...)` separates the two. The "exactly one entry node" rule is an *execution* invariant, enforced by the executor, rule import, and the read-only `GET /rules/{id}/validate` endpoint (which surfaces it as a non-blocking `graph_errors` warning). The edge-save endpoint (`PUT /rules/{id}/edges`) passes `check_entry=False`, because a pipeline under construction routinely has unwired steps (multiple entry nodes) and must remain editable. Structural checks (unknown step refs, invalid ports, cycles) always run. Never re-add the entry-count check to the edge-save path; it makes incremental editing and edge deletion 422.

### Running a pipeline subgraph non-durably (the GateGraphRunner pattern)

When you need to execute a subset or variation of a pipeline without storing state or starting database transactions (e.g. evaluating a vision-confirmation gate rule), use the `GateGraphRunner` pattern.

1. **Reuse traversal core:** Never duplicate the DAG traversal logic. Reuse the existing pure traversal core functions: `traverse_dag`, `build_adjacency`, `build_graph_snapshot`, `apply_step_result`, and `resolve_pipeline_value`.
2. **Synthetic execution & trigger context:** To support the `StepHandler` interface without DB persistence:
   - Construct minimal, in-memory python class instances (e.g., `_SyntheticExecution` and `_SyntheticRule`) that duck-type only the fields actually read by the handlers.
   - Enforce that these objects are never added to a SQLAlchemy session.
   - Below is the current mapping of fields read by gate-safe handlers:
     - `media_window_poll`: execution `.id` (used as lookback window key and for logs).
     - `scene_analysis`: trigger `.sensor_id`, `.room_name`.
     - `llm_call`: execution `.rule.name` (for trace tags), trigger `.room_name`, `.sensor_id`, `.media_type`.
     - `gate_verdict` and `condition`: access only `pipeline_data`.
3. **Short-lived read transactions:** Only query metadata (steps/edges) using a short-lived read-only session, and close it before traversal starts.
4. **Three-layer gate-safety check:** Cross-link with the `gate_safe` convention (defined in `guided-companion` skill Section 16). Enforce that step types are `gate_safe` during graph validation, rule attachment/execution prep, and at runner runtime. Refuse the entire run if any unsafe node type is present.
5. **Fail closed per node:** Run each node's handler under `asyncio.wait_for` with a timeout. If a handler throws an exception or times out, catch it, log `gate_node_failed`, and return an empty set of active ports (frozenset) to fail the node closed. Never let a node-level exception escape the traversal to crash the runner.

## Guided task and interactive sessions

Guided tasks are long-lived, stateful coaching sessions. A deterministic state
machine owns advancement, retry, skip, escalation, abandonment, and timeouts; the
live agent owns only the per-turn conversation. Load the full guided-companion
skill before changing this area:
`/home/sriram/code/nanai/cognitive-companion/.claude/skills/guided-companion/SKILL.md`.

Configuration precedence for every `guided_task.*` policy value resolves from the
global default, then the routine override, then the step override, with the most
specific non-null value winning. Use `resolve_policy(...)`; never read a global
default directly when a routine or step override may exist.

The guided-task state machine must be pure and clock-injectable. Pass the current
time into decisions, and use fake clocks in tests instead of sleeping. Use
`PerCameraRateLimiter` and `CooldownTracker` in `backend.services.aggregation` as
references for injectable time patterns.

Do not duplicate the quiz session mechanics. Shared prompt injection, durable
session tagging, timeouts, and pipeline park/resume belong in
`backend/services/interactive_session/`, and guided-task code calls those
primitives.

Full patterns:
`/home/sriram/code/nanai/cognitive-companion/.claude/skills/guided-companion/SKILL.md`.

## CC-local signals and shadow-mode detectors

CC-local signals are emitted from pipelines only via the `signal_emit` step, which validates against the CC-local kind allowlist (`backend.services.cts.signal_config.CC_LOCAL_SIGNAL_KINDS`); rules can never emit CTS-produced kinds. `signal_emit` writes through `SignalsService.emit()` (`backend/services/signals/service.py`), never the raw `SignalStore` from a step; this mirrors the semantic-memory single-write-seam rule. Every CC-local emission sets `evidence_grade="experimental"` unconditionally: `SignalStore.acknowledge()` only persists caregiver feedback for that grade. New detectors ship shadow-first: signal + notification only, with the labeling workflow and a flip gate documented in their milestone.

A rule with `trigger_types` containing an event-fired kind (`dementia_signal`, dispatched via `PipelineExecutor.fire_event`) reads that event's payload from `pipeline_data["trigger_event"]`, never from `TriggerContext` directly: `resume()` rebuilds a synthetic `TriggerContext` from persisted `pipeline_data["trigger"]` alone, so a field added only to the dataclass would vanish across a wait/resume cycle. `resolve_person_id()` (`backend/steps/_helpers.py`) falls back to `trigger_event.person_id` last, so `signal_emit`/`presence_query` steps in an event-fired rule resolve the right person without an explicit `person_id` in their step config.

Full detector-authoring guidance (dedup/cool-off patterns, the prefilter-confirm-join shape, `media_presign`, the signal-kinds table, the shadow-mode labeling/precision workflow) lives in the `daily-living` skill:
`/home/sriram/code/nanai/cognitive-companion/.claude/skills/daily-living/SKILL.md`.

## Inference budget (single-Spark deployments)

One DGX Spark serves the Triton model zoo, the vLLM vision model, the llama.cpp reasoning model, and TTS, fed by 9 to 12 cameras. Every rule, gate graph, and watch tick that adds inference must be admission-controlled and cheap-first: reuse CTS outputs before geometry/novelty gating, before a caption, before text reasoning, before the VLM.

**Local model calls go through the admission controller and carry a `caller` tag; never call a local provider around it.** `LLMAdmissionController` (`backend/integrations/llm/admission.py`) is the single choke point at the provider boundary: `OpenAICompatibleProvider` and `OllamaProvider` wrap their network call in `admission.admit(lane, caller)` whenever a controller is injected (constructed once in the bootstrap LLM phase, `backend/bootstrap/core_services.py`). A queued call that exceeds `llm.admission.queue_timeout_s` raises `LLMAdmissionTimeout` rather than piling up; `llm_call` (`backend/steps/builtin/llm_call.py`) converts that into a structured `StepResult(success=False, ...)`, never an uncaught exception. The cloud realtime provider (Gemini) is exempt by construction. Every local provider call must carry a `caller` tag so telemetry (`GET /api/v1/admin/inference-telemetry`) can attribute load.

**Watch-profile gate graphs are VLM-free unless a node is explicitly `watch_allowed`.** `GateGraphRunner.execute_node` (`backend/services/guided_task/gate_runner.py`) refuses to execute a vision-capable `llm_call` node in the `watch` profile unless the step's config sets `watch_allowed: true`. This is a structural guarantee, not a convention: an accidental Spark-melting watch tick cannot happen just because a node was never tagged.

Full tier table, the `novelty_gate` authoring pattern, and the tier-0 pre-flight checklist live in the `daily-living` skill:
`/home/sriram/code/nanai/cognitive-companion/.claude/skills/daily-living/SKILL.md`.
