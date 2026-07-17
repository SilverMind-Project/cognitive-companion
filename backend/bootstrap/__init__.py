"""Composition-root wiring, split by phase (M20).

Every service the app depends on is constructed here, in the exact order
``backend/main.py``'s lifespan used to construct it inline, and assigned onto
``app.state`` (or the shared :class:`~backend.steps.base.ServiceContainer`).
See ``README.md`` in this package for the full attribute inventory and the
phase each one belongs to.

``backend.bootstrap`` is wiring, not an API: nothing outside
``backend.main`` and this package may import it (enforced by the
``backend.pyproject.toml`` import-linter contract), and this package may
never import ``backend.routers`` (wiring must not reach into HTTP handlers).
"""

from __future__ import annotations
