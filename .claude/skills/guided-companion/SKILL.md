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
