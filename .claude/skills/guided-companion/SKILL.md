---
name: guided-companion
description: "Use when implementing or changing the guided task companion: routines, the guided-task state machine, interactive-session primitives, completion evaluators, the camera-selection cascade, the safety watch, escalation/takeover, or guided-task MCP tools."
---

# Guided Companion

Patterns for the always-on guided task companion (see
`/home/sriram/code/nanai/cognitive-companion/guided-companion-m00-overview.md` for
the full decision ledger). This skill adds only what is specific to guided tasks.
For naming, layering, testing, logging, time, and DB rules, follow
`/home/sriram/code/nanai/cognitive-companion/.claude/skills/engineering-standards/SKILL.md`.

## 1. Mental model: deterministic spine, agent per turn (D1)

A guided session is a deterministic state machine over a linear list of steps. The
**code** owns the journey: which step, attempt count, timeouts, and the decision to
advance, retry, skip, escalate, or abandon. The **live Gemini Live agent** owns the
conversation *within* a step: it speaks in her language and proposes "step done" by
calling a tool. The state machine validates that proposal before advancing.

Never let the agent own advancement, escalation, or safety. Those are code.

## 2. Module layout

```
backend/services/interactive_session/   shared session primitives (quiz + guided task)
backend/services/guided_task/
  state_machine.py     pure, deterministic, no I/O, injectable clock
  service.py           lifecycle: start / resume / tick / complete (owns I/O)
  store.py             routine/session/event persistence
  policy.py            resolve_policy(): global -> routine -> step precedence
  completion/          CompletionEvaluator protocol + ResponseEvaluator (+ M7 impls)
  safety/              SafetyWatch + the four conditions (M7)
  escalation/          minimal notify (M5), full ladder + takeover (M8)
  camera_selection.py  the D5 cascade (M7)
```

Layering (from engineering-standards): `state_machine.py` is pure and imports only
from `core/` and domain dataclasses. `service.py` orchestrates store, evaluators,
the interactive-session primitives, and the scheduler. Routers and MCP tools are
thin and call `service.py`; they never touch the store directly.

## 3. The state machine is pure and clock-injectable

`GuidedTaskStateMachine.decide(session_state, event, policy, now)` returns a
`Decision` dataclass (advance / retry / skip / escalate / abandon / wait) and never
performs I/O. All time comparisons use the injected `now`; tests advance a fake
clock and never sleep. This mirrors `PerCameraRateLimiter` and `CooldownTracker` in
`backend.services.aggregation`. The `service.py` layer applies the decision (writes
rows, schedules timers, injects prompts).

Inputs that move the machine: `step_completed` (validated tool call), `timeout_tick`,
`skip_condition_met`, `safety_event`, `caregiver_takeover`, `resume`.

## 4. Completion is gated by the response by default (D4)

`CompletionEvaluator` is a protocol:

```python
class CompletionEvaluator(Protocol):
    kind: str  # "response" | "vision_confirm" | "activity_signal" | "zone_presence"
    async def is_complete(self, session, step, evidence) -> CompletionResult: ...
```

`ResponseEvaluator` (M3) is the default and only gate until M7. Vision/activity/zone
evaluators are added in M7 behind this same protocol. A step's `completion_gate`
config selects evaluators; the response gate is always implicitly present so a step
can always advance on her confirmation. Never make vision the sole gate.

**Trigger / verifier / assist model (M23).** `evaluate_completion` partitions
evaluators into three roles, not one ordered list: the `response` evaluator is the
**trigger** (it must complete before anything else runs; if she has not confirmed,
no verifier or assist runs, and the step waits on "not_confirmed"); a configured
`vision_confirm` evaluator is a **verifier** that always runs once triggered,
regardless of `mode` (a negative or fail-closed verdict holds the step and feeds
the bounded-disagreement logic); `activity_signal`/`zone_presence` are **assists**
governed by `mode`: `"any"` treats them as advisory (their failure never blocks
advancement), `"all"` requires every configured assist to also complete. A
configured `vision_confirm` gate always runs on the done path; `mode` applies only
to assist gates. Never reintroduce first-complete-wins across the response gate.

## 5. Configuration precedence (resolve_policy)

Every `guided_task.*` value resolves: per-step override, then per-routine override,
then global `config/settings.yaml`. A `null` override inherits upward. Always call
`resolve_policy(routine, step, key)`; never read the global default directly when an
override may exist. This lets one long step (steeping tea) carry a longer
`step_timeout_s` than the routine.

## 6. Reuse the interactive-session primitives (do not duplicate the quiz)

Quiz and guided task share: a durable session row linked to an `execution_id`,
prompt injection into the live agent via
`connection_manager.send_backend_task(prompt, voice_instruction, metadata)`, the
`metadata.delivery_type` + `session_id` tagging consumed by `audio_handler`, a
scheduled session timeout, and `pipeline_executor.resume(execution_id, db)` on
completion. These live in `backend/services/interactive_session/` after M2. Call
them; do not re-implement prompt injection or pipeline park/resume in
`guided_task/`.

## 7. Session status and transitions

`GuidedSession.status`: `pending` -> `summoning` -> `active` -> `waiting` ->
(`escalated` | `caregiver_takeover`) -> (`completed` | `abandoned` | `failed`).
`waiting` means parked on a response or a timed step. `summoning` means presence-
gated and waiting for her to arrive. Every transition writes a `GuidedSessionEvent`.

## 8. MCP tools mirror the quiz tools (D3, single-service-layer)

Guided-task tools (`get_active_guided_step`, `mark_guided_step_complete`,
`repeat_guided_step`, `report_step_blocked`, `request_caregiver_help`) call
`GuidedTaskService` methods, never the store. Add them to the `mcp.gemini_tools`
allowlist in `config/settings.yaml`. Browser-visible data behind a router and a tool
reads the same service function (see the bff-api-design skill). The MCP registry
smoke test must still resolve every tool.

## 9. Camera selection and the coordinate convention (D5, D19, D25)

Select cameras for a vision check in this order: explicit `RoutineStep.camera_ids`
or `RoomZone.camera_ids`, then cameras with live identity detections of her in the
CTS buffer or event aggregator (reCamera), then zone-covering cameras, then all cameras in her room.

- **Source-tagged cameras (`ResolvedCamera`):** The cascade supports both CTS and reCamera.
  Callers query `select_cameras_tagged`, which returns a list of `ResolvedCamera(id, source)`
  objects, where `source` is `"cts"` or `"recamera"`. The legacy `select_cameras` remains
  as a backward-compatible, id-only wrapper that defaults to `"cts"` if no resolver or
  aggregator is provided.
- **Camera source resolver:** Constructed as `CameraSourceResolverService` in `main.py`,
  this resolver maps a camera/sensor ID to its source (`"cts"` if it exists in the `cts_cameras` table,
  or `"recamera"` if it exists in the `sensors` table).
- **Multi-source media polling:** `media_window_poll` partitions the tagged cameras,
  fetches CTS frames via `collect_recent_cts_frames` and reCamera images via `query_media_by_sensor`,
  then merges and sorts them chronologically before applying downsampling.
  The step outputs `"source": "mixed"` when both sources are present.

**Never use `cts_camera.visibility_polygon` as a runtime correctness input**: it is normalised
[0,1] image space and is wall-contaminated until Track G lands. Zone polygons are
floor meters, the same space as `location_observation.floor_x_m/floor_y_m`. Never
compare a meter polygon against a normalised polygon; convert through the camera
`homography_matrix`.

## 10. Safety watch (D14) and emergencies

A continuous watch runs for every active session and covers: abandonment/wandered-
off, hazard-left-active, prolonged no-motion/possible-fall, repeated
confusion/distress. Normal stalls go through the graduated ladder (retry, notify,
takeover). Emergencies (hazard, fall) skip the ladder and alert immediately. Safety
events enter the state machine as `safety_event`; the watch never advances steps.

## 11. Seamless to her, auditable for the caregiver (D18)

Caregiver interventions are spoken in the same agent voice and are never surfaced to
her as "human". Internally, every turn is attributed via `conversation_manager`
actor roles (`user`, `assistant`, `orchestrator`, `system`, and a caregiver role),
so the caregiver trail is fully auditable. Orchestrator/caregiver prompts are hidden
from her UI exactly as `audio_handler` already hides orchestrator prompts.

**Conversation linkage (M24, D18).** Guided sessions reference `conversation_sessions`
via `guided_sessions.conversation_session_id`, a nullable FK set once a realtime
companion session is open (`on_session_opened`, `_begin_session`) or, for a caregiver
message with no live realtime session, created on demand
(`GuidedTaskService._link_conversation`). Guided session ids and conversation session
ids are independent autoincrement sequences; never key a `conversation_manager` read
or write by a guided session id (`ensure_session(guided_session.id)` was the closed
G2/F3 bug). Every consumer (`caregiver_say`, `get_detail`, `FullEscalator._recent_transcript`,
`prune_retained_data`) reads or writes through `session.conversation_session_id`, and
linking always emits a `conversation_linked` `GuidedSessionEvent`.

## 12. Language and voice (D15)

Resolve the agent's system instruction with
`VoiceInstructionConfig.compose(step_type, base_instruction, step_override,
resource_override)`. The routine carries the language/voice override; the resident
profile is the next fallback; `config/settings.yaml` (Tamil/Tanglish/English) is the
default. The VLM reasons in English; the agent speaks her language. Do not translate
in code; let the agent handle language.

## 13. Privacy and retention (D13)

Store transcripts (via `conversation_manager`), step events, and outcomes. Do not
store raw audio. Prune transcripts and events past
`guided_task.transcript_retention_days` (default 30) with a scheduled job, the same
way `prune_observations` works for semantic memory.

**Retention prunes via the linkage (M24).** `prune_retained_data` collects the
`conversation_session_id` of completed sessions older than the retention window and
passes only those ids to `conversation_manager.prune_sessions`; it never passes a raw
guided session id. A conversation still linked to a *live* guided session is excluded
even if another guided session that shares it has aged out, so retention never deletes
a transcript still in active use.

## 14. Testing

- State machine: pure unit tests with a fake clock covering advance, retry to the attempt cap, skip-ahead, timeout, abandon after grace, safety preemption, resume. No DB.
- Service: conftest DB fixtures (never mock the DB); cover success, missing-service (agent/CTS/scheduler `None`), and edge cases (no steps, duplicate completion, resume race).
- MCP tools: parity/coverage tests per the bff-api-design skill; registry smoke test resolves every tool.
- Geometry: a wall-heavy synthetic camera proves zone containment is unaffected and that the visibility polygon is not a runtime input.

## 15. Anti-patterns specific to guided tasks

| Anti-pattern | Correct approach |
|---|---|
| Agent decides when to advance/escalate | Code (state machine) decides; agent only proposes via a tool |
| Vision required to advance a normal step | Response is the gate; vision is opt-in confirm/safety |
| Reading a global default when a routine/step override exists | `resolve_policy(routine, step, key)` |
| Re-implementing prompt injection or pipeline resume in `guided_task/` | Call the `interactive_session` primitives |
| Using `visibility_polygon` to decide camera coverage at runtime | Explicit `camera_ids` + detection-driven selection |
| Telling her an answer came from a human | Same voice, no attribution to her; audit internally only |
| Building a graph/branching routine | Linear with optional skip-ahead only |
| `time.sleep` / wall-clock in the state machine | Injected `now`; schedule via APScheduler |

## 16. Gate graphs (vision-gate graphs)

A vision-confirmation gate is a callable pipeline graph, represented as a `Rule` with `trigger_types == []`.
- **`gate_safe` and `gate_only` flags:** Step metadata declares `gate_safe: bool = True` for read-only perception/reasoning steps (e.g. `media_window_poll`, `scene_analysis`, `condition`, `gate_verdict`). The `gate_only` flag (True for `gate_verdict`) filters steps so they only appear in vision-gate graph palettes.
- **`gate_verdict` step:** The single required sink step of a gate graph. It evaluates a `complete_if` Lark-based expression, resolves JMESPath confidence and reason, and writes a standard `{complete, confidence, reason}` verdict block to `pipeline_data["gate_verdict"]`.
- **`validate_gate_graph`:** Validates gate safety constraints (no side-effects, single reachable `gate_verdict` step). Run-time/attach-time validation enforces the full check, while save-time incremental edits use `gate_safe_only=True` to allow temporary missing/unwired steps.
- **`GateGraphRunner`:** Executes a gate graph non-durably and without database persistence (no `WorkflowExecution` or `EventLog` writes). It constructs a transient in-memory `_SyntheticExecution` and `_SyntheticRule`, and a minimal `TriggerContext` to satisfy the `StepHandler.execute()` contract. Traversal is driven by the pure `traverse_dag` core function over a read-only DB snapshot of steps and edges.
- **Profiles:** Predefined parameter sets (`confirm`, `watch`) resolved before calling the runner:
  - Poll parameters (`window_s`, `max_frames`) are inherited by `media_window_poll` when set to `"inherit"` or `None` in step configuration.
  - VLM models are overridden in `llm_call` if `use_profile_model: true` and the profile specifies `model_id`.
  - Heavy pruning: steps configured with `heavy == True` are skipped as dead branches when `profile.prune_heavy` is True (typical for watch checks to save cost/latency).
- **Cool-off cache:** An in-memory cache keyed by `(session_id, step_ord, profile_name)` holding the last `GateVerdict` and timestamps. Callers check this cache first; if a verdict is younger than the configured `min_interval_s`, the cached verdict is reused without invoking the graph runner. **Cache polarity (M23, G3):** only positive watch verdicts (`complete=True` and `confidence >= min_confidence`) may warm the confirm cool-off slot; the watch slot itself is always warmed so its own throttle keeps working. Cached negative confirm verdicts are recorded as disagreement events (`reason="cached:<original_reason>"`) so the bounded-disagreement bound still accumulates while the confirm slot is fresh; a cached positive is never re-recorded.
- **Confirm Path & Profile Integration:** The linear routine spine completion path (`VisionEvaluator`) executes the gate graph in `confirm` mode via the `GateGraphRunner`.
- **Bounded Disagreement Rule (D24):** When a resident asserts "done" but the vision gate graph returns `complete=False` (disagreement), the session policy records the disagreement. After `max_disagreements` consecutive disagreements (counted durably via `GuidedSessionEvent` database records), the system defers to the resident and advances (using `actor="resident"`, emitting `vision_deferred` kind) or escalates (if configured with `on_max_disagreements: "escalate"`), avoiding trapping the resident.
- **Removed Camera Override:** The dead `camera_ids` override under `completion_gate.vision` is deleted; only step-level `camera_ids` are resolved. Any legacy keys like `camera_ids` or `description` are automatically stripped during schema ingestion.
- **Config Shape:** Under `completion_gate.vision`, the new config structure is structured under `gate_graph_rule_id`, `confirm`, and `watch` dictionaries.
- **Rich Audits:** Disagreements and successful gate runs emit `vision_confirm` events with detailed metadata (`profile`, `gate_graph_rule_id`, `cameras`, `complete`, `confidence`, `reason`, `node_results`, `cost`).
- **Watch Path & Profile Integration:** The watch profile runs the same gate graph in the `watch` profile on a background tick (cadence aligned with `safety_tick_s`). It runs advisorily and is isolated/fail-soft; any watch error is logged and caught so it never blocks the safety watch or tick loop.
- **Per-Session Watch Throttle:** Tracks `last_watch_at` in-memory per `(session, step_ord)`. Checks are skipped if run within the resolved `watch.tick_s` interval to control VLM execution costs.
- **Nag-Suppression:** When a recent watch verdict yields `complete == True` (or expected activity in node results) with `confidence >= watch.min_confidence`, `progress_seen_at` is set to `now`. When evaluating step timeouts/re-prompts, the system defers (extends) the deadline if progress was recently observed, suppressing unnecessary nags without blocking safety/abandonment checks.
- **Opt-in Auto-Advance:** When `watch.auto_advance` is enabled, the system count-checks the streak of consecutive successful watch verdicts durably from database events. If `watch.auto_advance_k` (default 3) consecutive high-confidence complete verdicts are seen, the session auto-advances under `actor="orchestrator"`, speaking a brief, warm encouragement transition. This is strictly forbidden on `is_safety_critical` steps.
- **Metrics (Confirm vs Watch):**
  - `vision_agreement` evaluates resident-asserted confirm vs vision verdict using the updated event detail shape.
  - `watch_summary` reports watch run counts, auto-advances, confirmation matching rate, and average cost (calls, frames, latency).
  - `gate_cost_summary` aggregates gate execution costs (model calls, frames, latency) for Confirm + Watch combined to analyze overall compute spend.

### Authoring a vision gate (preset-first, scoped canvas) (D26, D25, VG08)

The routine spine stays a linear step list (D16); only a gate's internals are a graph (D26). A caregiver authors a gate in two tiers:

- **Preset-first.** `CompletionGateEditor` shows a preset selector backed by `GET /api/v1/gate-presets`. Choosing a preset calls `POST /api/v1/gate-graphs {from_preset}` (the shared `gate_presets` factory) and stores the new `gate_graph_rule_id` in `completion_gate.vision`. Seeded presets: `generic_vlm_confirm` (poll -> VLM -> verdict), `kettle_on_hob` (the canonical cheap-first cascade: poll -> scene_analysis -> condition --true--> heavy VLM --> verdict; --false--> verdict, one sink via join), `person_at_sink`.
- **Power user.** "Edit vision logic" opens `GateEditorDialog` (`AppDialog size="xl"`) hosting `PipelineCanvas mode="gate"` (gate-safe palette) plus a test-run preview. Casual caregivers never open it.

The `completion_gate.vision` shape (VG0 section 4): `{ gate_graph_rule_id, confirm: {window_s, max_frames, min_confidence, min_interval_s, max_disagreements, on_max_disagreements, model_id}, watch: {enabled, tick_s, window_s, max_frames, model_id, auto_advance, auto_advance_k} }`. Empty override = inherit the `config/settings.yaml` default through `resolve_policy`; the editor shows the resolved default as a placeholder (precedence visible).

**One camera control (D25).** The dead `completion_gate.vision.camera_ids` override is gone. The step-level `CameraPicker` (`step.camera_ids`, labeled "Cameras for vision + selection") is the single picker, backed by the source-tagged cascade; empty = auto-select. Never surface visibility polygons as truth (D19); camera suggestions are labeled best-effort.

**The three sampling knobs** map to three layers: rate = `sample_period_s` (per `media_window_poll` node, set in the canvas), count = `max_frames` (per profile), cool-off = `min_interval_s` (gate-level throttle returning the cached verdict). The editor groups them under "Sampling and cool-off" so the caregiver's mental model matches the backend.
