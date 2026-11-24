---
name: guided-companion
description: "Use when implementing or changing the guided task companion: routines, the guided-task state machine, interactive-session primitives, completion evaluators, the camera-selection cascade, the safety watch, escalation/takeover, or guided-task MCP tools."
---

# Guided Companion

Patterns for the always-on guided task companion (see
`/home/sriram/code/nanai/notes/cc/guided-companion/guided-companion-m00-overview.md` for
the full decision ledger). This skill adds only what is specific to guided tasks.
For naming, layering, testing, logging, time, and DB rules, follow
`/home/sriram/code/nanai/cognitive-companion/.claude/skills/engineering-standards/SKILL.md`.

## 1. Mental model: deterministic spine, agent per turn

A guided session is a deterministic state machine over a linear list of steps. The
**code** owns the journey: which step, attempt count, timeouts, and the decision to
advance, retry, skip, escalate, or abandon. The **live Gemini Live agent** owns the
conversation *within* a step: it speaks in her language and proposes "step done" by
calling a tool. The state machine validates that proposal before advancing.

Never let the agent own advancement, escalation, or safety. Those are code.

## 2. Module layout

`service.py` is a thin façade; the actual concerns live in single-purpose
collaborator modules the façade builds once and delegates to:

```
backend/services/interactive_session/   shared session primitives (quiz + guided task)
backend/services/guided_task/
  state_machine.py     pure, deterministic, no I/O, injectable clock
  context.py           RuntimeContext: shared deps + cross-cutting helpers (leaf)
  service.py           GuidedTaskService façade: builds context + collaborators,
                        delegates every public method (composition root)
  routine_admin.py     routine CRUD, sanitize_completion_gate, gate-preview/test-run
  presentation.py      descriptors, voice dispatch, session reads, WS broadcast (leaf)
  retention.py         transcript/event pruning (leaf)
  memory_bridge.py     ledger/episode/preference writes on every terminal
                        transition (DL-M05, leaf; see skill section 13a)
  runtime.py           handle_completion, apply_decision, on_step_timeout,
                        maybe_skip_step, abandon (single funnel for every
                        abandon route, mirrors complete())
  resident_actions.py  repeat_step / report_blocked / request_help / resume
  summon.py            presence-gated start, summon announce/recheck
  watch.py             live tick: vision watch, resume-grace abandon, safety events
  caregiver.py         takeover surface: say / advance / complete / release
  completion/          CompletionEvaluator protocol + evaluators, disagreement.py
                        (bounded vision/response disagreement resolution, G1/D24)
  store.py             routine/session/event persistence
  policy.py            resolve_policy(): global -> routine -> step precedence
  safety/              SafetyWatch + the four conditions
  escalation/          minimal notify, full ladder + takeover
  camera_selection.py  the D5 cascade
```

Layering (from engineering-standards): `state_machine.py` is pure and imports only from `core/` and domain dataclasses. `presentation.py`, `retention.py`, and `memory_bridge.py` are leaves depending only on `context.py` (plus, for `presentation.py`, the `GUIDED_TASK_DELIVERY_TYPE` constant from `agent_voice.py` and `interactive_session.tagging`, to build its voice owner key); `runtime.py` depends on `presentation.py` and `memory_bridge.py`; `summon.py`, `watch.py`, and `caregiver.py` depend on `runtime.py` and `presentation.py`. `RuntimeContext` is held by reference everywhere (bootstrap setters like `set_zone_service` write through it, so already-built collaborators see the update). No collaborator reaches into another's private (`_`-prefixed) attributes; cross-cutting calls go through a constructor-injected public method or callable. Routers and MCP tools are thin and call `service.py`; they never touch the store, or any collaborator module, directly. A structural test (`test_guided_task_module_sizes.py`) keeps every module in this list under 500 lines.

## 3. The state machine is pure and clock-injectable

`GuidedTaskStateMachine.decide(session_state, event, policy, now)` returns a
`Decision` dataclass (advance / retry / skip / escalate / abandon / wait) and never
performs I/O. All time comparisons use the injected `now`; tests advance a fake
clock and never sleep. This mirrors `PerCameraRateLimiter` and `CooldownTracker` in
`backend.services.aggregation`. The `service.py` layer applies the decision (writes
rows, schedules timers, injects prompts).

Inputs that move the machine: `step_completed` (validated tool call), `timeout_tick`,
`skip_condition_met`, `safety_event`, `caregiver_takeover`, `resume`.

## 4. Completion is gated by the response by default

`CompletionEvaluator` is a protocol:

```python
class CompletionEvaluator(Protocol):
    kind: str  # "response" | "vision_confirm" | "activity_signal" | "zone_presence"
    async def is_complete(self, session, step, evidence) -> CompletionResult: ...
```

`ResponseEvaluator` is the default gate. `VisionEvaluator`, `ActivitySignalEvaluator`, and
`ZonePresenceEvaluator` implement the same protocol. A step's `completion_gate`
config selects evaluators; the response gate is always implicitly present so a step
can always advance on her confirmation. Never make vision the sole gate.

**Trigger / verifier / assist model.** `evaluate_completion` partitions
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
`metadata.delivery_type` + `session_id` tagging consumed by `audio_handler`, an
`enable_microphone` broadcast before each spoken step (she answers aloud), a
scheduled session timeout, and `resume_owning_pipeline(scheduler, execution_id)` on
a terminal transition (it schedules the resume under the executor's
`resume_{execution_id}` job, off the caller's path, replacing the `wait_until`
fallback). These live in `backend/services/interactive_session/`. Call
them; do not re-implement prompt injection or pipeline park/resume in
`guided_task/`. A delivery's realtime instruction always includes the base
persona (`llm.realtime.system_instruction`) and is released by its owner key
(`voice_owner_key`) through `ConnectionManager.release_voice_instruction`; for a
guided session that is `Presentation.release_voice`, called by `Runtime.complete`
and `Runtime.abandon`. Steps reach the companion socket through
`ServiceContainer.ws_manager`, never through another service's private attributes.

## 7. Session status and transitions

`GuidedSession.status`: `pending` -> `summoning` -> `active` -> `waiting` -> (`escalated` | `caregiver_takeover`) -> (`completed` | `abandoned` | `failed`). `waiting` means parked on a response or a timed step. `summoning` means presence-gated and waiting for her to arrive. Every transition writes a `GuidedSessionEvent`.

**Skip conditions.** A step's `skip_condition` (`{"kind": ...}`) is dispatched from two places only: `activity_signal` / `zone_presence` are evaluated on step entry (`_begin_session`, and the advance/skip branch of `_apply_decision`, via `maybe_skip_step`); `response_says_done` fires only when the agent passes `already_done=True` into `mark_guided_step_complete` and the current step names that kind. Either path dispatches the `skip_condition_met` event into the state machine exactly like any other event; the state machine still owns the transition (advance, skip, or complete). Never evaluate a skip condition from inside an evaluator or a router; `maybe_skip_step` (`runtime.py`) is the single dispatcher.

## 8. MCP tools mirror the quiz tools (D3, single-service-layer)

Guided-task tools (`get_active_guided_step`, `mark_guided_step_complete`,
`repeat_guided_step`, `report_step_blocked`, `request_caregiver_help`) call
`GuidedTaskService` methods, never the store. Add them to the `mcp.gemini_tools`
allowlist in `config/settings.yaml`. Browser-visible data behind a router and a tool
reads the same service function (see the bff-api-design skill). The MCP registry
smoke test must still resolve every tool.

## 9. Camera selection and the coordinate convention

Select cameras for a vision check in this order: explicit `RoutineStep.camera_ids` or `RoomZone.camera_ids`, then cameras with live identity detections of her in the CTS buffer or event aggregator (reCamera), then zone-covering cameras, then all cameras in her room. The cascade is source-tagged: `select_cameras_tagged` returns `ResolvedCamera(id, source)` where `source` is `"cts"` or `"recamera"` (resolved via `CameraSourceResolverService`, built in `main.py`); the legacy `select_cameras` is a backward-compatible, id-only wrapper. `media_window_poll` partitions tagged cameras, fetches CTS frames via `collect_recent_cts_frames` and reCamera images via `query_media_by_sensor`, merges them chronologically, and outputs `"source": "mixed"` when both are present.

**Never use `cts_camera.visibility_polygon` as a runtime correctness input**: it is normalised [0,1] image space and is wall-contaminated until Track G lands. Zone polygons are floor meters, the same space as `location_observation.floor_x_m/floor_y_m`; never compare a meter polygon against a normalised one without converting through the camera `homography_matrix`.

**A floor point is written only when the source event carries real coordinates.** Absence of floor data is `None`, never `(0, 0)`: a synthetic origin point must not masquerade as a real floor position and silently poison zone lookup, zone-based camera selection, `zone_presence` completion, or the safety watch's expected-room check. Every ingestion path that can write a `FloorPoint` (`services/cts/world_observation_subscriber.py`, and any future source; the reCamera path, `services/person_location/face_sighting_ingest.py`, never writes floor points) gates construction on an explicit `is not None` check of the real coordinate fields, never a `.get(key, 0.0)` default. `PersonLocationService.ingest_room_transition` has no floor-point parameters; a transition event's floor coordinates are dead data until a milestone actually persists them.

**`max_cameras` and `max_frames` are independent budgets.** The camera-cascade cap comes from `guided_task.vision.max_cameras` (default 3, overridable per profile via `vision.confirm.max_cameras` / `vision.watch.max_cameras`, resolved through `resolve_vision_override`). `max_frames` is the per-camera frame budget passed to the `GateProfile` for the poll nodes. Never pass one where the other belongs: many frames from few good cameras beats one frame from many cameras for VLM reasoning.

## 10. Safety watch and emergencies

A continuous watch runs for every active session and covers: abandonment/wandered-
off, hazard-left-active, prolonged no-motion/possible-fall, repeated
confusion/distress. Normal stalls go through the graduated ladder (retry, notify,
takeover). Emergencies (hazard, fall) skip the ladder and alert immediately. Safety
events enter the state machine as `safety_event`; the watch never advances steps.

**Ownership rule:** the state machine owns attempts/timeout escalation
exclusively, through `timeout_tick`. `GuidedTaskSafetyWatch` must never check `idle_s > policy.step_timeout_s` or emit `abandoned` on idle time; an idle check in the safety watch races with `on_step_timeout` and defeats vision-watch `nag_suppressed` (where `progress_seen_at` holds retry prompting without advancing `last_activity_at`). The same holds for `Watch.tick`'s idle abandon: for an `active`/`waiting` session it is only a backstop for a timeout job lost on restart, so it fires after `step_timeout_s + resume_grace_s` measured from the later of `last_activity_at` and the step's `progress_seen_at` (owner decision 2026-11-23: sustained vision progress holds off abandonment, relaxing the VG6 "suppression only delays" bound); a `summoning` session keeps the plain `resume_grace_s`. `progress_seen_at` and `last_watch_at` are TTL caches whose TTL must outlive any step timeout plus the grace; a TTL equal to the grace silently forgot progress. The safety watch owns perception conditions
only (`left_expected_room`, `hazard_active`, `no_motion`, `confusion_distress`) and each fires at most once per **arm window**, never per tick. A step is armed when it is entered (`step_entered`) and re-armed when a caregiver releases takeover (`takeover_ended` on that step), so a stove still on after the caregiver hands the session back escalates again. Every condition checks `GuidedTaskStore.has_event(session_id=..., kind="safety_event", step_ord=step.ord, detail_condition=..., since=armed_at)` before emitting, and judges only evidence since `armed_at`: no-motion signals with `received_at >= armed_at`, `step_blocked` reports counted on this step since `armed_at`. Never anchor on `last_activity_at`: every retry bumps it, which would hide a fall signal that arrived just before a retry. The hazard look is gated on the raw left-room check (or `is_safety_critical`), not on whether the left-room escalation already fired. Perception conditions run only for `active`/`waiting` sessions: a `summoning` resident is by definition not yet in the step's room. When multiple conditions fire on the same tick, `Watch.tick` records each as its own `safety_event` row (the secondaries carry `coalesced_into`) and calls `apply_decision` once for the most severe (`emergency > high > medium > low`), so the caregiver never receives duplicate escalation notifications on a single tick. Hazard frame collection (`_hazard_event`) uses `select_cameras_tagged` and `collect_recent_frames_multi_source` (CTS bucketizer + reCamera `event_aggregator`), never CTS-only `select_cameras`, so a reCamera-only room is checked too. When consuming CTS signal kinds (e.g.
the no-motion condition's kind set), guard the local subset against the canonical
`ALL_SIGNAL_KINDS` with a `subset <= set(ALL_SIGNAL_KINDS)`-style test so a future
kind rename cannot silently orphan the subscription.

**Escalation channel boundary (caregiver-only vs resident-facing).** Escalation notifications dispatched by `FullEscalator` contain caregiver diagnostic payloads (session ID, failure reason, recent transcript, and `/admin/guided-sessions/{id}` takeover URL). They must go exclusively to caregiver channels and must never be dispatched to the resident's companion WebSocket (`ws_manager` on `/ws/audio`), the tablet popup, e-ink, or in-home speakers. In-room audio or tablet popups of diagnostic escalation dumps startle and disorient a resident with dementia. The boundary is an allowlist, `escalation/channels.py::caregiver_channels` (`telegram`, `webhook`), applied by both `FullEscalator` and `NotifyOnlyEscalator` to the global setting and to `escalation_channels_override`; anything else is dropped with `guided_escalation_resident_channel_skipped`. It never returns an empty list, because the notification dispatcher treats an empty list as "use the alert level's defaults", which include the popup, e-ink, and speakers; it falls back to `telegram` instead. Escalators never force a channel in on emergencies. `FullEscalator` takes no companion socket at all: its `guided_escalation` event goes to the admin console broadcaster (`/ws/pipeline`) only.

## 11. Seamless to her, auditable for the caregiver

Caregiver interventions are spoken in the same agent voice and are never surfaced to
her as "human". Internally, every turn is attributed via `conversation_manager`
actor roles (`user`, `assistant`, `orchestrator`, `system`, and a caregiver role),
so the caregiver trail is fully auditable. Orchestrator/caregiver prompts are hidden
from her UI exactly as `audio_handler` already hides orchestrator prompts.

**Takeover and release voice invariants.**
- `Caregiver.inject_caregiver_message` must compose the system instruction via `ctx.voice_instructions.compose("guided_task", base_instruction, resource_override=routine.system_instruction_override)` plus `compose_language_directive`, matching `AgentSessionVoice.speak_step`. Never pass a raw `routine.system_instruction_override` that drops `guided_task_default` when the override is empty.
- When `caregiver_advance` is called while `session.status == "escalated"`, it must record a `takeover_started` event before transitioning to `"caregiver_takeover"`.
- When `release_takeover` returns the session to `"active"`, if the current step was entered during the takeover (its latest `step_entered` is at or after the latest `takeover_started`), it calls `presentation.speak(updated, step, is_retry=False)` so the resident hears the new step at once rather than sitting in silence until it times out. A release on the step the takeover began on does not repeat it.

**Live session telemetry (`broadcast_session_update`).** Every session transition is announced once. `Runtime.apply_decision` is the seam for decisions: it applies the decision through the private `_apply` and then broadcasts the landed state; a skip cascade (`maybe_skip_step`) re-enters `_apply`, not `apply_decision`, so it announces only where it lands. Callers that transition outside `apply_decision` announce themselves: `_begin_session` (`session_started`), a summoning start (`summon_started`), the summon timeout, `ResidentActions` (`repeat_step`, `report_blocked`, `request_help`), the escalated-unanswered abandon, and the caregiver actions. `complete()` and `abandon()` do not broadcast, so their callers' single announcement is not doubled. `broadcast_session_update` sends the diagnostic `guided_session_update` to the admin console broadcaster (`/ws/pipeline`) only, then calls `broadcast_resident_state`, which sends the resident-safe `GuidedSessionStateEvent` (`guided_session_state`: routine name, status, step, total, prompt) to `ws_manager` (`/ws/audio`). Its `prompt_text` is rendered with `include_agent_context=False` (no `memory_context` or `preferences`, which are agent context such as how the routine went last time) and is empty unless a step is in progress. Never send the console event, failure reasons, or transcript to `/ws/audio`.

**Multimodal senior companion surface and native Android / TV hardware capabilities.** A senior with dementia frequently experiences presbycusis (age-related hearing loss), working-memory decay, and loss of executive initiation (they cannot be expected to walk up to a sleeping tablet and tap a microphone button).
- While a guided session is in `active`, `waiting`, `escalated`, or `caregiver_takeover`, the Companion surface (`CompanionView.vue`) must display a guided-task widget with the current step prompt in high-contrast large typography (`>= 24px` on tablet, `>= 36px` on TV), step progress (`Step X of N`), and large touch/D-pad targets (`>= 64px` height) for `"I'm Done"`, `"Repeat"`, and `"I Need Help"`, wired over `/ws/audio` (`guided_step_action`) to `GuidedTaskService`.
- **Surface-targeted hardware activation (`surface_id` routing):** WebSocket connections on `/ws/audio?surface_id=<id>` register their `surface_id` with `ConnectionManager`. When a sensor cue, routine start, or step prompt targets a specific room or `surface_id`, `ConnectionManager.send_to_surface(surface_id, ...)` dispatches `surface_hardware_command` (`wake_screen`, `enable_microphone`, `enable_camera`, `volume_min_pct`, `attention_chime`) **only** to the surface(s) in the resident's active room, never activating microphones or waking screens in empty rooms.
- **Native Android Tablet & Google TV shell:** On Android tablets (`kind="tablet"`) and Google TV / Android TV (`kind="tv"`), the Capacitor + Kotlin native shell (`CompanionForegroundService` + `CompanionHardwarePlugin`) sets `mediaPlaybackRequiresUserGesture = false`, wakes the screen (`setTurnScreenOn(true)` / HDMI-CEC One-Touch Play on TV), activates hardware-AEC microphone capture and optional front-camera face/attention verification (`CameraX` + ML Kit Face Detection) without requiring a tap, and releases the microphone/camera back to ambient mode as soon as the session ends. Every senior-facing dialog (`QuizDialog.vue`, `InfoCardDialog.vue`, `InteractivePromptDialog.vue`, and the guided-task widget) must support both touch (tablet) and D-Pad spatial navigation (`ArrowUp`/`ArrowDown`/`Enter` on Android TV).

**Conversation linkage.** Guided sessions reference `conversation_sessions`
via `guided_sessions.conversation_session_id`, a nullable FK set once a realtime
companion session is open (`on_session_opened`, `_begin_session`) or, for a caregiver
message with no live realtime session, created on demand
(`RuntimeContext.link_conversation`). Guided session ids and conversation session
ids are independent autoincrement sequences; never key a `conversation_manager` read
or write by a guided session id (`ensure_session(guided_session.id)` was the closed
G2/F3 bug). Every consumer (`caregiver_say`, `get_detail`, `FullEscalator._recent_transcript`,
`prune_retained_data`) reads or writes through `session.conversation_session_id`, and
linking always emits a `conversation_linked` `GuidedSessionEvent`.

## 12. Language and voice

Resolve the agent's system instruction with `VoiceInstructionConfig.compose(step_type, base_instruction, step_override, resource_override)`. The routine carries the language/voice override (`Routine.language_override`, `Routine.voice_override`); `config/settings.yaml` (Tamil/Tanglish/English) is the default. The VLM reasons in English; translation is otherwise left to the agent, not code.

**The directive seam (`AgentSessionVoice`).** When `Routine.language_override` is set, `backend/services/guided_task/language.py::compose_language_directive` renders the `guided_task_language_directive` template from `config/knowledge_voice.yaml` with the display name resolved from `app.language_names`, and appends it to the composed instruction. This runs at every seam that speaks to her: `AgentSessionVoice.speak_step` (every step and retry) and `GuidedTaskService._inject_caregiver_message` (caregiver relays). An unmapped language code degrades loudly (passes through verbatim, logs `guided_language_name_unknown`) rather than mistranslating silently. `Routine.voice_override` has no runtime effect yet (Gemini Live cannot switch voice mid-session); it is passed through for forward compatibility and logs `guided_voice_override_unsupported` once per session so the gap stays visible.

**The literal-TTS seam (`_announce_summon`).** The summon announcement plays before a companion session exists, so it cannot rely on the agent. Its text is a per-language map, `guided_task.summon_messages` in `config/settings.yaml`, resolved in order: `Routine.language_override`, then `tts.default_language`, then `"en"`. A resolved language missing from the map falls back to `"en"` (text and `tts_language` together) and logs `guided_summon_language_missing`.

**Anti-pattern.** Resident-facing strings must never be hardcoded English in service code. Agent-path strings are instruction templates in `config/knowledge_voice.yaml` (the agent renders them in her language); literal-TTS strings (dispatched straight to a speaker channel, bypassing the agent) are per-language maps in `config/settings.yaml`.

## 13. Privacy and retention

Store transcripts (via `conversation_manager`), step events, and outcomes. Do not
store raw audio. Prune transcripts and events past
`guided_task.transcript_retention_days` (default 30) with a scheduled job, the same
way `prune_observations` works for semantic memory.

**Retention prunes via the linkage.** `prune_retained_data` collects the
`conversation_session_id` of completed sessions older than the retention window and
passes only those ids to `conversation_manager.prune_sessions`; it never passes a raw
guided session id. A conversation still linked to a *live* guided session is excluded
even if another guided session that shares it has aged out, so retention never deletes
a transcript still in active use.

## 13a. What a session writes to memory

Every terminal transition (`complete()` **and** `abandon()`, the latter's single funnel
being `Runtime.abandon()`, which every abandon call site -- `apply_decision`'s abandon
branch, `summon.py`'s summon-timeout, `watch.py`'s escalated-unanswered -- goes through
instead of calling `ctx.mark_abandoned` directly) invokes
`memory_bridge.py::GuidedMemoryBridge.on_session_terminal(session)`. It writes up to
three destinations, by information type:

1. **Activity ledger** (`ActivitySession`, via `ctx.activity_service`): **only** when
   `session.status == "completed"` **and** `routine.activity_type` is set. An abandoned
   or failed session never writes a ledger row, even if the routine has an
   `activity_type` -- a false "she took her medication" is a care-safety hazard.
   Confidence and provenance are folded into `metadata` (`source="guided_companion"`,
   `guided_session_id`, `routine_id`, `confidence"`), since `ActivitySession` has no
   dedicated confidence column.
2. **Episodic observation** (semantic memory, via `ctx.scene_intel.persist_observation`):
   on **every** terminal outcome, exactly one per session. `kind="guided_episode"`,
   `person_id=session.person_id`, `source="guided_companion"`,
   `object_list=[routine.name]`, no fake room key (`room_id=None` -- `Routine` has no
   room field). Per-step writes are forbidden; this is the only semantic-memory write in
   the guided-task package (DL8's single write seam, via `scene_intel`, never the raw
   `semantic_memory_client`). The description is a deterministic 2-4 sentence template
   (`memory_bridge.build_episode_description`): outcome, duration, local start hour,
   completed/skipped/stalled step ordinals, total retries plus the most-retried step,
   and escalation count. Text-embedded via the shared Triton `embedding_client`
   (`app.state.embedding_client`, the same instance the knowledge repository uses) into
   `description_embedding`, never the CLIP `embedding` column; an unavailable embedder
   degrades to no embedding, not a failed write.
3. **Durable preferences** (knowledge repository, via the `record_resident_preference`
   MCP tool, not the bridge): use only for a stable preference ("two sugars"), never a
   transient fact. Stored as a `KnowledgeDocument` tagged
   `["resident_preference", person_id]`; the top 3, shortest-first, are read back into
   `{{ preferences }}` in every step's prompt via `Presentation._preferences`.

**Best-effort, never fails the transition.** Each write is independently wrapped: a
failure logs `guided_memory_bridge_error` and appends a `memory_write_failed`
`GuidedSessionEvent` (`detail.target` is `"ledger"` or `"episode"`); success appends
`ledger_recorded` / `episode_recorded`. The bridge never raises into `complete()` /
`abandon()`.

**Personalization read-back (DL-M05 Part E.1).** `Presentation._memory_context` (the
same seam that renders scene-memory context into prompts) also looks up the most recent
`kind="guided_episode"` observation matching `objects_any=[routine.name]` and
`person_id=session.person_id`, and contributes **one condensed sentence**
("Last time this routine: completed in 14 minutes; step 1 needed 3 tries.") to
`{{ memory_context }}`. One seam, hard-capped at one sentence -- do not add a second
prompt-compose hook for this.

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
| Parking an owning pipeline execution on a single step's timeout | The park ceiling (`guided_task_start`) is routine-scale: summon budget plus every step's `step_timeout_s * max_step_attempts`, capped by `guided_task.max_pipeline_park_s` |
| An unbounded per-session in-memory dict (`{}`) on a service that runs forever | `cachetools.TTLCache`, sized and evicted on terminal transitions (`RuntimeContext.evict_runtime_state`); TTL is a memory bound only, never the correctness gate |

## 16. Gate graphs (vision-gate graphs)

A vision-confirmation gate is a callable pipeline graph: a `Rule` with `trigger_types == []`, built from `gate_safe` steps (`media_window_poll`, `scene_analysis`, `condition`, `gate_verdict`) and ending on exactly one `gate_verdict` sink (`gate_only=True`), which writes `{complete, confidence, reason}` to `pipeline_data["gate_verdict"]`. `GateGraphRunner` (`gate_runner.py`) executes it non-durably (no `WorkflowExecution` row). Two profiles resolve before the run: `confirm` (authoritative, on "done") and `watch` (advisory, background tick, fail-soft, forbidden on `is_safety_critical` steps). Mechanism detail beyond the two rules below (profile parameter inheritance, nag-suppression, auto-advance streak counting, the `vision_agreement`/`watch_summary`/`gate_cost_summary` metrics) lives in `gate_runner.py`, `metrics_service.py`, and the VG00-VG08 ledger, not here.

**Cool-off cache polarity.** Keyed by `(session_id, step_ord, profile_name)`. Only a positive watch verdict (`complete=True` and `confidence >= min_confidence`) may warm the confirm slot; the watch slot is always warmed so its own throttle works. A cached *negative* confirm verdict is still recorded as a disagreement event (`reason="cached:<original_reason>"`) so the bounded-disagreement bound keeps accumulating; a cached positive is never re-recorded.

**Bounded disagreement.** When she says "done" but the gate returns `complete=False`, the disagreement is recorded. After `max_disagreements` consecutive disagreements (counted durably via `GuidedSessionEvent` rows), the system defers to her (`actor="resident"`, `vision_deferred`) or escalates if `on_max_disagreements: "escalate"` is configured. Never trap her behind a camera that will not agree.

**Config shape and single-source sanitization.** `completion_gate.vision: {gate_graph_rule_id, confirm: {window_s, max_frames, max_cameras, min_confidence, min_interval_s, max_disagreements, on_max_disagreements, model_id}, watch: {enabled, tick_s, window_s, max_frames, max_cameras, min_confidence, model_id, auto_advance, auto_advance_k}}`; empty = inherit the `config/settings.yaml` default through `resolve_policy`. The key lists live once, in `backend/schemas/_completion_gate.py::normalize_completion_gate`, called by both `RoutineStepIn.validate_completion_gate` and `routine_admin.sanitize_completion_gate`, so schema validation and service persistence never drift. The runtime profile models (`VisionConfirmConfig`, `VisionWatchConfig` in `domain.py`) ignore unknown fields, so every key the sanitizer keeps must also be declared there, or it is saved and then silently dropped at evaluation time. Both `VisionEvaluator.is_complete` and `Watch._vision_watch_tick` must pass `confirm_cfg.max_cameras` / `watch_cfg.max_cameras` into `resolve_val(...)` before falling back to `guided_task.vision.max_cameras`.

### Authoring a vision gate

The routine spine stays linear; only a gate's internals are a graph. A caregiver picks a preset (`CompletionGateEditor` -> `GET /api/v1/gate-presets` -> `POST /api/v1/gate-graphs {from_preset}`, the shared `gate_presets` factory; seeded: `generic_vlm_confirm`, `kettle_on_hob`, `person_at_sink`) or, as a power user, opens `GateEditorDialog` (`PipelineCanvas mode="gate"`) to edit and test-run the graph directly. Casual caregivers never open the canvas.

**One camera control.** The dead `completion_gate.vision.camera_ids` override is gone; the step-level `CameraPicker` (`step.camera_ids`) is the single picker, backed by the source-tagged cascade; empty = auto-select. Never surface `visibility_polygon` as truth.

**Three sampling knobs, three layers.** Rate = `sample_period_s` (per `media_window_poll` node), count = `max_frames` (per profile), cool-off = `min_interval_s` (gate-level throttle). The editor groups them under "Sampling and cool-off" so the caregiver's mental model matches the backend.
