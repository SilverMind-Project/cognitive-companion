# Pipeline Step Data Plan

## Scope

This document analyzes how `pipeline_data` is created, mutated, templated, and persisted today, then lays out a sequential remediation plan.

Primary goals:

1. Eliminate race conditions and dirty-session behavior around `WorkflowExecution.pipeline_data_json`.
2. Make step outputs safe and explicit when a rule contains multiple steps of the same type.
3. Preserve existing rule behavior during migration, especially template access.
4. Keep the work executable by a less-capable agent with clear stop points and test gates.
5. Require the Python virtual environment at `backend/.venv/bin/` for all direct Python tooling invocations.
6. End with a clean `make check-all`.

---

## Current Lifecycle

### 1. Where `pipeline_data` is created

`backend/services/pipeline_executor.py:175-204`

- `PipelineExecutor.execute()` constructs the initial dict.
- The initial shape is:
  - `trigger`
  - `system`
  - `_pipeline`
  - `_step_timings`
  - `trigger_input` for webhook/Telegram-style payloads
- The dict is persisted as `WorkflowExecution.pipeline_data_json`.

### 2. Where it is updated during normal step execution

`backend/services/pipeline_executor.py:330-409`

- `_run_steps()` keeps a live reference to `execution.pipeline_data_json`.
- Each handler receives that live dict as `pipeline_data`.
- After the handler returns `StepResult`, the executor does:
  - `pipeline_data.update(result.data)`
  - if `step.label` exists, `pipeline_data[label_key] = dict(result.data)`
  - `pipeline_data["_step_timings"] = step_timings`
  - `db.commit()`

### 3. How downstream steps read it

`backend/core/template.py:49-118`

- `render_template()` and `resolve_path()` support:
  - dotted dict traversal
  - list indices
  - JSON-string auto-parse
  - attribute fallback
- This is the main mechanism used by prompts, notification templates, condition expressions, and several config fields.

### 4. Where it is updated outside the executor

`backend/services/interactive_response.py:200-312`

- `InteractiveResponseService` loads `WorkflowExecution` in a separate async path.
- It writes a response payload directly into `execution.pipeline_data_json`.
- It then commits and schedules an immediate resume.

### 5. Relevant ORM behavior

`backend/models/pipeline.py:84-113`

- `pipeline_data_json` uses `MutableDict.as_mutable(JSON)`.
- `WorkflowExecution` uses optimistic locking via `version`.
- The session factory uses `expire_on_commit=False`, which makes in-memory/detached object mistakes more dangerous.

---

## Findings

## Finding 1: top-level step output keys are collision-prone

Examples:

- `llm_call` defaults to `llm_response`
- `condition` writes `condition`
- `verification` writes `verification`
- `activity_detection` writes `detected_activities`
- `person_identification` writes `person_detections`, `room_transitions`, `annotated_image`
- `scene_analysis` writes fixed `scene_*` keys
- `semantic_memory_write` writes fixed `semantic_memory_*` keys
- `ha_action` writes `ha_action`

Impact:

- Two steps of the same type usually overwrite one another at the top level.
- A label-based namespace exists, but it is only a partial workaround.

## Finding 2: the label namespace is optional, unstable, and unvalidated

`backend/services/pipeline_executor.py:399-406`

- The alias key is derived by `step.label.strip().lower().replace(" ", "_")`.
- There is no uniqueness validation per rule.
- There is no reserved-key protection.
- Renaming the label changes the template reference surface.
- The alias is a shallow copy: `dict(result.data)`.

Impact:

- `label` can collide with:
  - another step label
  - a reserved key like `trigger`, `system`, `steps`, `error`
  - another output alias
- The current alias scheme is not a stable contract.

## Finding 3: `output_key` support is inconsistent

Supported today:

- `llm_call`
- `interactive_prompt`
- `activity_session_start`
- `activity_session_end`
- `daily_report`
- `object_trend_analysis`
- `semantic_memory_query`

Problems:

- `daily_report` uses `output_key` on the success path but not on empty/error paths.
- `object_trend_analysis` accepts `output_key` for the main map, but its empty helper is still hard-coded to `room_trends`.
- Many data-producing steps do not support `output_key` at all.

Impact:

- Rule authors cannot rely on a consistent naming model.
- Simply “using `output_key` everywhere” is not enough because many steps return multiple fields, not one field.

## Finding 4: the code claims optimistic retry coverage that is not actually wired in

`backend/services/pipeline_executor.py:646-673`

- `_update_pipeline_data_with_retry()` exists.
- It is referenced by docs/tests.
- It is not used by the executor’s real step-commit path.
- It is not used by `InteractiveResponseService`.

Impact:

- The code/documentation contract and the runtime behavior diverge.
- Real conflicts still surface in the normal execution path.

## Finding 5: `InteractiveResponseService` is a concurrent writer to the same row

`backend/services/interactive_response.py:67-109` and `:225-291`

- `record_response()` first commits `InteractiveResponse`.
- It then updates `WorkflowExecution.pipeline_data_json`.
- It then schedules immediate resume.

Impact:

- If the second commit conflicts, the response row can be persisted while:
  - the workflow row is not updated
  - resume is not scheduled
  - the workflow stays stuck
- This is the worst class of failure: “side table says the response exists, workflow never consumes it.”

## Finding 6: `interactive_prompt` mutates the execution object through the wrong session

`backend/steps/builtin/interactive_prompt.py:216-222`

- The step opens `db = services.db_factory()`.
- It mutates `execution.status` on an object owned by the outer executor session.
- It commits the new session, which does not own that object.

Impact:

- This is dirty-session behavior.
- The step appears to work only because the outer session still holds the same in-memory object and later commits it.
- The separate-session commit is effectively accidental and misleading.

## Finding 7: resume can be scheduled before the workflow is actually waiting

Current flow:

1. `interactive_prompt.execute()` sends the prompt before `_run_steps()` commits `status="waiting"`.
2. A fast human/client response can call `record_response()`.
3. `record_response()` schedules immediate resume.
4. `PipelineExecutor.resume()` only proceeds when `execution.status == "waiting"` (`backend/services/pipeline_executor.py:257-264`).

Impact:

- The resume job can fire too early.
- The job is consumed.
- The workflow later reaches `waiting`, but no wake-up job remains.
- This can strand the workflow indefinitely.

## Finding 8: timeout and generic wait resume are scheduled for the same moment

Current flow:

- `interactive_prompt` schedules `interactive_timeout_<execution>_<step>`
- `_run_steps()` also schedules the generic `resume_<execution>` at `result.wait_until`

Impact:

- Ordering is nondeterministic.
- Resume can happen before the timeout response is recorded.
- Downstream steps can see no response data at all.

## Finding 9: the exception path after commit failure is unsafe

`backend/services/pipeline_executor.py:347-531`

- If a `db.commit()` raises `StaleDataError`, the session enters a failed transaction state.
- The `except Exception` block does not first call `db.rollback()`.
- It immediately continues querying/mutating ORM objects.

Impact:

- The cleanup path itself can fail with `PendingRollbackError` or follow-on ORM failures.
- The workflow can end up in a partially updated state with a misleading terminal status.

## Finding 10: several configurable readers only support top-level keys

Examples:

- `llm_call.include_context` uses `pipeline_data.get(key)` (`backend/steps/builtin/llm_call.py:303-325`)
- `activity_detection.scene_description_key` uses `pipeline_data.get(scene_key)` (`backend/steps/builtin/activity_detection.py:195-196`)
- `semantic_memory_write` uses `pipeline_data.get(<configured_key>)` for all configurable source keys (`backend/steps/builtin/semantic_memory_write.py:151-197`)

Impact:

- Even if we add a canonical nested step namespace, these config fields will not be able to consume it until they switch to dotted-path resolution.

## Finding 11: the concurrency gate’s status vocabulary does not match interactive behavior

`backend/services/workflow.py:158-163`

- The concurrency gate counts only `running` and `waiting`.
- `interactive_prompt` invents `waiting_for_response`, but `WorkflowExecution.status` comments do not list it (`backend/models/pipeline.py:92-94`).

Impact:

- Status semantics are inconsistent.
- The system should converge on one persisted waiting state.

---

## Recommendation

Do **not** repurpose `output_key` to mean “step identity.”

Reason:

- `output_key` is the name of a payload field.
- Some steps produce multiple fields.
- Step identity and payload key are different concepts.

Recommended target model:

1. Use a canonical step namespace keyed by `step.id`.
2. Offer a friendly alias keyed by a validated label slug when unique.
3. Keep top-level aliases temporarily for backward compatibility.
4. Make the executor the only code path that merges data into `pipeline_data_json`.

### Canonical shape

```json
{
  "trigger": { "...": "..." },
  "system": { "...": "..." },
  "_pipeline": { "started_at": "...", "completed_at": null },
  "_step_timings": [],
  "steps": {
    "by_id": {
      "12": {
        "step_id": 12,
        "step_type": "llm_call",
        "label": "Vision Step",
        "label_slug": "vision_step",
        "outputs": {
          "vision_response": {
            "summary": "..."
          }
        }
      }
    },
    "by_label": {
      "vision_step": "12"
    },
    "sequence": ["12"]
  },
  "vision_response": {
    "summary": "..."
  }
}
```

Template examples:

- Canonical: `{{steps.by_id.12.outputs.vision_response.summary}}`
- Friendly alias: `{{steps.by_label.vision_step}}` to get the step id, then `{{steps.by_id.12.outputs.vision_response.summary}}`
- If a direct friendly namespace is desired, also allow:
  - `steps.by_name.vision_step.outputs.vision_response`

I recommend `steps.by_id` as the required canonical path and `steps.by_label` or `steps.by_name` as the optional ergonomic alias.

### Backward compatibility policy

For one migration window:

- Keep the current top-level aliases.
- Continue last-writer-wins behavior for those aliases to avoid breaking old rules.
- Add collision logging whenever two different step ids write the same top-level alias.
- Update docs/UI to mark top-level aliases as legacy.

This preserves old pipelines while finally giving a safe way to reference duplicate step types.

---

## Sequential Implementation Plan

## Step 1: introduce a single helper module for pipeline-data mutations

Create a new module:

- `backend/services/pipeline_data_manager.py`

Add these functions:

1. `build_initial_pipeline_data(trigger: TriggerContext, *, now_utc: datetime, now_local: datetime, timezone_name: str) -> dict[str, Any]`
2. `slugify_step_label(label: str | None) -> str | None`
3. `resolve_pipeline_value(data: Mapping[str, Any], path: str, default: Any = None) -> Any`
4. `apply_step_result(data: dict[str, Any], step: PipelineStep, result: StepResult) -> dict[str, Any]`
5. `apply_interactive_response(data: dict[str, Any], step: PipelineStep, response: InteractiveResponse) -> dict[str, Any]`
6. `copy_pipeline_snapshot(data: dict[str, Any]) -> dict[str, Any]`
7. `reserved_pipeline_keys() -> set[str]`

Implementation details:

- `resolve_pipeline_value()` must call `backend.core.template.resolve_path()`.
- `apply_step_result()` must:
  - deep-copy `result.data`
  - write the canonical `steps.by_id.<step_id>.outputs`
  - update `steps.sequence`
  - create the friendly alias only if the slug is unique and not reserved
  - project legacy top-level aliases
  - record collisions in a reserved block like `_alias_collisions`
- `copy_pipeline_snapshot()` must use `copy.deepcopy()`, not `dict(...)`.

Stop condition before Step 2:

- `backend/tests/services/test_pipeline_data_manager.py` exists and passes.

Required tests:

1. initial builder returns the same trigger/system keys as today
2. applying one step result writes `steps.by_id.<id>.outputs`
3. applying two same-type steps keeps both canonical entries
4. label slug alias is created when unique
5. reserved or duplicate label slug does not overwrite reserved keys
6. top-level alias collision is recorded when two steps write the same legacy key
7. snapshot helper deep-copies nested structures

## Step 2: switch configurable readers from `dict.get()` to dotted-path resolution

Files to update:

- `backend/steps/builtin/llm_call.py`
- `backend/steps/builtin/activity_detection.py`
- `backend/steps/builtin/semantic_memory_write.py`

Implementation details:

- Import `resolve_pipeline_value` from the new helper module.
- Replace direct `pipeline_data.get(configured_key)` reads with `resolve_pipeline_value(...)`.
- In `llm_call.include_context`, preserve the original text key in the rendered context block, but resolve it via dotted-path lookup.

Concrete rules:

- If the configured key/path does not resolve, preserve current fallback behavior.
- Do not change the auto-included top-level compatibility behavior yet.

Stop condition before Step 3:

- New dotted-path tests pass in the step-specific test files.

Required tests:

1. `llm_call.include_context` accepts `steps.by_id.<id>.outputs.<key>`
2. `activity_detection.scene_description_key` can read a namespaced path
3. `semantic_memory_write.description_key` and friends can read namespaced paths

## Step 3: centralize normal step-result writes in the executor

Files to update:

- `backend/services/pipeline_executor.py`

Implementation details:

1. Replace the inline mutation block:
   - `pipeline_data.update(result.data)`
   - label alias logic
2. Call `apply_step_result(...)` instead.
3. Replace every `event_log.pipeline_data_json = dict(pipeline_data)` with `copy_pipeline_snapshot(pipeline_data)`.
4. Add `db.rollback()` at the top of the `except Exception` block when the exception originated from commit/flush activity.

Important note:

- Do not remove legacy top-level aliases in this step.
- The canonical namespace is the new contract; the top-level aliases are compatibility only.

Additional hardening:

- If a top-level alias collision occurs, log:
  - execution id
  - old step id
  - new step id
  - key name

Stop condition before Step 4:

- `backend/tests/services/test_pipeline_executor.py` passes.

Required tests:

1. canonical step namespace is persisted after each step
2. two `llm_call` steps with identical `output_key` values both survive under `steps.by_id`
3. legacy top-level alias still exists for single-step pipelines
4. legacy collision warning fires when duplicate aliases are written
5. event-log snapshot includes canonical step namespace
6. exception cleanup works after simulated `StaleDataError` without `PendingRollbackError`

## Step 4: normalize the steps that already claim `output_key`

Files to update:

- `backend/steps/builtin/daily_report.py`
- `backend/steps/builtin/object_trend_analysis.py`
- any other step where success/empty/error paths disagree on `output_key`

Implementation details:

- `daily_report`
  - compute `output_key` once near the top
  - use it for success, empty, and error returns
- `object_trend_analysis`
  - make `_empty_output(output_key: str)` accept the configured key
  - keep companion summary flags inside the canonical step namespace
  - preserve top-level legacy companion keys for compatibility if needed

Do not do this in Step 4:

- Do not add `output_key` to every step type.
- Do not auto-merge multiple step outputs by type.

Reason:

- Universal multiplicity is solved by canonical step namespacing.
- Type-specific merge semantics should remain explicit.

Stop condition before Step 5:

- step-specific unit tests for `daily_report` and `object_trend_analysis` pass.

Required tests:

1. custom `output_key` works on success/empty/error paths for `daily_report`
2. custom `output_key` works on empty and normal paths for `object_trend_analysis`

## Step 5: remove `InteractiveResponseService` as a direct writer to `pipeline_data_json`

Files to update:

- `backend/services/interactive_response.py`

Implementation details:

1. Keep `InteractiveResponse` as the authoritative first-write-wins record.
2. Delete or stop using `_update_pipeline_data(...)`.
3. After persisting the response row:
   - cancel `interactive_timeout_<execution>_<step>` if the response was not generated by the timeout path
   - request resume via a new helper like `request_resume_when_waiting(...)`
4. `request_resume_when_waiting(...)` must:
   - open a fresh DB session each retry
   - read the execution status
   - if status is `waiting`, schedule immediate resume and return
   - if status is `running`, sleep briefly and retry with bounded exponential backoff
   - if status is terminal, stop
   - if retries are exhausted, log a hard error with execution id and step id

Suggested retry schedule:

- 0.05s
- 0.1s
- 0.2s
- 0.4s
- 0.8s

Stop condition before Step 6:

- `backend/tests/services/test_interactive_response.py` passes with the new ownership model.

Required tests:

1. response row still persists on happy path
2. duplicate response still returns `None`
3. service no longer mutates `pipeline_data_json` directly
4. early response while execution is still `running` retries until `waiting`
5. terminal execution does not schedule resume
6. timeout-generated response does not double-schedule resume

## Step 6: make interactive waits deterministic inside the executor

Files to update:

- `backend/steps/base.py`
- `backend/steps/builtin/interactive_prompt.py`
- `backend/services/pipeline_executor.py`

Implementation details:

1. Extend `StepResult` with a small wait discriminator, for example:
   - `wait_mode: str | None = None`
   - allowed values: `"time"` and `"interactive"`
2. `interactive_prompt` must:
   - stop opening a second DB session
   - stop mutating `execution.status`
   - continue sending the prompt
   - continue scheduling only the `interactive_timeout_<execution>_<step>` job
   - return `StepResult(wait_until=timeout_timestamp, wait_mode="interactive")`
3. `_run_steps()` must:
   - when `wait_mode == "interactive"`, set `execution.status = "waiting"` and `resume_at = wait_until`
   - commit that state
   - **not** schedule the generic `resume_<execution>` timer
4. `resume()` must:
   - lock the execution row
   - if `current_step` is `interactive_prompt`, load the corresponding `InteractiveResponse`
   - if no response exists yet, keep the execution in `waiting` and return
   - if a response exists, merge it into `pipeline_data` using `apply_interactive_response(...)`
   - then continue to the next step

Why this is the right split:

- the executor becomes the only merger of `pipeline_data_json`
- the timeout path and the early-response path both converge through the same response row
- the generic wait timer no longer races the timeout-response writer

Stop condition before Step 7:

- both the prompt-step tests and concurrency tests pass.

Required tests:

1. `interactive_prompt.execute()` no longer asserts/depends on `waiting_for_response`
2. response is merged into pipeline data during `resume()`, not during `record_response()`
3. early response before the waiting commit does not strand the workflow
4. timeout path resumes only after the synthetic response exists
5. downstream templating sees the merged response

## Step 7: clean up status semantics

Files to update:

- `backend/models/pipeline.py`
- `backend/services/workflow.py`
- tests that assert `waiting_for_response`

Implementation details:

- Persist only:
  - `running`
  - `waiting`
  - `completed`
  - `failed`
  - `cancelled`
- Remove `waiting_for_response` as a persisted state.
- If UI needs to know “interactive prompt pending,” derive it from:
  - `current_step.step_type == "interactive_prompt"`
  - `status == "waiting"`
  - response row absent
  - or a reserved pipeline marker like `_pending_interactive_step_id`

Stop condition before Step 8:

- no test asserts persisted `waiting_for_response`.

Required tests:

1. updated prompt-step tests
2. concurrency-gate behavior still counts `waiting`
3. interactive workflows no longer rely on undocumented status strings

## Step 8: validate friendly aliases and update the UI help surface

Files to update:

- `backend/routers/rules.py`
- `backend/schemas/rule.py` if schema-level validation is preferred
- `frontend/src/components/pipeline/StepConfigDialog.vue`

Implementation details:

1. Add validation for label-derived aliases:
   - slug must be non-empty after normalization
   - slug must not be a reserved key
   - slug must be unique within the rule if it will become a friendly alias
2. Update the help text and reference examples:
   - old: `{{step_label.key}}`
   - new canonical examples:
     - `{{steps.by_id.<step_id>.outputs.<key>}}`
     - `{{steps.by_name.<label_slug>.outputs.<key>}}` if you implement direct name lookup
3. Update sidebar/reference text so it no longer implies that outputs are grouped only by step type.
4. Update `Include Context Keys` help to explicitly allow dotted paths.

Stop condition before Step 9:

- UI copy and backend validation are aligned.

Required tests:

1. rule step update/create rejects duplicate or reserved friendly aliases
2. static UI snapshot/string assertions if frontend test coverage exists
3. manual UI smoke-check notes added to the PR description if no frontend test harness exists

## Step 9: add concurrency regression coverage

Files to update:

- `backend/tests/services/test_pipeline_concurrency.py`
- `backend/tests/services/test_pipeline_executor.py`
- `backend/tests/services/test_interactive_response.py`
- `backend/tests/steps/test_interactive_prompt.py`
- `backend/tests/core/test_template.py`

Add these regression cases:

1. two same-type steps writing the same legacy alias do not lose canonical data
2. response row committed while executor is mid-step does not fail the workflow
3. immediate response before the waiting commit still resumes correctly
4. timeout response and resume ordering is deterministic
5. canonical namespaced paths are template-readable
6. event-log snapshot contains final canonical step data

Do not proceed to final verification until all of these exist.

---

## Suggested File-Level Ownership

If multiple agents are implementing in parallel, split ownership like this:

1. Agent A
   - `backend/services/pipeline_data_manager.py`
   - `backend/tests/services/test_pipeline_data_manager.py`

2. Agent B
   - `backend/services/pipeline_executor.py`
   - `backend/tests/services/test_pipeline_executor.py`
   - `backend/tests/services/test_pipeline_concurrency.py`

3. Agent C
   - `backend/services/interactive_response.py`
   - `backend/steps/builtin/interactive_prompt.py`
   - `backend/tests/services/test_interactive_response.py`
   - `backend/tests/steps/test_interactive_prompt.py`

4. Agent D
   - `frontend/src/components/pipeline/StepConfigDialog.vue`
   - `backend/routers/rules.py`
   - `backend/schemas/rule.py`

If one agent is doing everything, follow the numbered steps in order and do not overlap Step 5 and Step 6.

---

## Explicit Non-Goals For This Pass

1. Do not replace all top-level aliases immediately.
2. Do not add type-specific automatic list aggregation unless a concrete rule requires it.
3. Do not add a new immutable `step_ref` database column in the same change unless label-based validation proves insufficient.
4. Do not broaden the status vocabulary further.

---

## Verification Commands

All direct Python-based tooling must use the repo virtualenv under `backend/.venv/bin/`.

Run these focused commands after the relevant implementation step:

```bash
backend/.venv/bin/python -m pytest backend/tests/core/test_template.py -q
backend/.venv/bin/python -m pytest backend/tests/services/test_pipeline_data_manager.py -q
backend/.venv/bin/python -m pytest backend/tests/services/test_pipeline_executor.py -q
backend/.venv/bin/python -m pytest backend/tests/services/test_pipeline_concurrency.py -q
backend/.venv/bin/python -m pytest backend/tests/services/test_interactive_response.py -q
backend/.venv/bin/python -m pytest backend/tests/steps/test_interactive_prompt.py -q
backend/.venv/bin/python -m ruff check backend
backend/.venv/bin/python -m mypy --config-file backend/pyproject.toml -p backend.core
```

Final gate before merge:

```bash
make check-all
```

If `make check-all` fails after the focused venv commands are green, fix the issues and rerun both the focused failing command and `make check-all` until both are clean.

---

## Bottom Line

The safest path is:

1. introduce a canonical per-step namespace
2. keep legacy aliases temporarily
3. stop out-of-band writers from mutating `pipeline_data_json`
4. merge interactive responses only inside the executor
5. add deterministic resume behavior for interactive waits

That gives us correctness first, backward compatibility second, and enough structure to support any number of same-type steps without ambiguous template references.
