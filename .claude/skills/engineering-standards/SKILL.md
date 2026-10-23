---
name: engineering-standards
description: "Use when changing Cognitive Companion backend or full-stack architecture, database code, tests, logging, naming, error handling, CTS consumers, or shared contracts."
---

# Engineering Standards

The rules for every backend and full-stack change in `cognitive-companion`. Each rule is one
line; the detail, examples, and rationale live in `reference/`. Frontend UI rules are the
`front-end` skill. Read a reference file when its trigger applies:

| Read | When |
| --- | --- |
| `reference/conventions.md` | Writing or reviewing any backend Python: naming, typing, errors, logging, time, venv, anti-patterns |
| `reference/layering-and-wiring.md` | Adding a module, service, router dependency, or MCP tool; abstracting; envelopes |
| `reference/testing.md` | Writing or changing tests |
| `reference/database.md` | Changing models, queries, invariants, or migrations |
| `reference/api-and-security.md` | Adding or changing a route, auth, or input validation |
| `reference/pipelines-and-plugins.md` | A step, channel, or filter; a new CTS signal kind; guided tasks; CC-local signals; inference load |
| `reference/cts-integration.md` | Code under `backend/services/cts/`, CTS routers, the CTS WebSocket, or location SSOT reads and writes |
| `reference/supply-chain.md` | Dependencies, lock files, toolchain versions |
| `reference/checklist.md` | Before declaring a change done |

## Gates and data safety (check these first)

1. `make check` while iterating; `make check-all` before declaring done. It runs every test
   under `backend/tests` plus the hook, markdown, docs-reference, and frontend gates; CI runs the
   same tree. Never deselect, skip, or delete a test to pass, and never lower the coverage floor.
2. Backend tests use the testcontainer fixtures (`db_session`, `db_factory`, `db_engine`): never
   a hand-built database, never the live database, never a mocked database.
3. Run Python only through `backend/.venv` or `uv run --frozen --project backend`; never system
   Python. Format only touched files. `backend/uv.lock` changes only when you re-lock on purpose.
4. A behavior change and a refactor never share a commit.
5. A gate that enumerates a collection (routes, plugins, files) carries a non-vacuity canary; a
   shrinking gate population is a defect (`reference/testing.md`).
6. Contract changes run `make contracts` and `npm run generate:api` and commit both artifacts;
   CI diff-gates them.

## Layering and wiring

7. Dependency direction: `core` imports nothing above it; then `models`, `schemas`,
   `integrations`, `services`, plugin packages, `routers`, `mcp`. Import-linter enforces it
   (`make import-lint`).
8. Services are constructed only in `backend/bootstrap/` phase modules and read from `app.state`;
   `backend/main.py` only builds the app. A new service: wire it in its phase, add it to
   `bootstrap/README.md` and the `test_bootstrap_wiring.py` pin, and add a typed `get_<name>`
   dependency (`reference/layering-and-wiring.md`).
9. Never read another service's underscore attributes; add a public method on the owner.
10. Routers are thin: validate, `require_permission`, call one service, return a schema. Never
    `getattr(request.app.state, "x", None)`; use a typed dependency or typed direct access.
11. Data a router exposes to the UI is exposed to MCP through the same service function; MCP
    tools hold no query logic. Every MCP tool declares its permission token
    (`_register(token=...)`); a state-changing tool gets its own token in `config/auth.yaml`.
12. Abstract at the third repetition, not before. A shared function, composable, or component
    exposes one canonical name per value; no convenience aliases.
13. Modules stay under about 500 lines; one router file per domain; one file per plugin.

## Errors, logging, typing

14. Raise `AppError` subclasses from services and routers; never catch them in a router.
15. A required upstream contract fails closed with a typed 502/503: never `.get("required", [])`
    or fabricated display data. An optional integration returns an explicit zero value and logs.
16. Broad `except Exception` only inside the BLE001 allowlist paths in `backend/pyproject.toml`;
    elsewhere a narrow exception or `# noqa: BLE001` with a reason.
17. Log with `backend.core.logging.get_logger(__name__)`, event name first, `key=value` fields;
    never `print`, `logging.getLogger`, structlog's `get_logger`, or f-strings in log calls. Never
    log secrets, keys, names, face crops, embeddings, or person-tied positions.
18. Every public signature is annotated; `backend.core` is strict mypy. `T | None`, built-in
    generics, `collections.abc`; no `Any` in `ServiceContainer` fields or service parameters.
19. Pydantic v2 at boundaries with `extra="forbid"` on Create/Update schemas; frozen dataclasses
    for results returned to callers.
20. Absolute imports with the full `backend.` path; `from __future__ import annotations` in every
    file.

## Time

21. Storage is timezone-aware UTC. Wall-clock rules use `app.timezone`; convert before comparing a
    time of day. Time-based logic takes an injectable clock; tests never sleep.

## Database

22. Schema changes are new Alembic revisions on top of head; the baseline is frozen; `downgrade()`
    exactly reverses `upgrade()`; never drop and recreate a database (`reference/database.md`).
23. An invariant is a constraint or (partial) unique index mapped to a domain error, never a
    read-then-write check.

## API and security

24. Every route has `response_model` (unless 204), a unique `(path, method)`, and
    `require_permission`. New routes use a `<resource>:<action>` token (decision D4), defined in
    `config/auth.yaml` and granted to a role; add a 403 test (`reference/api-and-security.md`).
25. Keys come from the `X-API-Key` header; only device endpoints (`get_auth_context_device`)
    accept a query or body key.
26. List endpoints that can grow paginate server-side and return `{items, total}`.

## Plugins, pipelines, domain recipes

27. A step, channel, or filter is one file in `builtin/` with complete metadata and a working
    zero-config default; every builtin filter has a through-the-engine test.
28. Pipelines are DAGs: fan-out and fan-in, in-degree-gated traversal; `wait` only on a linear
    segment; never `run_until_complete` inside the event loop (`reference/pipelines-and-plugins.md`).
29. Semantic-memory writes go only through `backend/services/scene_intel/`; countable daily-life
    facts are `ActivitySession` rows, never aggregated captions (the `daily-living` skill).
30. Local model calls go through `LLMAdmissionController` with a `caller` tag; watch-profile gate
    graphs are VLM-free unless a node is `watch_allowed`.
31. CC-local signals are emitted only by `signal_emit` through `SignalsService.emit()`, shadow-first.

## CTS integration

32. Person location has one read API and one write path: `PersonLocationService`. Never query its
    tables directly, never add a second store, writer, or step-level write flag
    (`reference/cts-integration.md`).
33. CTS tables are written only inside `services/cts/`; Redis Stream subscriptions only inside
    `CTSRuntime`; browser and MCP traffic to CTS services only through CC routers and typed clients.
34. Reuse the shared helpers (`services/cts/_time`, `routers/cts_deps.cts_enabled`,
    `services/aggregation`); never redefine them. WebSocket payloads are `model_dump(mode="json")`
    of a schema in `backend/schemas/<domain>_ws.py`, debounced per entity.
35. A new CTS signal kind starts in `cts-contracts`, then follows the CC touchpoint inventory in
    `reference/pipelines-and-plugins.md`; unknown kinds always render generically.

## Supply chain and comments

36. Lock files are committed and used frozen in CI; `npm ci`, never `npm install`, in CI; run
    `npm audit --audit-level=high` before a PR (`reference/supply-chain.md`).
37. Comments explain intent, never milestone ids or status (`.claude/rules/comments.md`). No
    em-dashes in markdown (`make check-md`).
