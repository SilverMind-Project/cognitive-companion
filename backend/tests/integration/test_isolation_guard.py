"""Regression guard for the DB test-isolation fragility class (M15 / C11).

The bug: ``_truncate_tables`` in ``backend/tests/conftest.py`` used to gate
truncation on whether a test *requested* the ``db_session``/``db_factory``
fixture by name (``request.fixturenames``). Any test that opens its own
session straight off the shared ``db_engine`` (a `TestClient` dependency
override, a service constructed with its own factory, ...) writes real rows
that the name-gated fixture never sees, so they leak into whatever test runs
next.

This pair reproduces that leak deterministically: test A commits a row via
an engine-direct session (no ``db_session``/``db_factory`` in its
fixturenames), test B (alphabetically and by definition order, guaranteed to
run second -- pytest-randomly is not installed in this project) asserts the
table is empty. Under the old fixture-name gate this pair fails (test B
sees test A's row); under the engine-checkout-event listener it passes,
because the listener fires for *any* write through ``db_engine``,
regardless of which fixture requested it.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.models.cts_camera import CtsCamera

pytestmark = pytest.mark.integration


def test_a_leaks_a_row_via_engine_direct_session(db_engine: Engine) -> None:
    """Writes through a session built straight off db_engine.

    Deliberately does *not* request ``db_session``/``db_factory`` -- that is
    the whole point of the guard: this is exactly how a `TestClient`
    dependency override or a service-owned session writes in this suite.
    """
    factory = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    session: Session = factory()
    try:
        session.add(CtsCamera(id="isolation-guard-leak", name="leak"))
        session.commit()
    finally:
        session.close()


def test_b_sees_no_leftover_rows(db_session: Session) -> None:
    """If this fails, engine-direct writes are leaking past teardown."""
    rows = db_session.query(CtsCamera).all()
    assert rows == [], (
        "table not empty at start of test -- a prior test wrote through "
        "db_engine directly and teardown did not truncate it"
    )
