"""Route inventory for the **composed** app.

Every route-level gate in this directory (auth coverage, response-model
coverage, route uniqueness) has to enumerate what the assembled application
actually serves. They used to do it with::

    [r for r in app.routes if isinstance(r, APIRoute)]

FastAPI 0.139 made ``include_router`` lazy: instead of copying each route into
``app.routes``, it appends one opaque ``_IncludedRouter`` wrapper per included
router and expands it at match time. The comprehension above therefore stopped
finding included routes and returned **1 route out of 322** (only the inline
``/api/v1/health``).

Nothing failed loudly. The gates kept passing, because "no route violates the
rule" is trivially true when you can see one route. The auth-coverage gate in
particular certified an entire API surface it was no longer looking at. The two
tests that did fail (a stale-allowlist check and a person-location resolution
pin) failed only because they assert routes are *present*, which is what
eventually surfaced this.

The lesson is in ``test_route_inventory.py``: a gate that enumerates a
collection needs a non-vacuity canary, or an upstream change can silently empty
the collection and every assertion over it becomes a tautology.

``iter_route_contexts`` is the traversal FastAPI's own OpenAPI generator uses
(``fastapi/openapi/utils.py``), so it stays correct as long as the schema does.
A ``RouteContext`` exposes the **effective** route: ``.path`` carries the
include-time prefix, while ``.original_route`` is the ``APIRoute`` as declared.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.routing import APIRoute, RouteContext, iter_route_contexts
from starlette.routing import compile_path

# Non-vacuity floor for the canary in ``test_route_inventory.py``. Deliberately
# far below the real count (322 at the time of writing): this exists to catch a
# traversal that has broken outright, not to be bumped on every added endpoint.
MIN_EXPECTED_API_ROUTES = 200


def app() -> FastAPI:
    """The composed application.

    ``backend.main`` imports without a database (route definitions only, no
    lifespan), which is what makes these gates cheap enough to always run.
    """
    import backend.main

    return backend.main.app


def route_contexts() -> list[RouteContext]:
    """Every route the composed app serves, includes expanded, in match order."""
    return list(iter_route_contexts(app().routes))


def api_route_contexts() -> list[RouteContext]:
    """Just the ``APIRoute`` entries (the JSON/HTTP API surface)."""
    return [c for c in route_contexts() if isinstance(c.original_route, APIRoute)]


def primary_method(ctx: RouteContext) -> str:
    """The route's method for keying, ignoring the automatic HEAD/OPTIONS."""
    return sorted((ctx.methods or set()) - {"HEAD", "OPTIONS"})[0]


def route_key(ctx: RouteContext) -> str:
    """``"METHOD /effective/path"`` -- the identifier the gate allowlists use."""
    return f"{primary_method(ctx)} {ctx.path}"


def endpoint_ref(ctx: RouteContext) -> str:
    """``"module.function"`` for the handler that serves this route."""
    return f"{ctx.endpoint.__module__}.{ctx.name}"


def resolve(path: str, method: str = "GET") -> str:
    """Return the endpoint the app dispatches ``path`` to, or ``"NO MATCH"``.

    Resolution, not registration: a static path can be swallowed by an earlier
    path *parameter* (``/persons/{person_id}`` capturing ``/persons/locations``),
    which no by-path lookup would show.

    Matching is done against the **effective** path via ``compile_path``.
    ``RouteContext.original_route.matches()`` is not usable here: it carries the
    route's declared path, so a router mounted under a prefix would never match
    the real URL (``/rooms`` vs ``/api/v1/rooms``).
    """
    for ctx in api_route_contexts():
        pattern, _, _ = compile_path(ctx.path)
        if pattern.match(path) and method in (ctx.methods or set()):
            return endpoint_ref(ctx)
    return "NO MATCH"
