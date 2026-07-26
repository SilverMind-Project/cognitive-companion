"""Non-vacuity canary for the route-level gates.

The auth-coverage, response-model and route-uniqueness gates are all of the
shape "no route in this collection violates X". That assertion is trivially
true when the collection is empty, so the collection itself needs a test.

It did not have one, and a FastAPI upgrade (0.139, lazy ``include_router``)
quietly reduced the enumerated surface from 322 routes to 1. Every gate stayed
green while checking almost nothing, including the one that certifies every
endpoint is permission-guarded.

If this file fails, do not adjust the numbers to make it pass: the traversal in
``_route_inventory`` has stopped seeing the application, and the gates that
depend on it are no longer meaningful.
"""

from __future__ import annotations

from backend.tests.routers._route_inventory import (
    MIN_EXPECTED_API_ROUTES,
    api_route_contexts,
    resolve,
    route_key,
)


def test_inventory_sees_the_whole_api_surface() -> None:
    """The enumeration is not empty, near-empty, or silently truncated."""
    routes = api_route_contexts()

    assert len(routes) >= MIN_EXPECTED_API_ROUTES, (
        f"Route inventory found only {len(routes)} API routes, expected at least "
        f"{MIN_EXPECTED_API_ROUTES}. The traversal in _route_inventory.py has broken "
        "(FastAPI changed how include_router stores routes once already); every gate "
        "built on it is now vacuous. Fix the traversal, do not lower this floor."
    )


def test_inventory_reports_effective_prefixed_paths() -> None:
    """Paths carry the include-time prefix, not the router-local path.

    A gate keyed on ``/rooms`` instead of ``/api/v1/rooms`` would silently stop
    matching its own allowlist entries.
    """
    keys = {route_key(c) for c in api_route_contexts()}

    assert "GET /api/v1/rooms" in keys
    assert "GET /rooms" not in keys


def test_inventory_spans_multiple_routers() -> None:
    """Routes come from across the app, not just one include.

    Guards the failure mode where a traversal expands the first included router
    and stops, which would look healthy on a count alone.
    """
    modules = {c.endpoint.__module__ for c in api_route_contexts()}

    for module in (
        "backend.routers.rooms",
        "backend.routers.persons_location",
        "backend.routers.activities",
        "backend.routers.cts_signals",
        "backend.routers.admin_metrics",
    ):
        assert module in modules, f"No routes found from {module}; traversal is incomplete"


def test_resolution_matches_prefixed_routes() -> None:
    """``resolve`` works against effective paths, not declared ones."""
    assert resolve("/api/v1/rooms").startswith("backend.routers.rooms.")
