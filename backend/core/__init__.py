"""
``backend.core`` — foundational layer for the Cognitive Companion backend.

This package hosts the small number of primitives that every other backend
subsystem depends on:

* :mod:`backend.core.config` — YAML-backed :class:`Settings`
* :mod:`backend.core.database` — SQLAlchemy :class:`Database` wrapper
* :mod:`backend.core.auth` — :class:`KeyStore` + :class:`AuthContext`
* :mod:`backend.core.exceptions` — HTTP-aware :class:`AppError` hierarchy
* :mod:`backend.core.logging` — stdlib :class:`BoundLogger` wrapper
* :mod:`backend.core.template` — ``{{dotted.path}}`` renderer

All public symbols are re-exported here so call sites can simply do::

    from backend.core import settings, get_logger, AppError

though the per-module imports currently used throughout the codebase
(``from backend.core.config import settings`` etc.) remain fully supported.

Design invariants for this layer
--------------------------------
1. **No framework imports except FastAPI-specific leaves.** ``config``,
   ``logging``, ``template``, and ``exceptions`` must be usable without
   FastAPI; only ``auth`` and ``exceptions.register_exception_handlers``
   may touch FastAPI types.
2. **No dependency on higher-level packages.** Modules in ``backend.core``
   must not import from ``backend.services``, ``backend.routers``,
   ``backend.channels``, etc. ``backend.models`` is only imported lazily
   from :meth:`Database.create_all` to populate the ORM metadata.
3. **Testability first.** Every stateful singleton in this package is a
   thin facade over a class that can be instantiated directly in a test.
"""

from __future__ import annotations

from backend.core.auth import AuthContext, KeyStore, get_auth_context, require_permission
from backend.core.config import Settings, settings
from backend.core.database import Base, Database, get_db, get_session, init_db
from backend.core.exceptions import (
    AppError,
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
    register_exception_handlers,
)
from backend.core.logging import BoundLogger, get_logger, setup_logging
from backend.core.template import render_template, resolve_path

__all__ = [
    "AppError",
    "AuthContext",
    "AuthenticationError",
    "Base",
    "BoundLogger",
    "ConflictError",
    "Database",
    "KeyStore",
    "NotFoundError",
    "PermissionDeniedError",
    "Settings",
    "ValidationError",
    "get_auth_context",
    "get_db",
    "get_logger",
    "get_session",
    "init_db",
    "register_exception_handlers",
    "render_template",
    "require_permission",
    "resolve_path",
    "settings",
    "setup_logging",
]
