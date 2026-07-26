---
name: daily-living
description: "Use when implementing or changing daily-living detection, the activity ledger, hygiene/intent signals, semantic-memory writes, rule bundles, or inference load governance."
---

# Daily Living

Patterns for the Daily Living program: countable daily-life facts (medication, meals, TV,
hygiene, task intent), the shadow-mode detectors that produce them, and the inference budget
that keeps them cheap on a single DGX Spark. Full decision ledger and findings inventory:
`/home/sriram/code/nanai/daily-living-m00-program-overview-and-findings.md`. For naming,
layering, testing, logging, time, and DB rules, follow
`/home/sriram/code/nanai/cognitive-companion/.claude/skills/engineering-standards/SKILL.md`.
For guided-session memory writes specifically, also load
`/home/sriram/code/nanai/cognitive-companion/.claude/skills/guided-companion/SKILL.md` section 13a.

## 1. The three-layer memory architecture (DL2)

Three stores, three jobs. Never let one answer another's question:

| Layer | Store | Owns | Never |
| --- | --- | --- | --- |
| Activity ledger | `ActivitySession` rows (`backend/models/person.py`), `ActivitySessionService` (`backend/services/activity_session.py`), `DailyReportService` (`backend/services/daily_report.py`) | Countable/duration facts: did she eat, how long did she watch TV, has she taken medication | Never derive a count by aggregating semantic-memory captions with an LLM |
| Evidence layer | Semantic-memory observations/movements (`scene_intel`, SMS) | Scene recall, alert evidence, "what did she do around 3pm" | Never the source of truth for a countable answer |
| Task execution | `GuidedSessionEvent` (`backend/models/guided_task.py`) | Guided-routine step-by-step audit trail | Not queried directly for daily-life questions; feeds the ledger/episode via the memory bridge |

**Typed-first question answering.** A caregiver's countable question ("has she had her
medication today", "how many times did she eat", "how long did she watch TV") is parsed to a
typed query and aggregated in SQL via `DailyReportService`/`ActivityTimelineService`, never
answered by semantic search over captions. The MCP tools `get_daily_report`,
`get_person_timeline`, `get_open_sessions` (`backend/mcp/server.py`, allowlisted in
`config/settings.yaml`'s `mcp.gemini_tools`) are the typed surface; semantic search
(`semantic_memory_query` step, SMS recall tools) is for open-ended recall and evidence only.

## 2. Writing memory

### The `scene_intel` seam (DL8, DL-M02)

Every CC write to semantic memory goes through `backend/services/scene_intel/`
(`SceneIntelService.persist_observation` / `persist_movements`, or the composed `persist` for
analyze-then-write). Never call the semantic-memory client's write methods directly from a
step, subscriber, or service outside `scene_intel/`; there is exactly one write seam, checked
by a repo-wide grep for `semantic_memory_client.create_observation` /
`.create_movement` outside `backend/services/scene_intel/`.

Callers build an `ObservationDraft` (`backend/services/scene_intel/types.py`), never the raw
`ObservationCreate` wire dataclass:

```python
@dataclass(frozen=True)
class ObservationDraft:
    room_id: str | None = None
    description: str = ""
    object_list: list[str] = field(default_factory=list)
    hazard_flags: list[str] = field(default_factory=list)
    embedding: list[float] = field(default_factory=list)              # CLIP, image similarity
    source: str = "scene_intel"
    person_id: str | None = None                                       # DL-M05
    kind: str = "scene"                                                 # DL-M05
    description_embedding: list[float] = field(default_factory=list)  # embeddinggemma, text search
```

`kind`/`person_id` semantics (DL-M05, closes L3): `kind` is a record-kind taxonomy
(`"scene"` for CTS scene samples and person movements, the default so legacy writers keep
working unchanged; `"guided_episode"` for guided-session episodic writes). `person_id` is
optional attribution; a `None` value means the observation cannot be attributed to a specific
household member (most CTS scene-sample writes). `embedding` (CLIP) and `description_embedding`
(embeddinggemma text) are separate columns; never conflate them, and never send an empty
embedding list as `[]` where the caller means "no embedding" (`persist_observation` sends
`NULL`, avoiding a pgvector dimension-mismatch on `vector(768)`).

### One episode per session (DL7b, DL-M05)

`GuidedMemoryBridge.on_session_terminal` (`backend/services/guided_task/memory_bridge.py`)
writes exactly one narrative episodic observation per guided session, on **every** terminal
outcome (complete, abandon, fail) via `_write_episode`. Per-step semantic-memory writes are
forbidden; they would blur search with noise no caregiver query needs. The description is a
deterministic template (`build_episode_description`): outcome, duration, local start hour,
step ordinals by outcome, retries, escalation count.

### The completed-only ledger rule (DL9)

A guided session writes an `ActivitySession` row (`_write_ledger`) only when
`session.status == "completed"` **and** `routine.activity_type` is set. An abandoned or failed
session never writes a ledger row, even if the routine has an `activity_type`. Rationale (DL9):
a false "she took her medication" from an interrupted session is a care-safety hazard, not a
data-quality nicety; honesty about evidence grade is load-bearing. The same rule applies to
rule-bundle-driven ledger writes (`activity_session_start`/`_end` steps): they open/close
sessions from observed behavior (TV on + presence, meal-room dwell), never from an unconfirmed
inference.

### Provenance is a column, not a metadata key

Every ledger write records how it was produced and how much to trust it, on the row itself:
`ActivitySession.source` (`ActivitySourceEnum` in `backend/models/person.py`) and
`ActivitySession.confidence`. Both are required parameters of
`ActivitySessionService.open_session()` and flow through the `ActivityService` facade, the
`activity_session_start` step (`source` is a step config field), the
`POST /api/v1/activities/sessions/open` router, and `GuidedMemoryBridge._write_ledger`.

| `source` | Meaning | Supports the claim |
| --- | --- | --- |
| `guided_companion` | Confirmed step-by-step during a **completed** guided routine | "she took her medication with me at 9:05" |
| `ha_state_join` | Home Assistant entity state joined with presence | "the TV was on and she was in the room" |
| `sensor` | Reported by a physical sensor | "the sensor registered it" |
| `vision_inferred` | Inferred from camera analysis | "she was near the medicine cabinet" (never that she took anything) |

Two safety behaviors are deliberate and must not be "cleaned up": an unrecognized `source`
string degrades to `vision_inferred` (the weakest grade) with a warning rather than raising, so
a detector typo can never inflate an answer's confidence; and the idempotent-reuse path returns
the **stored** provenance, not the caller's, so a later weak sighting cannot appear to restate a
strong claim.

Read side: `DailyReportService._aggregate_medication` splits `doses_taken` into
`confirmed_doses` (guided only) and `inferred_doses`. Phrase medication answers off
`confirmed_doses`; `doses_taken` is the all-sources total and on its own supports no claim that
she actually took anything.

**`metadata_json` is a plain JSON column wrapped in `MutableDict.as_mutable(JSON)`.** Never
mutate it in place without that wrapper: SQLAlchemy detects attribute *replacement*, not
in-place writes, so `row.metadata_json["k"] = v` on an already-populated dict is silently
discarded at flush. This bug lived in `close_session`/`close_timed_out_sessions` and silently
dropped `closed_via` for exactly the rows that carry metadata. Both sites now rebuild the dict
(`{**(old or {}), "closed_via": ...}`); prefer that explicit form over relying on the wrapper.

## 3. Detectors

### Rule-bundle mechanism and placeholder convention (DL-M04)

Detectors ship as importable single-rule `RuleBundle` JSON documents under
`config/rule_bundles/` (one file per rule; the schema is single-rule, so a milestone's "one
bundle" is often several files). Deployment-specific values (a resident's `person_id`, a room
name, an HA entity id, a camera sensor id) are `__UPPER_SNAKE__` placeholder tokens documented
in the bundle's own `description` field, replaced by the operator before
`POST /api/v1/rules/import`. Never hardcode a real household member id, room name, or entity id
into a checked-in bundle. Existing examples:
`config/rule_bundles/daily_living_tv_open.json`, `daily_living_meal_open.json`,
`daily_living_tea_intent_shadow.json`, `daily_living_hygiene_confirm.json`.

### Shadow-first lifecycle and flip gates (DL10)

Every new detector ships notify-only or emission-off, with a measurement path in the same
milestone, and flips on only after measurement supports it. Flips are config changes, never
code changes.

Worked example, the tea-intent shadow detector (DL-M06, `daily_living_tea_intent_shadow.json`):
kitchen dwell (`daily_living.intent.dwell_minutes`, default 3) plus a cheap vision cascade emits
`tea_intent_suspected` and notifies the caregiver only; it never calls `guided_task_start`. The
caregiver labels each signal Accurate / Not agitation / Unsure in `SignalsPanel.vue`
(`POST /api/v1/cts/signals/{signal_id}/ack`). Precision over a rolling window:

```sql
SELECT
  date_trunc('week', received_at) AS week_start,
  round(
    count(*) FILTER (WHERE feedback = 'accurate')::numeric
      / NULLIF(count(*) FILTER (WHERE feedback IN ('accurate', 'inaccurate')), 0),
    3
  ) AS precision
FROM public.cts_dementia_signals
WHERE signal_type = 'tea_intent_suspected'
GROUP BY 1
ORDER BY 1 DESC;
```

Flip gate: two consecutive weeks with precision >= 0.7 AND at least 10 labeled detections AND
zero "she was asleep/absent" false fires among the `inaccurate` rows (read `context_json ->>
'reason'` on those rows manually; `feedback` has no dedicated false-fire-reason column). The
flip itself (config change from notify-only to `guided_task_start`) is additionally gated by
DL1(a): hardening M23+M24+M25+M27 must be landed, and `guided_task_start` must handle
`request_start`'s `ConflictError` for a live session (tracked in hardening M25's addendum) so a
cron-driven trigger does not log a failed execution every tick during a live session.

### `signal_emit` and the CC-local kind allowlist

`signal_emit` (step) is the only way a pipeline writes a CC-local signal; it validates against
`backend.services.cts.signal_config.CC_LOCAL_SIGNAL_KINDS` and writes through
`SignalsService.emit()` (`backend/services/signals/service.py`), never the raw `SignalStore`.
Rules can never emit CTS-produced (wire) kinds. Every CC-local emission sets
`evidence_grade="experimental"` unconditionally, which is what makes the caregiver
Accurate/Inaccurate/Unsure feedback buttons persist (`SignalStore.acknowledge()` only records
feedback for that grade). Current registry (`CC_LOCAL_SIGNAL_KINDS`):
`inferred_dwell_exceeded`, `tea_intent_suspected`, `hygiene_routine_missed`.

### The prefilter-confirm-join shape (DL-M08)

Cross-system detectors that combine a cheap CTS-side signal with a CC-side confirmation follow
one shape: cheap upstream signal (CTS emits a wire kind, e.g. `same_clothes_suspected`) -> one
bounded VLM confirmation (CC, `llm_call` over presigned evidence keyframes via `media_presign`)
-> structured join with local evidence (CC, e.g. the bathroom-dwell shower proxy built on
`PersonLocationService.room_segments`/`dwell_episodes`) -> alert + CC-local signal
(`hygiene_routine_missed`). Alerts always carry the evidence that produced them (presigned
keyframe URLs from both days). A VLM disagreement with the CTS prefilter ends the rule with no
notification; it is calibration data for the CTS-side threshold, not a code path to build
around. `daily_living_hygiene_confirm.json` is the reference bundle; it is also the first
`dementia_signal`-triggered rule with real pipeline steps, which is why
`PipelineExecutor.fire_event()` and `resolve_person_id()`'s `trigger_event` fallback tier exist
(see engineering-standards skill section 27).

## 4. Signal kinds table

| Kind | Producer | Vocabulary | Evidence contract | Feedback |
| --- | --- | --- | --- | --- |
| `tea_intent_suspected` | CC, `daily_living_tea_intent_shadow` rule bundle (`signal_emit`) | CC-local | Notification with a snapshot frame URL interpolated into the message text (no Telegram image attachment path built for this kind) | Accurate/Not agitation/Unsure via `SignalsPanel.vue`; precision SQL above |
| `same_clothes_suspected` | CTS, daily appearance-profile evaluator (DL-M07) | `cts_contracts.DementiaSignalKind` (wire) | Day-over-day quality-weighted PH `gallery_mean` centroid cosine similarity above `hygiene.same_clothes.similarity_threshold` (0.90 default); requires `hygiene.same_clothes.min_samples_per_day` (5 default) quality-weighted samples per day or emits no verdict | Backtested against historical data before live emission (DL-M07); live flip blocked on the backtest data gap as of the last verified state, re-check `daily-living-m07-*.md`'s own dated notes before assuming it is flipped |
| `hygiene_routine_missed` | CC, `daily_living_hygiene_confirm` rule bundle (`signal_emit`, joins CTS's signal with the shower proxy) | CC-local | VLM comparison of the two days' best keyframe crops (`media_presign` step) plus the bathroom-dwell shower proxy (`presence_query`'s `room_dwell_history` mode over `PersonLocationService.dwell_episodes`); alert fires only when clothes match AND no qualifying bathroom dwell in the lookback window (`hygiene.shower.window_hours`, 26h default) | Same generic experimental-grade feedback path as any CC-local kind |

`ALL_SIGNAL_KINDS` (`backend/services/cts/signal_config.py`) derives dynamically from
`cts_contracts.DementiaSignalKind` plus `CC_LOCAL_SIGNAL_KINDS`; a new kind registers in exactly
one of those two places, never both, and preset profile membership guard tests assert every
profile member is in `ALL_SIGNAL_KINDS`.

## 5. Inference budget (DL5)

One DGX Spark serves the whole model zoo for 9-12 cameras. Cheap-first, admission-controlled:

| Tier | What | Cost | Example |
| --- | --- | --- | --- |
| 0 | Reuse CTS outputs already paid for | free | `presence_dwell` filter, `PersonLocationService.room_segments` |
| 1 | Geometry + CLIP-delta novelty gating | near-free | `region_presence`, `novelty_gate` |
| 2 | Florence-2 caption | cheap | `scene_analysis` |
| 3 | Text reasoning over structured context | moderate | `llm_call` (text model) |
| 4 | The vLLM VLM | expensive, globally rate-limited | `llm_call` (vision model), admission-controlled |

**Admission controller contract.** `LLMAdmissionController`
(`backend/integrations/llm/admission.py`) is a two-lane (`"vision"` / `"text"`) semaphore at the
provider boundary; `OpenAICompatibleProvider` and `OllamaProvider` wrap their network call in
`admission.admit(lane, caller, model_id=...)` whenever a controller is injected (built once in
`backend/bootstrap/core_services.py`). A queued call older than
`llm.admission.queue_timeout_s` (20s default) raises `LLMAdmissionTimeout`, which `llm_call`
(`backend/steps/builtin/llm_call.py`) converts to a structured `StepResult(success=False, ...)`,
never an uncaught exception. Every call site carries a `caller` tag (rule name, or
`"gate:{profile}"` for gate-fired executions) so `GET /api/v1/admin/inference-telemetry` can
attribute load. The cloud realtime provider (Gemini Live) is exempt by construction; it does not
load the Spark.

**`novelty_gate` pattern.** Skip re-analysis of an unchanged scene:

```
scene_analysis -> novelty_gate -> condition(novel == true) -> llm_call
```

Compares a CLIP embedding (`scene_analysis`'s `scene_embedding`) against the last one cached for
the scope (one slot per rule and camera by default) using `novelty_gate.min_distance` (0.06
default) unless overridden per-step. Fails open (`novel=true`) on a missing embedding, since the
gate must never suppress analysis because an upstream step broke; a cached embedding older than
the step's `ttl_minutes` also counts as novel. `scene_analysis` (tier 2) still runs every tick;
the gate only saves tier-3/4 calls further downstream.

**Watch-profile VLM rule.** `GateGraphRunner.execute_node`
(`backend/services/guided_task/gate_runner.py`) refuses to execute an `llm_call` node in the
`watch` gate profile when its resolved model has vision capability, unless the step's config
sets `watch_allowed: true`. A pruned node reports `pruned: true, reason:
"pruned_heavy_vision"`. This is a structural guarantee, not a convention: an accidental
Spark-melting watch tick cannot happen just because a node was never tagged.

**Tier-0 checklist, before adding a vision step to any rule:**
1. Does `PersonLocationService` already answer this ("where is she", "how long has she been in
   this room") via `room_segments`/`dwell_episodes` and the `presence_dwell` filter?
2. Does a prior step's `scene_detections` already answer a geometry question
   (`region_presence`, no model call) instead of re-cropping and re-detecting?
3. Would `novelty_gate` let the rule skip tier-2/3/4 work on an unchanged scene?
4. Is the vision step in a `watch` gate profile without `watch_allowed: true` intended? If so,
   it will be pruned; if the check genuinely needs vision on watch ticks, set the flag
   deliberately, don't work around the prune.

## 6. Hard sequencing gates (DL1, verbatim)

Do not relitigate; check the hardening ledger before crossing either line:

- **DL1(a):** No autonomous `guided_task_start` launch goes live until hardening
  M23+M24+M25+M27 have landed. Daily Living milestones must not edit
  `backend/services/guided_task/service.py` except DL-M05, serialized after hardening M25.
- **DL1(b):** Nothing in this program trusts floor-zone dwell from reCamera-fed rooms until
  hardening M28 closes G15 (fabricated floor points from a `.get(key, 0.0)` default instead of
  an explicit `is not None` check).

Both gates are re-verified against the live hardening-wave state at implementation time, not
assumed from this skill; grep `codebase-hardening-m*-*.md` for the current landed set before
building on either.

## 7. UI surfaces (M00 rule 22, five lines)

1. **Data access**: generated API client (`frontend/src/generated/`) behind a
   `{ state, actions }` composable; components never call `fetch`/axios ad hoc.
2. **Vocabularies are generated**: step types, filter types, channel types, and signal kinds
   ship in `frontend/src/generated/vocabularies.json`; presentational extras (icon, blurb) live
   only in `frontend/src/constants/signalKinds.js` (`getKindPresentation`), always with a
   generic fallback for an unknown kind.
3. **Charts**: shared `Cc*` components (`frontend/src/components/charts/`) with
   `useChartTheme`; never a hand-rolled ECharts option.
4. **Admin cards**: mirror `CcDailyLivingHealthCard.vue` (DL-M01) and
   `CcInferenceTelemetryCard.vue` (DL-M09) -- a `use<Name>.js` composable, `CcSectionCard`
   wrapper, `CcMetricTile` with a `status` prop for stale/error states.
5. **Modals** use `AppDialog`; **tests** are Vitest specs under `frontend/tests/` mirroring the
   `src/` path, not a build-only justification, for any component or composable with logic.

Full treatment: `/home/sriram/code/nanai/cognitive-companion/.claude/skills/front-end/SKILL.md`.
