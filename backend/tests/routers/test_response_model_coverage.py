"""Response-model coverage gate (M17).

Generated TypeScript types are only as good as the schema the backend advertises: a JSON route
without `response_model` becomes `unknown` in `frontend/src/generated/api-types.d.ts`, which
silently pushes the contract back to the hand-written guesswork that `contracts.js` used to
paper over.

Every JSON route now declares one. Two exemptions, and only two:

* **204 No Content** -- exempt by status code, not by list. There is no body to describe, so a
  response model would be noise (31 routes, mostly DELETEs).
* **ALLOWLISTED** -- genuinely schemaless: binary bodies and Prometheus text. Each carries a
  justification. Adding a line here is a contract decision, and the bar is "this response has no
  JSON schema", not "writing one is inconvenient".

17a staged a backlog of 71 undeclared routes and 17b closed all of them, so there is no third
bucket any more: a JSON route either declares its shape or fails this test.
"""

from __future__ import annotations

from fastapi.routing import RouteContext

from backend.tests.routers._route_inventory import api_route_contexts, route_key

# ─── Genuinely schemaless ─────────────────────────────────────────────────
#
# Every entry needs a justification: these are contract decisions, not debt.

ALLOWLISTED: dict[str, str] = {
    "GET /api/v1/cts/cameras/{camera_id}/snapshot": "binary snapshot bytes (Response), not JSON",
    "GET /api/v1/cts/frames/{key:path}": "binary frame bytes (Response), not JSON",
    "GET /api/v1/image/active": "binary image bytes (Response), not JSON",
    "GET /api/v1/image/templates/{template_id}/preview": "binary image bytes (Response), not JSON",
    "GET /metrics": "Prometheus text exposition format, not JSON",
    "POST /api/v1/image/preview": "binary image bytes (Response), not JSON",
    "POST /api/v1/image/preview-form": "binary image bytes (Response), not JSON",
}


def _undeclared() -> dict[str, RouteContext]:
    """Routes that return a JSON body without declaring its schema."""
    return {
        route_key(c): c
        for c in api_route_contexts()
        # 204 has no body to describe.
        if c.response_model is None and c.status_code != 204
    }


def test_every_json_route_declares_a_response_model() -> None:
    """The gate: a JSON route declares its shape, or it is provably schemaless."""
    unaccounted = set(_undeclared()) - set(ALLOWLISTED)

    assert not unaccounted, (
        "Route(s) return JSON without a response_model, so the generated TypeScript types "
        "will be `unknown` and the frontend is back to guessing:\n"
        + "\n".join(f"  {k}" for k in sorted(unaccounted))
        + "\n\nDeclare response_model on the route. Only add to ALLOWLISTED if the body "
        "genuinely has no JSON schema (binary/text), with a justification."
    )


def test_allowlist_has_no_stale_entries() -> None:
    """An allowlisted route that gained a model (or vanished) must leave the allowlist.

    Without this the allowlist quietly becomes a place where exemptions accumulate and outlive
    the reason they were granted.
    """
    stale = set(ALLOWLISTED) - set(_undeclared())

    assert not stale, "Stale ALLOWLISTED entr(ies); remove them:\n" + "\n".join(
        f"  {k}" for k in sorted(stale)
    )
