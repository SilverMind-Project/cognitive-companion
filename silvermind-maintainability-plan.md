# SilverMind maintainability implementation plan

Status: ready for implementation. Written 2026-07-03 from a cross-repo review on branch `claude/silvermind-review-refactor-qk6bsf` (that branch already restored the quality gates in both repos, fixed a latent gallery-cache bug, restored `ReIDCandidateService`, and reconciled step-type docs; do not redo that work).

This plan is written for an implementing agent (for example Claude Sonnet) working one work package (WP) at a time. Each WP is independently shippable and states its own verification. Do not combine WPs in one PR unless the plan says so.

---

## How to use this plan

1. Pick the lowest-numbered WP whose dependencies are done.
2. Read the "Ground rules" section below in full before the first WP.
3. Follow the WP steps. Where a step says "investigate", the findings change the implementation; do not skip.
4. Run the WP's verification commands. All must pass before commit.
5. One WP per PR. Reference the WP number in the PR title, for example `WP3a: calibration validator parity fixtures`.

## Ground rules (read once, apply always)

**Repos and layout.** Work assumes sibling checkouts, as the Makefiles do:

```text
<root>/cognitive-companion       (CC)  - FastAPI BFF + Vue admin UI
<root>/continuous-tracking       (CTS) - tracking-orchestrator (Python) + rtsp-ingress (Go)
<root>/SilverMind-Project.github.io    - VitePress docs
```

**Environments.**

- CC backend: Python >= 3.14. Always `uv run --project backend ...`. Never system Python.
- CTS: Python >= 3.12, venv at `tracking-orchestrator/.venv`. Sync with `cd tracking-orchestrator && uv sync --frozen --extra dev`.
- Docs: Node 20+, `npm ci`.

**Gates. These are non-negotiable per repo:**

- CC: `make check` (ruff + mypy + pytest). ruff is pinned at 0.15.15 in `backend/uv.lock`; if the environment cannot install Python 3.14, at minimum run `uvx ruff@0.15.15 check backend` and `uvx ruff@0.15.15 format --check backend`, and say explicitly in the PR that mypy/pytest did not run and why.
- CTS: `make check`. For any change under `app/tracking/` or `app/storage/`, also run `make ci` (needs Docker) because it runs the C1/C2 WorldTracker and T5 repository-parity integration proofs.
- CTS Go: `make go-check` for anything under `rtsp-ingress/`.
- Docs: `npm test && npm run docs:build`.

**Safety guardrails, apply to every WP:**

- Never weaken an identity guardrail. The system invariant is: a stranger must never inherit a resident's identity, and the temporal prior alone must never trigger an identity commit. If a refactor touches `identity_resolver.py`, `commit_policy.py`, or the gallery trust scoring, the frame-replay proofs must pass unchanged.
- Preserve TD-009: `_crop_detection()` in `frame_pipeline.py` must always run before `ReidEmbedder.embed_batch()`.
- Do not connect `DepthEstimator` to `FrameProcessingPipeline` (TD-008).
- Behavior-preserving refactors only, unless the WP explicitly changes behavior. When in doubt, add a characterization test first.
- All refactors keep public import paths working (re-export from the old module) unless the WP says otherwise.
- Markdown in these repos avoids em dashes; use commas, colons, or two sentences.

**Decision points.** Three items need the project owner's decision and are marked `DECISION` where they appear: Python version convergence (WP9), the `reid_gallery.dimension` column semantics (WP6), and enabling branch protection (WP1, admin action).

---

## WP1: CI gates on every PR (do this first)

**Status: implemented** (branch `claude/silvermind-wp1` in all three repos). **The premise below was wrong and left here for history; read this box first.** All three repos already had a `.github/workflows/*.yml` that ran on `pull_request` (CC and CTS had a full `ci.yml`; the docs repo had only `deploy.yml`, which runs on push-to-main/`workflow_dispatch` and never runs tests). The actual problem was not "no CI exists" but **CI existed and had been failing on every single run for months** (CTS: 89 runs checked, every one red since at least mid-June; CC: every run red until the previous session's lint fixes landed), with no branch protection to make that failure block a merge. A red, unenforced check is worse than no check: it trains everyone to ignore it. Root causes found and fixed, one per job:

- CTS `python-test`: ran `psql -f tracking-orchestrator/migrations/0001_init.sql`, a file that has never existed (migrations are `.up.sql`/`.down.sql` pairs). The step, and the `services: postgres/redis` blocks feeding it, were also dead weight: integration-marked tests provision and migrate their own `timescale/timescaledb-ha:pg18` testcontainer via the session-scoped `_postgres_container` fixture in `tests/conftest.py`. Removed the dead blocks and the broken step.
- CTS `go-test`: ran `make check` inside `rtsp-ingress`, whose `check` target chains `lint vet test build`; `lint` invokes the bare `golangci-lint` binary, never installed in this job (unlike the separate `go-lint` job, which uses `golangci-lint-action`). Changed to `make vet test build`.
- CTS `proto-lint`: `buf generate`'s drift check shells out to `protoc-gen-go`, never installed, so it failed before ever comparing generated output. Added a `go install protoc-gen-go@v1.36.11` step (pinned to the `google.golang.org/protobuf` version in `rtsp-ingress/go.mod`) and put it on `$GITHUB_PATH`. This then correctly detected **real, 2-milestone-old drift**: `tracking.proto` was edited by Milestone 04 and Milestone 06 (both identity-governance work) without regenerating the committed Go bindings (Python bindings were regenerated correctly both times). Regenerated `tracking.pb.go`/`frame.pb.go` and committed them; verified inert in practice since `rtsp-ingress` only ever constructs `FrameReady`, never the affected message types.
- CC `Frontend gates`: `npm run build` failed on a real dependency incompatibility, not a CI config bug: dependabot bumped `@vue-flow/minimap` and `@vue-flow/controls` to versions that import `wheelDelta`/`isMacOs` from `@vue-flow/core`, but `@vue-flow/core` stayed at 1.41.7 (those symbols don't exist before 1.46.0, bisected locally, even though the peer range `^1.23.0` technically allowed it). Bumped `@vue-flow/core` to 1.46.0. This is arguably a hair outside "CI plumbing," but leaving it red would have meant WP1d's required check could never go green, so it was in scope.
- Docs: added `.github/workflows/check.yml` (`npm ci && npm test && npm run docs:build` on `pull_request` and push-to-main), since nothing ran tests on PRs before.

**Required check names for WP1d, once these branches merge:**

- `continuous-tracking`: `python-lint`, `python-test`, `go-lint`, `go-test`, `proto-lint`, `security-scan` (all from `.github/workflows/ci.yml`, job `CI`).
- `cognitive-companion`: `Backend gates`, `Frontend gates` (from `.github/workflows/ci.yml`, job `CI`).
- `SilverMind-Project.github.io`: `docs` (from the new `.github/workflows/check.yml`, job `Check`).

None of this was verified by an actual GitHub Actions run in the implementing session (no PR was opened, per that session's scope instructions; also no Docker available in that sandbox to exercise the CTS testcontainer path end-to-end). Verification was `make check`/`make check-all` locally (CTS, 1501 tests), direct `go build`/`go vet`/`go test -race` against system Go (CTS toolchain download was network-blocked in that sandbox), `npm run build`/`npm test` (CC frontend, 686 tests), and `npm test && npm run docs:build` (docs). Confirm green on the actual PRs before proceeding to WP1d.

The rest of this section is the original plan text, kept for context; treat the box above as authoritative over it.

### WP1a: continuous-tracking workflow (original draft; workflow already existed, see status box above)

Create `.github/workflows/check.yml` in `continuous-tracking`:

```yaml
name: check
on:
  pull_request:
  push:
    branches: [main]
jobs:
  python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: cd tracking-orchestrator && uv sync --frozen --extra dev
      - run: make lint
      - run: make format-check
      - run: make mypy
      - run: make import-lint
      - run: make test
  go:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version-file: rtsp-ingress/go.mod
      - run: make go-check
```

Adjust target names to the real Makefile: run `grep -E '^[a-z-]+:' Makefile` first and use the targets that `make check` and `make go-check` chain to (if `make check` works directly on the runner, prefer the single `make check` call). Note `triton-shared` and `cts-contracts` are git dependencies in `pyproject.toml`; the runner needs access to those GitHub repos (they are in the same org, so default `GITHUB_TOKEN` checkout of public repos or an org-scoped token works; verify by running `uv sync --frozen` in the workflow).

Optional second job, nightly only (schedule trigger), running `make ci` for the Docker-backed integration proofs.

### WP1b: cognitive-companion workflow (original draft; workflow already existed, see status box above)

Same shape, single Python job:

```yaml
      - uses: astral-sh/setup-uv@v5
      - run: uv python install 3.14
      - run: uv sync --project backend --extra dev
      - run: make check
```

Plus a frontend job if `frontend/package.json` has a `lint`/`test` script (check first; add `npm ci && npm run lint && npm run test -- --run` accordingly, skipping scripts that do not exist).

### WP1c: docs workflow (implemented; this one really was missing)

In `SilverMind-Project.github.io`: `npm ci && npm test && npm run docs:build`. Landed as `.github/workflows/check.yml`.

### WP1d: branch protection (`DECISION`, admin action)

The owner must enable required status checks on `main` in all three repos. An agent cannot do this: it requires repo admin rights, and the agent tooling has no branch-protection endpoint. The exact check names to require are listed in the status box at the top of WP1.

Exact owner steps, once per repo, AFTER the WP1 workflows are merged to main and at least one PR has run them (GitHub's check picker only offers names it has already seen; WP2's PR is a good trigger):

1. Repo on GitHub -> Settings -> Rules -> Rulesets -> New ruleset -> New branch ruleset.
2. Name: `protect-main`. Enforcement status: Active.
3. Target branches -> Add target -> Include default branch.
4. Enable rules:
   - Require a pull request before merging, with Required approvals: 0 (solo maintainer; 1 would block merging your own agent PRs).
   - Require status checks to pass -> Add checks -> select the exact job names from the WP1 workflows (copy them verbatim from the checks tab of any PR that ran them).
   - Optionally: Require branches to be up to date before merging.
   - Block force pushes stays on (ruleset default).
5. Bypass list: leave empty, so the rules apply to admins too. Add yourself temporarily for emergencies instead of weakening the ruleset.
6. Create.

Verify per repo: a direct `git push origin main` is rejected, and a PR with a deliberate lint error has its merge button blocked until checks pass.

**Verification:** open a draft PR with an intentional lint error in a scratch file; the workflow must fail. Remove the scratch file; the workflow must pass. Delete the draft PR.

---

## WP2: consistency tests so docs cannot drift from code

**Status: implemented** (branch `claude/silvermind-wp2` in cognitive-companion and in the docs repo; no CTS component). Both sub-parts matched the plan's design closely; two things worth knowing before reading further:

1. **WP2a needed a prerequisite fix.** `backend/channels/builtin/webhook.py` was missing `@ChannelRegistry.register` (every other builtin channel has it), so `webhook` had never actually registered despite being documented as one of the 7 channels. Fixed on its own commit (`claude/silvermind-fix-webhook-registration`, cherry-picked into WP2's branch) since WP2a's test would otherwise fail immediately against a real, separate bug rather than a docs problem.
2. **A large false alarm along the way, worth recording so it isn't repeated.** While verifying WP2a, a full-repo `ast.parse` scan (run with plain `python3`, which resolves to Python 3.11 in that sandbox) found 24 files using `except A, B:` instead of `except (A, B):`. That syntax is invalid in every Python 3 version through at least 3.13 and was fixed in all 24 files, then reverted in full after discovering the fix was wrong: this project's `target-version = "py314"` and real CI (which runs on actual Python 3.14) both confirm Python 3.14 accepts bare comma-separated exception types, and `ruff format --target-version py314` actively strips the parenthesized form back out. The original code was correct for this project's target interpreter. Lesson for future WPs: **this codebase targets Python 3.14, a version whose grammar is not yet reflected in general model/tooling knowledge; verify against this project's own `ruff`/`target-version` config (or real CI) before concluding any construct is "obviously" invalid syntax, especially anything touching `except`, `type` statements, or PEP 695 generics (`def foo[T](...)`).** The webhook fix (item 1) is unrelated to this and stands on its own.

**Why:** three hand-maintained step-type lists disagreed with the code (22 vs 23 vs 24) and the docs site documented two removed step types. These are mechanical drifts; make a machine catch them.

**Depends on:** nothing (WP1 makes it enforced).

### WP2a: CC registry-vs-docs test

Add `backend/tests/docs/test_doc_registry_parity.py`:

1. Import the step registry the same way existing tests do (find the pattern with `grep -rn "StepRegistry" backend/tests | head`); collect the set of registered `type_name`s. Do the same for channels and filters if registries exist (check `backend/channels/__init__.py`, `backend/filters/__init__.py`).
2. Parse `CLAUDE.md` and `AGENTS.md`: extract every backtick-quoted token from the line starting with `Current built-in step types:` (CLAUDE.md) and from the list under `### Step types` (AGENTS.md).
3. Assert set equality both ways, with a helpful diff message.
4. Also assert the counts stated in prose (`There are N registered built-in step types`) match `len(registry)` by regexing `(\d+) registered built-in step types`.

Guardrail: the test must read the markdown files relative to the repo root (`Path(__file__).parents[3]`), not the CWD.

### WP2b: docs-site manifest test

The docs repo has vitest configured and zero test files. Add `docs/.manifest.json` (checked in) describing the numbers the docs claim:

```json
{
  "step_types": 24,
  "channels": 7,
  "filters": 13,
  "trigger_types": 8
}
```

Add `tests/consistency.test.ts` that:

1. Globs `docs/**/*.md`.
2. Regex-scans for `(\d+)\s+(pipeline\s+)?step types`, `(\d+) notification channels`, `(\d+) context filters`, `(\d+) trigger types` and asserts every match equals the manifest value.
3. Asserts the removed identifiers `recamera_media_poll` and `cts_window_poll` appear nowhere except in sentences containing "removed".

When a count legitimately changes, the committer updates the manifest in the same PR; that is the point.

**Verification:** run the new tests; then temporarily edit one count in a doc and confirm the test fails; revert. Both WP2a and WP2b were verified exactly this way (WP2a via a standalone regex check plus a static cross-reference of every `type_name=`/`channel_name=`/`filter_type=` declaration against both markdown files, since this sandbox cannot run the real Python 3.14 test suite directly; WP2b by running the real vitest suite, corrupting `docs/.manifest.json`, confirming failure, and reverting).

---

## WP3: unify the calibration validator (highest correctness value)

**Why:** `cognitive-companion/backend/services/cts/calibration_validator.py` and `continuous-tracking/tracking-orchestrator/app/calibration/validator.py` are hand-maintained copies whose own docstring says "Both must produce identical results". They have already drifted: CC returns `HomographyValidation(ok, severity, issues, metrics)`, CTS returns `ValidationResult` with an extra derived `code` and `residual_m`, and issue strings differ ("camera→room" vs "camera->room"). If they diverge on a real matrix, CC will accept a calibration that CTS refuses, and the person dot silently degrades.

**Depends on:** WP1 (so parity tests are enforced). Split into two stages because stage 2 needs the `cts-contracts` repo, which may not be available to every session.

### WP3a: parity fixtures and tests (both repos, no shared package yet)

1. Create a fixture file `calibration_validator_cases.json` with 10-15 cases: identity-like homography (valid), near-singular matrix, negative determinant, huge scale, residual lists that cross the warning and error thresholds, a polygon-containment failure, and edge cases (empty residuals, missing polygon). For each case record the inputs only.
2. Commit the identical file to both repos: CC `backend/tests/services/cts/fixtures/` and CTS `tracking-orchestrator/tests/unit/fixtures/`.
3. In each repo add a test that runs its local validator over all cases and writes/asserts against a golden output file capturing the fields both sides share: `severity` and the normalized issue list (normalize `→` to `->` before comparing; that unicode drift is cosmetic).
4. Generate the goldens from the CTS side first (it is the defensive consumer), then run the CC test. Where CC disagrees, STOP and record the disagreement in the PR description; reconciling the logic is part of this WP only when the difference is an obvious drift (string wording, threshold constant that one side updated). If the difference is behavioral and ambiguous, flag it as a `DECISION` for the owner.

### WP3b: extract to `cts-contracts` (requires access to that repo)

1. In `cts-contracts`, add `cts_contracts/calibration.py` containing the pure validation core: a function returning a neutral dataclass `CalibrationCheck(severity: str, issues: list[str], metrics: dict[str, float])`. Copy from the CTS implementation reconciled in WP3a. The package already ships `py.typed`.
2. In CTS, reduce `app/calibration/validator.py` to an adapter: call the shared core, then derive `code`/`residual_m` and build `ValidationResult` as today. Public API unchanged.
3. In CC, reduce `backend/services/cts/calibration_validator.py` to an adapter building `HomographyValidation`. Public API unchanged.
4. Keep the WP3a parity tests; point them at the adapters. They now guard the adapters, not two implementations.
5. Bump the `cts-contracts` git pin in both `pyproject.toml`s in the same coordinated pair of PRs.

**Verification:** both repos' full gates; the parity tests pass with identical goldens; `grep -rn "def validate_homography" | wc -l` finds one implementation across the org (plus adapters).

---

## WP4: move the duplicated PH admin wire schemas into cts-contracts

**Why:** `cognitive-companion/backend/schemas/cts_ph.py` and `continuous-tracking/tracking-orchestrator/app/routers/ph_schemas.py` share an 86-line exact clone (starting near CC line 132 / CTS line 208): `CorrectIdentityRequest`, `MergeRequest`, `BatchMergeRequest`, revision-feed responses. A field added on one side and not the other becomes a silent contract break between the BFF and the orchestrator.

**Depends on:** WP3b (establishes the cts-contracts release flow). Requires `cts-contracts` repo access.

1. Diff the two files first (`diff <(sed -n ...) <(sed -n ...)` or open both); enumerate exactly which classes are byte-identical. Only those move. Side-specific response envelopes stay put.
2. Add `cts_contracts/ph_admin.py` with the shared Pydantic models. Pydantic v2 is already a dependency of both repos; `cts-contracts` must declare `pydantic>=2` too.
3. In both repos, replace the moved classes with `from cts_contracts.ph_admin import CorrectIdentityRequest, MergeRequest, BatchMergeRequest, ...` re-exported from the original modules so routers and tests keep their import paths.
4. Run both repos' router tests. In CC also run the MCP/BFF parity tests (`backend/tests/integrations/test_mcp_bff_parity.py`).

**Verification:** full gates both repos; `grep -rn "class MergeRequest" cognitive-companion continuous-tracking` shows zero local definitions.

---

## WP5: TD-007, put CC's face-based location writes behind a CTS-aware boundary

**Why:** when `cts.enabled=true`, CC's own face-based location conclusions duplicate CTS's world tracker: two subsystems can disagree about where the senior is. The CTS tech-debt table and `docs/identity-path-validation-2026-06.md` already validated that CC's conclusions are redundant in that mode. This WP changes behavior deliberately, behind config.

**Depends on:** WP1. Read `continuous-tracking/docs/identity-path-validation-2026-06.md` in full before starting.

1. **Investigate (do not skip):** map every write path for CC-side location conclusions. Start points: `backend/services/person_tracking.py` (818 lines), `backend/services/person_location/`, and `grep -rn "PersonLocationHistory(" backend --include="*.py"`. Classify each write site as (a) CTS-sourced (the Redis subscriber path: keep), (b) face/reCamera-sourced location conclusion (gate), or (c) raw sighting or activity capture (keep, other consumers own it).
2. Find how the code reads the CTS-enabled flag (`grep -rn "cts.enabled\|cts_enabled" backend --include="*.py"`), and reuse that accessor.
3. Introduce one guard function, for example `location_authority_is_cts() -> bool` in the person-location service module, and gate every class-(b) write with it. Log one structured line at startup stating which authority owns location writes.
4. Do not delete the gated code; this is a boundary, not a removal. Removal is a later milestone once consumers migrate.
5. Tests: for the gated path, add tests asserting (i) with `cts.enabled=false` the face path still writes (existing behavior), (ii) with `cts.enabled=true` the face path does not write a location conclusion but raw sightings are still captured.
6. Update `docs/systems-architecture.md` (CC) with a short "location authority" paragraph, and update the TD-007 row in CTS `CLAUDE.md` to point at the new guard.

**Verification:** CC full gate; the new tests; manual grep proving no class-(b) write site is unguarded.

---

## WP6: bring ReIDCandidateService into the storage layer

**Why:** the restored `app/tracking/identity/candidate_service.py` (CTS) executes raw SQL through `gallery_repo._pool`, bypassing the Protocol + InMemory + Postgres triplet that the rest of the repo enforces. Its tests mock a pool by hand instead of injecting an `InMemory*`. It is groundwork for the remaining identity-governance milestones, so fix its foundation before wiring it in.

**Depends on:** nothing. Touches `app/storage/`, so `make ci` (Docker) is required.

1. **`DECISION` first:** `create_candidate` stores `dimension = dimensions[0] * dimensions[1]` (crop pixel area, 32768 for 128x256). If the column means embedding dimensionality (SOLIDER-REID emits 768), the correct value is `len(embedding)`. Check consumers: `grep -rn "dimension" app/ --include="*.py" | grep -v dimensions`. Present both readings to the owner in the PR if still ambiguous; implement whichever is confirmed.
2. Add protocol methods to the gallery repository protocol in `app/storage/base.py` (find the class with `grep -n "class GalleryRepository" app/storage/base.py`):
   - `insert_candidate(entry: CandidateInsert) -> None` where `CandidateInsert` is a frozen dataclass in `app/domain/` carrying every column the current INSERT sets.
   - `transition_review_state(candidate_id, new_state, actor, reason, note) -> ReviewTransition` returning previous state, new audit version, and the `crop_key` when the transition is a rejection.
   - `relabel(candidate_id, new_identity_id, actor, reason) -> None`.
   - `undo_last_review(candidate_id, actor, reason) -> str` returning the restored state.
3. Implement in `PostgresGalleryRepository` (`app/storage/postgres/gallery_repo.py`) by moving the SQL verbatim from the service, including the optimistic `audit_version` check and the review-event inserts, inside one transaction per operation. In `undo_last_review`, order the event lookup by `audit_version DESC` instead of `event_time DESC` (event_time can tie within a transaction; audit_version cannot).
4. Implement the `InMemory*` counterpart next to the protocol with plain dicts, mirroring state, audit versions, and events.
5. Rewrite `ReIDCandidateService` to depend only on the protocol: validation, hashing, MinIO puts, and key construction stay; SQL goes. Constructor takes the typed protocol, not `Any`.
6. Rewrite `tests/unit/test_candidate_service.py` to inject the `InMemory*` implementation. Delete the hand-rolled pool mock. Keep the three behavioral tests (eligibility, rejection deletes crop and nulls embedding, approve/relabel/undo) and add one for the audit-version conflict path (transition with a stale version must not apply).
7. Add a T5-style parity test in `tests/integration/` exercising InMemory vs Postgres for the four new methods, following the pattern in `tests/contracts/test_ph_repository_property.py`.

**Verification:** `make check` and `make ci`. `grep -n "_pool" app/tracking/` returns nothing.

---

## WP7: decompose the five oversized files

**Why:** these files are where the next bug hides and where reviews go shallow. Each split below is behavior-preserving: move code, re-export, no logic edits. Do them as five separate PRs, any order.

For every split: after moving, the original module keeps `from .newmodule import X, Y  # re-export` so existing imports and monkeypatch targets keep working, then run the full gate. Check for string-based references before moving anything: `grep -rn "modulename" --include="*.py"` including tests and alembic.

### WP7a: CTS `app/domain/__init__.py` (1328 lines)

Split into `domain/tracking.py` (Detection, WorldObservation, PersonHypothesis, snapshots), `domain/identity.py` (gallery, review, provenance, correction types), `domain/signals.py` (dementia signal types). `__init__.py` becomes pure re-exports preserving `from app.domain import X` everywhere. mypy strict runs on domain; keep every annotation identical.

### WP7b: CTS `app/storage/base.py` (1053 lines)

Move each Protocol + its InMemory twin into `app/storage/contracts/<resource>.py` (ph.py, gallery.py, corrections.py, decisions.py, signals.py, ...). `base.py` re-exports everything. While there, extract the 33-line identity-correction clone (near old lines 477 and 715: single-PH correct vs batch correct in the InMemory PH repo) into one private helper `_apply_identity_correction(ph, new_identity_id, now)` used by both methods.

### WP7c: CTS `app/tracking/identity_resolver.py` (~2000 lines)

The target package `app/tracking/identity/` already exists (posterior.py, evidence.py, policy.py, commit_policy.py). Move the pure scoring functions first: `_score_gallery_hits`, `_logistic`, recency/trust weighting into `identity/posterior.py` as module-level functions taking explicit config parameters. The resolver keeps orchestration. Frame-replay proofs and `make ci` must pass; do not renumber or reorder any probability computation.

### WP7d: CC `services/guided_task/service.py` (2089 lines)

Investigate the seams first: `grep -n "def \|class " backend/services/guided_task/service.py`. Expected split: state-machine transitions vs side effects (notification sends, camera-selection cascade, TTS calls) vs query/read helpers. Move side-effect helpers to `services/guided_task/effects.py`, keep the state machine in service.py. The guided-task tests (`tests/services/guided_task/`, 6+ files) are the safety net; they must pass unmodified.

### WP7e: CC `mcp/server.py` (1801 lines)

Split tool registrations by domain into `mcp/tools_tracking.py`, `mcp/tools_rules.py`, `mcp/tools_knowledge.py`, each exposing `register(mcp, services)`. `server.py` builds the server and calls the three registrars. The MCP/BFF parity tests are the safety net.

**Verification per split:** full repo gate; for 7a-7c also `make ci`; `git diff --stat` shows moves plus re-exports and no logic hunks (spot-check with `git diff -w`).

---

## WP8: fold the small clones (one PR, or fold opportunistically)

Each item is small; batch them per repo.

**CTS:**

1. `app/inference/detector.py`: `_detect_model_batch` (line ~67) and `_detect_model_batch_at` (line ~129) share their preprocessing/meta loop. Make `_detect_model_batch` delegate: `return await self._detect_model_batch_at(images, self._config_threshold)` or extract the shared body into `_run_detector(images, threshold)`. TD-009 ordering unaffected (this is detection, not ReID), but re-read the callers anyway.
2. `app/pipeline/frame_pipeline.py`: the single-frame path (~line 840) and batch path (~line 1070) duplicate the semaphore + camera-lock + process + ack + latency block. Extract `async def _process_and_ack(self, frame) -> None` used by both; the locks stay acquired at the caller level exactly as today (the batch path holds one lock across frames deliberately; preserve that).
3. `app/routers/reid_review.py` re-declares the `ReviewCandidate` field list (~36 lines, near line 82) as a response model mirroring the domain dataclass (near `domain/__init__.py:796`). Do not merge them (domain vs wire is a legitimate boundary); add a parity test asserting `set(model.model_fields) == {f.name for f in dataclasses.fields(ReviewCandidate)}` minus an explicit, commented allowlist of wire-only fields.

**CC backend:**

4. `steps/builtin/activity_session_start.py` / `activity_session_end.py` share a 28-line `execute` preamble (config load + trigger_vars construction). Extract into `steps/builtin/_activity_session_common.py` (module-private helper), call from both.

**CC frontend** (run `cd frontend && npm run lint && npm run test -- --run` if those scripts exist; otherwise verify with `npm run build`):

5. `views/admin/InfoCardsView.vue`, `QuizzesView.vue`, `KnowledgeDocumentsView.vue`, `KnowledgeDocumentEditView.vue` share ~25-line list-fetch/dialog blocks. Extract a `composables/useAdminResource.ts` (list + loading + error + refresh) and adopt it in the three list views only; leave edit views alone in this pass.
6. `views/activity/ProcessActivityView.vue` and `views/admin/ExecutionsView.vue` share a 46-line template block; extract a shared component under `components/` named for what the block renders (inspect first).

**Tests (both repos):** move duplicated fixture blocks flagged by the review into package-level `conftest.py` files: CC `tests/services/guided_task/` (the 44-50 line shared setup between test_nag_suppression / test_watch_auto_advance / test_watch_tick / test_gate_presets / test_gate_runner) and `tests/services/presence/` (provider fixtures). Fixture names must not change assertion behavior; run each test file individually after the move.

**Verification:** full gates; rerun the duplicate scan and confirm the folded clones are gone:

```bash
npx -y jscpd --min-tokens 100 --silent --ignore "**/node_modules/**,**/.venv/**,**/proto/**,**/*_pb2*,**/alembic/**,**/migrations/**,**/dist/**" cognitive-companion/backend cognitive-companion/frontend/src continuous-tracking/tracking-orchestrator/app
```

---

## WP9: platform convergence and stragglers

1. **`triton-shared` py.typed** (needs that repo): add an empty `triton_shared/py.typed`, include it in package data, tag a release. Then in CTS remove `"triton_shared.*"` from the mypy overrides in `tracking-orchestrator/pyproject.toml` and bump the git pin. Verify `make mypy` stays clean.
2. **Python version (`DECISION`):** CC requires >=3.14, CTS >=3.12. Recommend documenting this as intentional in both CLAUDE.md files, or converging on one floor. Note for CI and sandboxes: 3.14 standalone builds must be downloadable; WP1b proves it on GitHub runners.
3. **Docs generation for step lists:** after WP2a exists, optionally add `backend/scripts/generate_step_docs.py` that prints the canonical markdown lists (steps, channels, filters) from the registries, so updating CLAUDE.md/AGENTS.md is copy-paste instead of hand-editing. Keep WP2a as the enforcement either way.
4. **Logging convention note:** CTS mandates structlog; CC uses a stdlib `BoundLogger` shim. Add one line to each CLAUDE.md stating the repo's convention explicitly so agents stop importing the wrong one. No code change.
5. **Proto staleness check:** in CTS CI (WP1a), after setup add a step that regenerates Python bindings (`make proto-py` requires protoc >= 25; if runner setup is heavy, instead hash-compare `proto/` against a committed manifest) and fails if `git diff --exit-code tracking-orchestrator/app/proto/` is dirty. This catches "edited .proto, forgot codegen" and the CC-side copy going stale.

---

## Suggested execution order

```text
WP1 (CI)  ->  WP2 (consistency tests)  ->  everything else in any order
WP3a -> WP3b -> WP4        (contract track; 3b/4 need cts-contracts access)
WP5                        (location authority; needs owner awareness, changes behavior)
WP6                        (candidate service storage refactor; needs Docker for make ci)
WP7a..WP7e                 (five independent decomposition PRs)
WP8                        (clone folds, batched per repo)
WP9                        (stragglers; item 2 needs owner DECISION)
```

Rationale: WP1 and WP2 stop the bleeding and make every later WP verifiable. WP3 has the highest correctness value for tracking quality at home. WP5 removes the last double-source-of-truth about the senior's location. The rest is compounding maintainability.

## Reporting

Each WP's PR description must include: what changed, the exact verification commands run and their results, any `DECISION` items encountered with a recommendation, and any deviation from this plan with the reason. If a WP turns out to be wrong about the code (line numbers drift, a seam does not exist), adapt and note it; do not force the plan against reality.
