"""Route-uniqueness gate (C17).

Starlette matches the *first* registered route for a given path; a second
registration of the same ``(path, method)`` is silently unreachable. Every
router suite in this tree mounts its router on a throwaway ``FastAPI()``, so a
shadowed route still passes its own tests -- which is exactly how the U2
person-location envelope endpoints stayed dead behind the legacy ``persons.py``
duplicates while their suites were green.

These checks only mean anything against the **composed** app, so that is what
they load. ``backend.main`` imports without a database (route definitions only,
no lifespan), same as ``test_route_auth_coverage.py``.
"""

from __future__ import annotations

from collections import defaultdict

from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.routing import Match


def _app() -> FastAPI:
    import backend.main

    return backend.main.app


def _api_routes() -> list[APIRoute]:
    return [r for r in _app().routes if isinstance(r, APIRoute)]


def _endpoint(route: APIRoute) -> str:
    return f"{route.endpoint.__module__}.{route.name}"


def test_no_duplicate_path_method_registrations() -> None:
    """No (path, method) is registered twice: the second one never serves.

    Grouping by (path, method) rather than by function name is deliberate -- the
    C17 pair ``get_all_locations`` / ``get_all_person_locations`` collided on the
    path while having different names, so a name-based check missed it.
    """
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for route in _api_routes():
        for method in route.methods:
            groups[(route.path, method)].append(_endpoint(route))

    duplicates = {key: eps for key, eps in groups.items() if len(eps) > 1}

    assert not duplicates, "Shadowed route(s) -- only the first registration serves:\n" + "\n".join(
        f"  {method} {path}\n    serves:    {eps[0]}\n    shadowed:  {', '.join(eps[1:])}"
        for (path, method), eps in sorted(duplicates.items())
    )


def test_no_duplicate_operation_ids() -> None:
    """Operation IDs are unique, so the generated OpenAPI spec matches runtime.

    ``app.openapi()`` builds ``paths`` as a dict keyed by path, so a duplicate
    lets the *last* registration win the spec while the *first* wins at runtime
    -- the spec then advertises a response model the endpoint never returns, and
    every client generated from it inherits the lie (M17). FastAPI warns about
    this, but a warning nothing reads is not a gate.
    """
    spec = _app().openapi()

    seen: dict[str, str] = {}
    collisions: list[str] = []
    for path, operations in spec["paths"].items():
        for method, operation in operations.items():
            op_id = operation.get("operationId")
            if op_id is None:
                continue
            where = f"{method.upper()} {path}"
            if op_id in seen:
                collisions.append(f"  {op_id!r}: {seen[op_id]} and {where}")
            else:
                seen[op_id] = where

    assert not collisions, "Duplicate operationId(s) in the OpenAPI spec:\n" + "\n".join(
        sorted(collisions)
    )


def _resolve(path: str, method: str = "GET") -> str:
    """Return the endpoint Starlette actually dispatches ``path`` to.

    Resolution, not registration: a static path can also be swallowed by an
    earlier path *parameter* (``/persons/{person_id}`` capturing
    ``/persons/locations``), which is a distinct failure from a duplicate
    registration and invisible to a by-path lookup.
    """
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "path_params": {},
        "headers": [],
        "query_string": b"",
        "root_path": "",
    }
    for route in _api_routes():
        if route.matches(scope)[0] is Match.FULL:
            return _endpoint(route)
    return "NO MATCH"


def test_person_location_endpoints_serve_the_envelope() -> None:
    """The U2 envelope handlers own the current-location paths (C17 regression).

    Pinned explicitly because the failure was invisible from the frontend's side
    of the contract: the legacy shape shares only ``person_id`` with
    ``PersonLocationEnvelope``, so the tracking panels rendered raw person ids
    and "Unknown" rooms rather than erroring.

    ``/persons/locations`` is the load-bearing case -- it is static, and the
    ``/persons/{person_id}`` route would capture it as ``person_id="locations"``
    (404 "Member 'locations' not found") if the include order in ``main.py``
    regressed.
    """
    for path in ("/api/v1/persons/locations", "/api/v1/persons/{person_id}/location"):
        resolved = _resolve(path.replace("{person_id}", "alice"))
        assert resolved.startswith("backend.routers.persons_location."), (
            f"GET {path} dispatches to {resolved}; it must be served by "
            "routers.persons_location (PersonLocationService SSOT, shared with the MCP tools)"
        )
