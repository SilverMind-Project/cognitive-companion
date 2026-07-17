"""Response-model coverage gate (M17).

Generated TypeScript types are only as good as the schema the backend advertises: a JSON route
without `response_model` becomes `unknown` in `frontend/src/generated/api-types.d.ts`, which
silently pushes the contract back to hand-written guesswork -- the exact failure `contracts.js`
was covering for.

Three buckets, so the gate is green today and ratchets:

* **204 No Content** -- exempt automatically. There is no body to describe, so a response model
  would be noise (31 routes, mostly DELETEs). Not a list: derived from the status code.
* **ALLOWLISTED** -- genuinely schemaless: binary bodies and Prometheus text. Each needs a
  justification. Adding a line here is a contract decision.
* **DEFERRED_TO_17B** -- the real backlog, enumerated so it can only shrink. M17 lands as two
  PRs (17a: foundation + pilot domains; 17b: the remaining domain migration); this is 17b's
  worklist. `test_deferred_list_has_no_stale_entries` deletes the excuse once a route is fixed.

The three properties below are what actually hold the line:
  1. no *new* undeclared route appears (the gap cannot grow);
  2. the deferred list has no stale entries (it cannot rot);
  3. the pilot domains are fully declared (17a's own bar).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.routing import APIRoute

# ─── Genuinely schemaless ─────────────────────────────────────────────────
#
# Every entry needs a justification: these are contract decisions, not debt.

ALLOWLISTED: dict[str, str] = {
    "GET /api/v1/cts/cameras/{camera_id}/snapshot": "binary snapshot bytes (Response), not JSON",
    "GET /api/v1/cts/frames/{key:path}": "binary frame bytes (Response), not JSON",
    "GET /api/v1/image/active": "binary image bytes (Response), not JSON",
    "GET /api/v1/image/templates/{template_id}/preview": "binary image bytes (Response), not JSON",
    "GET /api/v1/persons/cts/person-location": "410 Gone tombstone, no body",
    "GET /metrics": "Prometheus text exposition format, not JSON",
    "POST /api/v1/image/preview": "binary image bytes (Response), not JSON",
    "POST /api/v1/image/preview-form": "binary image bytes (Response), not JSON",}

# ─── 17b backlog ──────────────────────────────────────────────────────────
#
# Routes that return JSON but do not declare its shape. Delete lines from this
# list as 17b adds models; never add one. A route added here instead of fixed
# will fail review -- the whole point of M17 is that this list reaches empty.

DEFERRED_TO_17B: set[str] = {
    "GET /api/v1/admin/app-info",
    "GET /api/v1/admin/config/current",
    "GET /api/v1/admin/health",
    "GET /api/v1/admin/health/person-id",
    "GET /api/v1/admin/health/scene-analysis",
    "GET /api/v1/admin/health/semantic-memory",
    "GET /api/v1/admin/health/tracking-orchestrator",
    "GET /api/v1/admin/health/triton",
    "GET /api/v1/admin/health/tts",
    "GET /api/v1/admin/notification-channels/audit",
    "GET /api/v1/admin/telegram/trigger-defaults",
    "GET /api/v1/conversations/recent",
    "GET /api/v1/ha/entities",
    "GET /api/v1/ha/media-players",
    "GET /api/v1/health",
    "GET /api/v1/image/fonts",
    "GET /api/v1/info-cards",
    "GET /api/v1/info-cards/{card_id}",
    "GET /api/v1/interactive-responses",
    "GET /api/v1/knowledge-interactions/info-card-deliveries",
    "GET /api/v1/knowledge-interactions/queries",
    "GET /api/v1/knowledge-interactions/quiz-sessions",
    "GET /api/v1/knowledge-interactions/quiz-sessions/{session_id}",
    "GET /api/v1/knowledge/analytics/tags",
    "GET /api/v1/knowledge/documents",
    "GET /api/v1/knowledge/documents/{doc_id}",
    "GET /api/v1/knowledge/layouts",
    "GET /api/v1/knowledge/layouts/{layout_id}",
    "GET /api/v1/knowledge/voice-defaults",
    "GET /api/v1/occupancy/",
    "GET /api/v1/occupancy/history",
    "GET /api/v1/pipeline/image-sources/sample",
    "GET /api/v1/quizzes",
    "GET /api/v1/quizzes/{quiz_id}",
    "PATCH /api/v1/info-cards/{card_id}",
    "PATCH /api/v1/info-cards/{card_id}/slots/{slot_index}",
    "PATCH /api/v1/knowledge/documents/{doc_id}",
    "PATCH /api/v1/knowledge/documents/{doc_id}/images/{img_id}",
    "PATCH /api/v1/quizzes/{quiz_id}",
    "PATCH /api/v1/quizzes/{quiz_id}/questions/{qid}",
    "POST /api/v1/admin/config/reload",
    "POST /api/v1/device/recamera",
    "POST /api/v1/ha/sync/rooms",
    "POST /api/v1/ha/sync/sensors",
    "POST /api/v1/image/render",
    "POST /api/v1/image/reset",
    "POST /api/v1/info-cards",
    "POST /api/v1/info-cards/suggest",
    "POST /api/v1/info-cards/{card_id}/approve",
    "POST /api/v1/info-cards/{card_id}/archive",
    "POST /api/v1/info-cards/{card_id}/restore",
    "POST /api/v1/knowledge/documents",
    "POST /api/v1/knowledge/documents/{doc_id}/approve",
    "POST /api/v1/knowledge/documents/{doc_id}/archive",
    "POST /api/v1/knowledge/documents/{doc_id}/images",
    "POST /api/v1/knowledge/documents/{doc_id}/reembed",
    "POST /api/v1/knowledge/documents/{doc_id}/restore",
    "POST /api/v1/quizzes",
    "POST /api/v1/quizzes/suggest",
    "POST /api/v1/quizzes/voice-instruction-suggest",
    "POST /api/v1/quizzes/{quiz_id}/approve",
    "POST /api/v1/quizzes/{quiz_id}/archive",
    "POST /api/v1/quizzes/{quiz_id}/questions",
    "POST /api/v1/quizzes/{quiz_id}/questions/reorder",
    "POST /api/v1/quizzes/{quiz_id}/questions/{qid}/regenerate",
    "POST /api/v1/quizzes/{quiz_id}/restore",
    "POST /api/v1/webhooks/{rule_id}",
    "POST /api/v1/webhooks/{rule_id}/generate-secret",
    "PUT /api/v1/image/templates/{template_id}/image",
    "PUT /api/v1/info-cards/{card_id}/slots/{slot_index}",
    "PUT /api/v1/quizzes/{quiz_id}/questions/{qid}/image",}

# Domains migrated to the typed client in 17a: these must be fully declared, because
# `services/modules/{rules,pipeline,workflows}.ts` is generated against their schemas.
PILOT_MODULES = (
    "backend.routers.rules",
    "backend.routers.pipeline",
    "backend.routers.pipeline_runs",
    "backend.routers.workflows",
)


def _app() -> FastAPI:
    import backend.main

    return backend.main.app


def _api_routes() -> list[APIRoute]:
    return [r for r in _app().routes if isinstance(r, APIRoute)]


def _key(route: APIRoute) -> str:
    method = sorted(route.methods - {"HEAD", "OPTIONS"})[0]
    return f"{method} {route.path}"


def _undeclared() -> dict[str, APIRoute]:
    """Routes that return a JSON body without declaring its schema."""
    return {
        _key(r): r
        for r in _api_routes()
        # 204 has no body to describe.
        if r.response_model is None and r.status_code != 204
    }


def test_no_new_undeclared_response_models() -> None:
    """Every JSON route declares response_model, is allowlisted, or is known 17b debt."""
    unaccounted = set(_undeclared()) - set(ALLOWLISTED) - DEFERRED_TO_17B

    assert not unaccounted, (
        "Route(s) return JSON without a response_model, so the generated TypeScript types "
        "will be `unknown`:\n"
        + "\n".join(f"  {k}" for k in sorted(unaccounted))
        + "\n\nDeclare response_model on the route (preferred). Only add to ALLOWLISTED if the "
        "body genuinely has no JSON schema (binary/text), with a justification."
    )


def test_deferred_list_has_no_stale_entries() -> None:
    """A fixed route must be removed from the backlog, so the list stays honest."""
    fixed = DEFERRED_TO_17B - set(_undeclared())

    assert not fixed, (
        "Route(s) now declare a response_model but are still listed as deferred debt. "
        "Remove them from DEFERRED_TO_17B:\n" + "\n".join(f"  {k}" for k in sorted(fixed))
    )


def test_allowlist_has_no_stale_entries() -> None:
    """An allowlisted route that gained a model (or vanished) must leave the allowlist."""
    stale = set(ALLOWLISTED) - set(_undeclared())

    assert not stale, "Stale ALLOWLISTED entr(ies); remove them:\n" + "\n".join(
        f"  {k}" for k in sorted(stale)
    )


def test_pilot_domains_fully_declare_response_models() -> None:
    """17a's bar: the domains backing the typed client modules have no undeclared routes."""
    gaps = sorted(
        key for key, route in _undeclared().items() if route.endpoint.__module__ in PILOT_MODULES
    )

    assert not gaps, (
        "Pilot domain route(s) lack response_model; the generated client would type these "
        "as `unknown`:\n" + "\n".join(f"  {k}" for k in gaps)
    )
