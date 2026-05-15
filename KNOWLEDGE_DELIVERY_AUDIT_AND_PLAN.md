# Knowledge, Info Card, and Quiz: Audit and Phased Fix Plan

Audience: an implementing agent. Read this top to bottom once before touching code.
Every bug cites `file:line`. Every phase ends with a concrete verification step.

Conventions used here:
- "PWA" means the companion UI served by `frontend/src/views/CompanionView.vue`.
- "voice" means the Gemini Live session reached over the `/ws/audio` WebSocket.
- "eink" means a physical e-ink display that polls the backend for a rendered PNG.
- File references look like `backend/routers/quizzes.py:330`.

---

## Part A. How the system works today (walkthrough)

### A.1 Knowledge document creation

1. Caregiver uploads title, source text, tags, and optional images:
   `POST /api/v1/knowledge/documents` in `backend/routers/knowledge.py:46`.
2. The router calls `KnowledgeIngestionService.create_document`
   (`backend/services/knowledge/ingestion_service.py`). Images go to MinIO; a
   background job chunks and embeds the text into `knowledge_document_chunks`
   (pgvector), retried by `knowledge_reembed_retry` (`backend/main.py:522`).
3. Status lifecycle: `uploaded -> chunked -> approved -> archived`
   (`backend/models/knowledge.py:74`).
4. Embedded chunks power senior-initiated RAG through
   `KnowledgeQueryService` and the `query_knowledge_base` MCP tool
   (`backend/mcp/server.py:1087`).

### A.2 Info card creation

1. `POST /api/v1/info-cards` (`backend/routers/info_cards.py:30`) creates an
   `InfoCard` in `draft`. `layout_id` is validated against the layout registry
   (`config/knowledge_layouts.yaml`, loaded by
   `backend/services/knowledge/layout_registry.py`).
2. LLM paraphrase assist: `POST /api/v1/info-cards/suggest`
   (`backend/routers/info_cards.py:227`) calls
   `ContentGenerationService.suggest_paraphrase`
   (`backend/services/knowledge/content_generation.py:63`).
3. Caregiver binds images to layout slots:
   `PUT /api/v1/info-cards/{id}/slots/{slot_index}`
   (`backend/routers/info_cards.py:262`). The image pipeline renders per-surface
   variants (`pwa`, `eink`) defined by the layout.
4. `POST /api/v1/info-cards/{id}/approve` (`backend/routers/info_cards.py:149`)
   validates `min_images` and flips status to `approved`. Only `approved` cards
   can be delivered.

### A.3 Quiz creation

1. `POST /api/v1/quizzes` (`backend/routers/quizzes.py:32`) creates a `Quiz` in
   `draft` with a `question_layout_id`.
2. LLM quiz assist: `POST /api/v1/quizzes/suggest`
   (`backend/routers/quizzes.py:330`) calls
   `ContentGenerationService.suggest_quiz`.
3. Questions are created, edited, reordered, and image-bound through
   `/api/v1/quizzes/{id}/questions*` (`backend/routers/quizzes.py:231` onward).
   Each `QuizQuestion` is `multiple_choice` or `open_ended`
   (`backend/models/knowledge.py:251`).
4. `POST /api/v1/quizzes/{id}/approve` (`backend/routers/quizzes.py:150`) flips
   status to `approved`.

### A.4 Info card delivery

1. A rule pipeline runs the `info_card` step
   (`backend/steps/builtin/info_card.py`). Config: `info_card_id`, `channels`
   (`pwa`, `eink`), dismiss/expiry timers, `voice_instruction`.
2. The step loads the card, then calls
   `KnowledgeDeliveryService.deliver_info_card`
   (`backend/services/knowledge/delivery_service.py:59`), which:
   - writes an `InfoCardDelivery` audit row;
   - broadcasts a `info_card` WebSocket message to all PWA clients;
   - renders to eink if `eink` is in channels and an eink renderer is present;
   - queues a Gemini Live voice prompt through
     `ConnectionManager.send_backend_task`.
3. The PWA shows `frontend/src/components/companion/InfoCardDialog.vue`, which
   counts down and sends `info_card_dismiss` back over the WebSocket.

### A.5 Quiz delivery

1. The `quiz_start` step (`backend/steps/builtin/quiz_start.py`) loads the quiz,
   dedupes, then calls `KnowledgeDeliveryService.start_quiz_session`
   (`backend/services/knowledge/delivery_service.py:169`), which:
   - creates a `QuizSession` row;
   - broadcasts `quiz_start` plus the first `quiz_question` WebSocket message;
   - queues a Gemini Live intro+question voice prompt.
2. The PWA shows `frontend/src/components/companion/QuizDialog.vue`
   (intro -> question -> complete screens). Choice buttons send `quiz_answer`
   over the WebSocket.
3. The voice path is meant to record answers through the MCP tools
   `submit_quiz_answer` and `complete_quiz_session` (`backend/mcp/server.py:1137`
   and `:1178`), which Gemini Live can call as functions
   (`backend/mcp/gemini_adapter.py`).

---

## Part B. Architectural decision: who owns quiz state

The current code half-implements two competing models (PWA-driven button clicks
versus Gemini-driven tool calls) and neither works end to end. The plan below
commits to one model. Every fix traces back to it. Do not hybridize.

**Decision: the backend `KnowledgeDeliveryService` is the single source of truth
for quiz session state. Both the PWA and the voice path are thin clients of it.**

- The PWA records answers by sending `quiz_answer` over the WebSocket; the
  backend handler calls `submit_quiz_answer`.
- The voice path records answers when Gemini calls the `submit_quiz_answer` MCP
  tool. Gemini learns the current question by calling a new MCP tool
  `get_current_quiz_question` (added in Phase 3). Gemini is never pre-loaded with
  the full question list.
- After every recorded answer, the backend decides "advance" or "complete" and
  pushes the next `quiz_question` (or `quiz_complete`) WebSocket message itself.
- Question order and the per-session subset are persisted on the `QuizSession`
  row so both channels and the backend agree on "current question".

---

## Part C. Bug catalog

Severity: CRITICAL blocks the feature; HIGH breaks a stated requirement; MEDIUM
is correctness or standards debt.

### CRITICAL

**C1. Pipeline steps never use the fully wired delivery service.**
`backend/main.py:207` builds `knowledge_delivery` with MinIO, eink renderer,
voice config, and content generation, and stores it at
`app.state.knowledge_delivery`. But:
- `backend/steps/builtin/info_card.py:98` checks
  `hasattr(services, "_delivery_service")`. `ServiceContainer`
  (`backend/steps/base.py:69`) has no such field, so this is always false. The
  step then builds a bare `KnowledgeDeliveryService(db_factory, ws_manager)`
  with no MinIO, eink, voice, or content generation.
- `backend/steps/builtin/quiz_start.py:128` unconditionally builds the same bare
  service.
Consequences: eink info card delivery never fires (`self._eink` is `None`); PWA
info card and quiz images get empty URLs (`self._minio` is `None`); open-ended
grading is disabled (`self._content_gen` is `None`); YAML voice defaults are
never applied (`self._voice` is `None`).

**C2. PWA quiz answering is completely dead.**
`QuizDialog.vue:299` sends `{type: "quiz_answer", ...}` over `/ws/audio`. The
WebSocket reader `backend/websocket/audio_handler.py:120` only handles
`end_of_turn`, `text`, and `interactive_response`. `quiz_answer` is silently
dropped. `submit_quiz_answer` is never called from the PWA path, and no
`quiz_answer_recorded` message is ever sent back.

**C3. Info card view and dismiss events are dropped.**
`InfoCardDialog.vue:115` and `:137` send `{type: "info_card_dismiss", ...}`.
Same drop as C2. `KnowledgeDeliveryService.record_info_card_event`
(`backend/services/knowledge/delivery_service.py:260`) is never called, so
`viewed_at` and `dismissed_at` stay null forever.

**C4. Multi-question quiz flow is broken on every channel.**
`start_quiz_session` (`delivery_service.py:226`) sends only the first
`quiz_question`. Nothing ever sends question 2..N. `submit_quiz_answer` computes
an `advance` flag (`delivery_service.py:375`) but never calls `_send_question_ws`
for the next question. The MCP `submit_quiz_answer` broadcasts
`quiz_answer_recorded` (`backend/mcp/server.py:1166`) but also never sends the
next question. `QuizDialog.handleQuizAnswerRecorded` then calls
`loadNextQuestion()` against an empty queue, so the quiz stalls after Q1.

**C5. Per-session question order and subset are not persisted.**
`start_quiz_session` (`delivery_service.py:205`) sorts, optionally shuffles, and
truncates questions to `max_questions` in memory, sends Q[0], and discards the
list. `submit_quiz_answer` (`delivery_service.py:307`) then looks up the question
by `ord` against the full quiz table, so randomization breaks the mapping and
`max_questions < total` breaks the `advance`/complete math at
`delivery_service.py:372`.

**C6. The pipeline never resumes when a quiz completes; voice cannot drive a
multi-question quiz.**
`quiz_start` returns `wait_until=timeout_at` (`quiz_start.py:172`), so the
pipeline stays paused until the full timeout even when the quiz finishes early.
`complete_quiz_session` (`delivery_service.py:390`) does not resume the
execution. On the voice side, Gemini is only told question 1 in the intro prompt
(`delivery_service.py:234`) and has no tool to fetch later questions, so it
cannot conduct the quiz past Q1.

### HIGH

**H1. `KnowledgeAnswerWidget` is dead UI.**
`CompanionView.vue` never registers `wsClient.on("onKnowledgeAnswer", ...)` and
`getWidgetProps` (`CompanionView.vue:118`) returns `{}` for `knowledge-answer`.
`KnowledgeAnswerWidget.vue`'s `show()` ignores its arguments. The backend does
broadcast `knowledge_answer` (`backend/mcp/server.py:1120`), but nothing renders
it. Note: that broadcast sends `query_id: -1`; confirm the payload shape before
relying on it.

**H2. Info card voice is delivered unconditionally.**
`deliver_info_card` gates voice on `if voice_inst or card.title:`
(`delivery_service.py:143`). `card.title` is always truthy, so a Gemini voice
prompt is always queued even when the caregiver picked only `pwa` or `eink`. The
`info_card` step `channels` enum is `["pwa", "eink"]` only
(`info_card.py:41`); there is no way to opt out of voice.

**H3. Eink info card rendering is text-only, no layout, no images, no template.**
`deliver_info_card` calls `self._eink.render(text=f"{title}\\n\\n{body}",
template="info_card", ...)` (`delivery_service.py:134`). There is no `info_card`
eink template (only `backend/assets/images/templates/default.png` exists), so
`_resolve_template` (`backend/integrations/eink_renderer.py:348`) falls back to
the default and dumps raw text. The `eink` image variants that layouts like
`single_hero` and `side_by_side` declare (`config/knowledge_layouts.yaml:36`,
`:59`) are never rendered to the display.

**H4. `InfoCardDialog.vue` ignores `layout_id`.**
The `info_card` WebSocket payload includes `layout_id`
(`delivery_service.py:122`), but `InfoCardDialog.vue:35` renders every image in
one vertical flex column regardless. `side_by_side` and `gallery_grid_2x2` look
identical to `single_hero`. The file also hardcodes `rgba(255,255,255,...)`
colors (`InfoCardDialog.vue:177`, `:183`), which violates the front-end skill
(use `var(--cc-*)` tokens).

**H5. `send_backend_task` metadata is plumbed but discarded.**
`ConnectionManager.send_backend_task` accepts `metadata`
(`backend/websocket/connection_manager.py:128`) and the delivery service passes
`delivery_type`, `session_id`, etc. But `audio_handler.py:222` unpacks it as
`_metadata` and ignores it. The voice turn therefore cannot be correlated to a
quiz session, which is why the voice path cannot record answers without the new
MCP tool from Phase 3.

### MEDIUM

**M1. `QuizSession.senior_id` is never set; `per_senior_dedupe_hours` lies.**
`start_quiz_session` (`delivery_service.py:183`) never sets `senior_id`. The
dedupe query in `quiz_start.py:102` filters only by `quiz_id` and `completed`
status, not by senior. The config key name promises per-senior behavior the code
does not implement.

**M2. Docstrings placed after a statement in `content_generation.py`.**
`regenerate_question` (`content_generation.py:137`) and `_parse_single_question`
(`content_generation.py:233`) put `_validate_question_type(...)` before the
triple-quoted string, turning the "docstring" into a dead expression statement.

**M3. Info card `preview` and `rerender` endpoints are stubs.**
`backend/routers/info_cards.py:248` and `:407` return
`{"status": "not_implemented"}`. `api.js` exposes `previewInfoCard` and
`rerenderInfoCard`, so the admin UI likely has dead buttons.

**M4. Quiz `preview` endpoint is a stub.**
`backend/routers/quizzes.py:218` returns `not_implemented`; `api.js` exposes
`previewQuiz`.

**M5. `list_quiz_sessions` hardcodes `response_count: 0`.**
`backend/routers/knowledge_interactions.py:101` still has the Phase 3 TODO.

**M6. `quiz_start._handle_timeout` captures a service object as an APScheduler
job arg.**
`quiz_start.py:155` passes the `delivery_svc` instance into `add_job(args=...)`.
APScheduler currently uses the default in-memory jobstore, so this works today,
but it is fragile and reaches into a private method
(`delivery_svc._update_session_status`). Prefer an `app.state` lookup inside the
job function.

**M7. Both new steps are missing `output_schema`.**
`info_card.py:28` and `quiz_start.py:30` return `StepMetadata` with no
`output_schema`. CLAUDE.md requires it for data-emitting steps and
`backend/tests/steps/test_registry_contract.py` enforces it.

**M8. `VoiceInstructionConfig.compose()` is dead code.**
`backend/services/knowledge/voice_instructions.py:53` defines a base+override
composition rule that nothing calls. `deliver_info_card` and `start_quiz_session`
do their own ad-hoc resolution, and `audio_handler` sets the system instruction
to the raw string.

**M9. `submit_quiz_answer` advancement is not idempotent.**
`delivery_service.py:367` sets `session.current_question_ord = question_ord + 1`
unconditionally, even when the response row already existed. A double-send of the
same answer double-advances the session.

---

## Part D. Phased implementation plan

Each phase is independently shippable and ends with a verification step. Do the
phases in order; later phases assume earlier fixes.

Run `make check` after every phase. Run `make check-all` for any phase that
touches `backend/services/` or schema (Phases 0, 1, 3, 4, 6). Run
`cd frontend && npm run build` for any phase touching `frontend/` (Phases 1, 2,
5). Frontend step/widget changes also need `npm run test`.

### Phase 0. Wire the real delivery service into pipeline steps (fixes C1)

This unblocks every later phase. No behavior is correct until steps use the
fully wired service.

1. Add a field to `ServiceContainer` in `backend/steps/base.py:69`:
   ```python
   knowledge_delivery: Any = None  # KnowledgeDeliveryService (knowledge feature)
   ```
2. In `backend/services/pipeline_executor.py`, add `knowledge_delivery=None` to
   the constructor signature (near line 110) and pass it into the
   `ServiceContainer(...)` call (near line 126).
3. In `backend/main.py`, find where `PipelineExecutor` is constructed and pass
   `knowledge_delivery=knowledge_delivery` (the object built at
   `backend/main.py:207`).
4. Rewrite `backend/steps/builtin/info_card.py:96-116` to use
   `services.knowledge_delivery` directly. If it is `None`, return
   `StepResult(success=False, data={"error": "knowledge delivery service not available"})`.
   Delete the bare-construction fallback and the `hasattr` check.
5. Do the same in `backend/steps/builtin/quiz_start.py:118-133`: use
   `services.knowledge_delivery`; delete the local import and bare construction.
6. Update or add unit tests:
   `backend/tests/steps/test_info_card.py` and
   `backend/tests/steps/test_quiz_start.py`. Cover success, missing service
   (`knowledge_delivery=None`), and a not-approved resource. Build the
   `ServiceContainer` with only the fields the step uses.

Verification: run `make check-all`. Then in a dev environment trigger a rule
with an `info_card` step targeting an approved card with one image on the
`single_hero` layout; confirm the `info_card` WebSocket payload now contains a
non-empty `image_slots[].url`.

### Phase 1. PWA quiz answering and multi-question flow (fixes C2, C4, C5, M9)

This phase has a schema change. It goes through Alembic, not `create_all`.

**1a. Schema: persist per-session question order.**
1. Add a column to `QuizSession` in `backend/models/knowledge.py:283`:
   ```python
   question_order: Mapped[list[int]] = mapped_column(
       JSONB, nullable=False, default=list, server_default="[]"
   )
   ```
   This stores the ordered list of `quiz_questions.id` for this session (after
   shuffle and `max_questions` truncation).
2. Generate the migration: `make migration`. Review the autogenerated file in
   `backend/alembic/versions/` before committing; confirm it only adds the one
   column. Apply with `make migrate`.

**1b. Backend: build, persist, and drive the question list.**
1. In `start_quiz_session` (`backend/services/knowledge/delivery_service.py:169`):
   - After sorting/shuffling/truncating `questions` (current lines 205-209),
     write `session.question_order = [q.id for q in questions]` and commit it on
     the same session row you already create.
   - Keep sending `quiz_start` and the first `quiz_question`.
2. Add a private helper `_send_question_by_index(session, index)` that resolves
   `session.question_order[index]`, loads that `QuizQuestion`, and calls the
   existing `_send_question_ws` with `ord_num=index` and
   `total=len(session.question_order)`. Use the list index as the canonical
   "question_ord" everywhere downstream, not `QuizQuestion.ord`.
3. Rewrite `submit_quiz_answer` (`delivery_service.py:287`):
   - Resolve the question via `session.question_order[question_ord]` instead of
     the `QuizQuestion.ord` lookup at `delivery_service.py:307`.
   - Make advancement idempotent: only advance and only send the next question
     when the response row was newly inserted (guard the block at
     `delivery_service.py:367`).
   - Compute `advance = (question_ord + 1) < len(session.question_order)` using
     the persisted list, not `len(all_questions)`.
   - When `advance` is true, call `_send_question_by_index(session,
     question_ord + 1)`.
   - When `advance` is false, call `complete_quiz_session(session_id)`.
   - Broadcast `quiz_answer_recorded` from here (the service), so both the PWA
     handler and the MCP tool get identical behavior. Remove the duplicate
     broadcast from `backend/mcp/server.py:1166` so it is not sent twice.
4. Confirm `complete_quiz_session` (`delivery_service.py:390`) still broadcasts
   `quiz_complete`. (Pipeline resume on completion is Phase 3; leave the timeout
   path alone for now.)

**1c. Backend: handle the `quiz_answer` WebSocket message.**
1. In `backend/websocket/audio_handler.py:120` (`_receive_from_client`), add an
   `elif msg_type == "quiz_answer":` branch that calls a new
   `await self._handle_quiz_answer(data)`.
2. Implement `_handle_quiz_answer`: read `app.state.knowledge_delivery` via
   `self.ws.app.state` (mirror the `_handle_interactive_response` pattern at
   `audio_handler.py:492`). Call `submit_quiz_answer` with `session_id`,
   `question_ord`, `choice_id` or `open_ended_text`, `channel="pwa"`. The service
   does the broadcasts; the handler only validates and forwards. Log on missing
   service.

**1d. Frontend: nothing structural required.**
`QuizDialog.vue` already pushes incoming `quiz_question` messages into
`questionQueue` and advances on `quiz_answer_recorded`. Once the backend sends
Q2..N, the existing logic works. Verify `handleQuizQuestion`
(`QuizDialog.vue:207`) loads a queued question when the screen is on `question`
and `advanceTimer` is null. Add a test in
`frontend/src/components/companion/__tests__/` driving start -> Q1 -> answer ->
Q2 -> ... -> complete.

Verification: approve a quiz with 3 questions, `max_questions: 3`. Trigger the
`quiz_start` step. In the PWA, answer Q1; confirm Q2 appears, then Q3, then the
complete screen with the correct tally. In the database confirm
`quiz_sessions.question_order` is a non-null 3-element array and
`quiz_responses` has 3 rows. Repeat with `randomize_order: true` and confirm the
answers map to the right questions.

### Phase 2. Info card events and voice gating (fixes C3, H2)

**2a. Handle `info_card_dismiss`.**
1. In `audio_handler.py:120`, add `elif msg_type == "info_card_dismiss":` calling
   a new `_handle_info_card_event(data)`.
2. The payload carries `action`, which is `"viewed"` (sent on display,
   `InfoCardDialog.vue:137`) or `"dismissed"` / `"timeout"` (sent on close,
   `InfoCardDialog.vue:115`). Discriminate on `action`. Map `"viewed"` to
   `viewed_at`, and `"dismissed"`/`"timeout"` to `dismissed_at`. Call
   `app.state.knowledge_delivery.record_info_card_event(delivery_id, action)`.
3. Extend `record_info_card_event` (`delivery_service.py:260`) so it accepts
   `"timeout"` and treats it like `"dismissed"` with `dismissed_by="senior"`.

**2b. Make voice an explicit channel.**
1. In `backend/steps/builtin/info_card.py:41`, change the `channels` enum to
   `["pwa", "eink", "voice"]`.
2. In `deliver_info_card` (`delivery_service.py:59`), add a parameter
   `speak: bool` (default derived by the step from `"voice" in channels`).
   Replace the unconditional gate at `delivery_service.py:143` with `if speak:`.
3. In `info_card.py`, pass `speak=("voice" in channels)` to `deliver_info_card`.
4. Keep backward compatibility: if a saved config has no `voice` in channels,
   voice is now off. Note this in the commit message; it is an intentional
   behavior change.

Verification: deliver an info card with `channels: ["pwa"]` and confirm no
Gemini prompt is queued (check logs for absence of `info_card_voice_delivery`).
Deliver with `channels: ["pwa", "voice"]` and confirm it is queued. Open the PWA
dialog and confirm `info_card_deliveries.viewed_at` is set; click "Got it" and
confirm `dismissed_at` is set.

### Phase 3. Voice and Gemini Live quiz wiring (fixes C6, H5; M8)

**3a. New MCP tool: `get_current_quiz_question`.**
1. In `backend/mcp/server.py`, register a tool near the other quiz tools
   (`server.py:1137`):
   ```python
   @_register
   async def get_current_quiz_question(session_id: int) -> dict:
       """Return the question the senior should answer next in this quiz
       session: its ord, text, type, and choices. Call this before asking
       the senior a question."""
   ```
   Implement it on `KnowledgeDeliveryService` as
   `get_current_question(session_id)`: read `QuizSession.current_question_ord`,
   resolve `question_order[current_question_ord]`, return ord/text/type/choices,
   or `{"done": True}` if past the end.
2. Add `"get_current_quiz_question"` to both `mcp.tools` and `mcp.gemini_tools`
   in `config/settings.yaml:174` and `:188`. MCP tools are gated by these
   allowlists, not by `auth.yaml`.

**3b. Carry `session_id` into the voice turn (use the metadata, fix H5).**
1. In `audio_handler.py:222`, stop discarding `_metadata`. When a prompt arrives
   with `metadata` containing `delivery_type == "quiz_start"` and a
   `session_id`, append a short system note to the turn so Gemini knows which
   session to act on, for example: prepend to the prompt text
   `f"[quiz session {session_id}] "` or include it in the composed voice
   instruction. Keep it minimal; the senior never sees orchestrator prompt text
   (`audio_handler.py:357`).
2. Update the `quiz_default` instruction in `config/knowledge_voice.yaml` to tell
   Gemini to call `get_current_quiz_question` then `submit_quiz_answer` for each
   question, and `complete_quiz_session` at the end, using the session id from
   the prompt.

**3c. Resume the pipeline when the quiz completes.**
1. Give `KnowledgeDeliveryService` access to the pipeline executor (constructor
   param `pipeline_executor: Any = None`, wired in `backend/main.py:207`).
2. In `complete_quiz_session` (`delivery_service.py:390`), after marking the
   session completed, if the session has an `execution_id` and a pipeline
   executor is present, call `pipeline_executor.resume(execution_id, db)` inside
   a try/except that logs and swallows. This ends the pipeline wait early
   instead of blocking until `wait_until`.
3. Fix `quiz_start._handle_timeout` (`quiz_start.py:175`): change the scheduled
   job to a module-level function that looks up
   `app.state.knowledge_delivery` rather than capturing the service instance as
   a job arg (addresses M6). The timeout should mark the session `timed_out`
   and also resume the execution.

**3d. Use `VoiceInstructionConfig.compose()` (fix M8).**
Route both `deliver_info_card` and `start_quiz_session` voice-instruction
resolution through `VoiceInstructionConfig.compose(...)` so the documented
"step override > resource override > yaml default" order is real. Delete the
ad-hoc resolution at `delivery_service.py:91` and `:200`. If `compose()` truly
has no caller after this, that is fine; it now has two.

Verification: with `GEMINI_API_KEY` set, deliver a 2-question quiz with
`channels` including voice. Speak answers. Confirm Gemini calls
`get_current_quiz_question` and `submit_quiz_answer` (check
`gemini_tool_call_executing` logs), that `quiz_responses` rows appear with
`channel="voice"`, that the PWA mirrors the progress via `quiz_answer_recorded`,
and that the owning pipeline execution resumes immediately on
`complete_quiz_session` rather than at the timeout.

### Phase 4. Eink info card template and rendering (fixes H3)

**4a. Create an eink `info_card` template.**
1. Add `backend/assets/images/templates/info_card.png` sized to the display
   (`image.display_width` x `image.display_height`, default 800x480 from
   `config/settings.yaml`).
2. Create an `ImageTemplate` DB row named `info_card` with regions for `title`,
   `body`, and one `image` region. Follow the existing `alert` template's region
   structure; the admin region editor is
   `frontend/src/components/eink/RegionEditor.vue`. Seed it via a small Alembic
   data migration or the existing template admin flow, whichever the repo
   already uses for the `alert` template.

**4b. Render layout-aware content to eink.**
1. In `deliver_info_card` (`delivery_service.py:131`), when `eink` is in
   channels: resolve the card's eink image variant (the `eink` key of
   `slot.variants`, analogous to the `pwa` block at `delivery_service.py:98`),
   fetch the bytes from MinIO, and pass them to the renderer.
2. Extend `EInkRenderer.render` (`backend/integrations/eink_renderer.py:58`) or
   add a sibling method that accepts an optional image (PIL `Image` or bytes) to
   composite into the template's `image` region. `_render_image` already accepts
   a preloaded `Image` for the template (`eink_renderer.py:215`); add the same
   capability for a content image placed into a named region.
3. Pass `template="info_card"` and, if the step config specifies them,
   `template_id` and `sensor_ids`. Add `eink_targets` and `eink_template_id` to
   the `info_card` step `config_schema` (`info_card.py:35`) so a caregiver can
   target specific displays, mirroring the `eink` channel
   (`backend/channels/builtin/eink.py:25`).

Verification: deliver a `single_hero` info card with `channels: ["eink"]` to a
known eink sensor id. Confirm the active image for that sensor renders the title,
body, and the dithered hero image in their regions, and that an unrelated
`text_only` card renders title and body with no image artifacts.

### Phase 5. Frontend polish (fixes H1, H4)

**5a. Layout-aware `InfoCardDialog.vue`.**
1. Read `data.layout_id` in `handleInfoCard` (`InfoCardDialog.vue:126`) and store
   it in a `layoutId` ref.
2. Render conditionally:
   - `single_hero`: one full-width image above the body.
   - `side_by_side`: image and body in a two-column row (stack on narrow
     screens).
   - `gallery_grid_2x2`: a 2x2 CSS grid of up to 4 images.
   - `text_only`: no image block.
   Keep it simple; a `v-row`/`v-col` per layout is enough.
3. Replace the hardcoded `rgba(255, 255, 255, ...)` values at
   `InfoCardDialog.vue:177` and `:183` with `var(--cc-*)` tokens (see
   `frontend/src/styles/theme.css` and the front-end skill). `QuizDialog.vue`
   already does this correctly; match it.

**5b. Make `KnowledgeAnswerWidget` live.**
1. In `CompanionView.vue`, add reactive state `knowledgeAnswerData` and register
   `wsClient.on("onKnowledgeAnswer", (data) => { ... })` in `onMounted`
   (mirror the `onInteractivePrompt` wiring at `CompanionView.vue:350`).
2. Add a `case "knowledge-answer":` to `getWidgetProps` (`CompanionView.vue:118`)
   returning `queryText`, `answerText`, `sourceDocumentIds`.
3. Fix `KnowledgeAnswerWidget.vue`'s `show()` so it actually sets the refs from
   its arguments, or drive it purely by props (the `watch` on `queryText` already
   exists). Pick one mechanism; do not keep both half-wired.
4. First confirm the backend `knowledge_answer` payload shape
   (`backend/mcp/server.py:1120`); the `query_id: -1` placeholder suggests the
   payload may need tightening. Align the widget to whatever the backend actually
   sends.

Verification: ask the companion a question answerable from an approved knowledge
document via voice. Confirm `KnowledgeAnswerWidget` appears with the query and
answer. Deliver each info card layout and confirm the PWA dialog renders the
distinct layout. Run `npm run build` and `npm run test`.

### Phase 6. Consistency and standards cleanup (fixes M1-M8 remainder)

1. **M1.** Either populate `QuizSession.senior_id` in `start_quiz_session` (from
   trigger context if available) and make the dedupe query in `quiz_start.py:102`
   filter by it, or rename the config key to `dedupe_hours` and update its
   description. Do not leave the name lying.
2. **M2.** Move the docstrings above the statements in
   `content_generation.py:137` and `:233`.
3. **M3, M4.** Either implement the `preview` and `rerender` endpoints
   (`info_cards.py:248`, `:407`, `quizzes.py:218`) or remove the dead routes and
   the `previewInfoCard`/`rerenderInfoCard`/`previewQuiz` methods from
   `frontend/src/services/api.js` and any admin buttons that call them.
4. **M5.** Populate `response_count` in `list_quiz_sessions`
   (`knowledge_interactions.py:101`) with a real count query.
5. **M7.** Add `output_schema` to `StepMetadata` for both `info_card`
   (`info_card.py:28`) and `quiz_start` (`quiz_start.py:30`). The schemas must
   describe the `data` dict each `execute` returns. Confirm
   `backend/tests/steps/test_registry_contract.py` passes.

Verification: `make check-all` passes, including
`test_registry_contract.py`. `cd frontend && npm run build` passes. No
`not_implemented` strings remain in `info_cards.py` or `quizzes.py` unless the
corresponding frontend calls were removed.

---

## Part E. Final validation checklist

Run after Phase 6. This is the end-to-end acceptance gate.

Backend:
- [ ] `make check-all` passes.
- [ ] `make typecheck` passes on every changed module.
- [ ] New/changed step tests cover success, missing-service, and an edge case.
- [ ] The Alembic migration from Phase 1 is reviewed and applies cleanly with
      `make migrate`, and downgrades cleanly.
- [ ] No new endpoint was added without an `auth.yaml` entry (the existing
      `info-cards*`, `quizzes*`, `knowledge*` wildcards in `config/auth.yaml`
      cover sub-routes; new MCP tools are gated by `config/settings.yaml`
      `mcp.tools` / `mcp.gemini_tools` instead).

Frontend:
- [ ] `cd frontend && npm run build` passes.
- [ ] `npm run test` passes, including a new quiz multi-question test.
- [ ] No hardcoded hex or `rgba()` colors remain in `InfoCardDialog.vue`.

Info card end to end:
- [ ] `text_only`, `single_hero`, `side_by_side`, `gallery_grid_2x2` each render
      distinctly in the PWA dialog with non-empty image URLs.
- [ ] `single_hero` and `side_by_side` render title, body, and a dithered image
      to an eink display via the `info_card` template.
- [ ] `viewed_at` and `dismissed_at` populate on `info_card_deliveries`.
- [ ] Voice is queued only when `voice` is in the step's channels.

Quiz end to end:
- [ ] A 3-question quiz advances Q1 -> Q2 -> Q3 -> complete in the PWA via
      button clicks, with a correct final tally.
- [ ] `randomize_order: true` and `max_questions < total` both produce a correct
      `question_order` array and correctly mapped `quiz_responses`.
- [ ] With Gemini Live active, spoken answers record via the MCP tools, the PWA
      mirrors progress, and `complete_quiz_session` resumes the owning pipeline
      execution immediately rather than at the timeout.
- [ ] A timed-out session is marked `timed_out` and its pipeline resumes.

Knowledge answer:
- [ ] A voice question answerable from an approved document shows in
      `KnowledgeAnswerWidget` and logs a `senior_knowledge_queries` row.
