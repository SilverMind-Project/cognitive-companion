"""Tests for ``ConversationManager``.

Uses the shared ``db_factory`` fixture from ``backend/tests/conftest.py`` so
every test runs against an isolated PostgreSQL test database with the real
ORM schema.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.models.conversation import ConversationTurn
from backend.services.conversation_manager import (
    ALLOWED_ACTORS,
    ConversationManager,
    _actor_label,
)

# ---------------------------------------------------------------------------
# _actor_label
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("actor", "label"),
    [
        ("user", "User"),
        ("assistant", "Assistant"),
        ("orchestrator", "Orchestrator"),
        ("rules_engine", "Rules Engine"),
        ("system", "System"),
        ("caregiver", "Caregiver"),
        ("custom_agent", "Custom_Agent"),
    ],
)
def test_actor_label(actor: str, label: str) -> None:
    assert _actor_label(actor) == label


# ---------------------------------------------------------------------------
# session lifecycle
# ---------------------------------------------------------------------------


def test_create_and_end_session(db_factory) -> None:
    manager = ConversationManager(db_factory)
    session_id = manager.create_session()
    assert isinstance(session_id, int)

    manager.end_session(session_id)

    from backend.models.conversation import ConversationSession

    db = db_factory()
    try:
        session = db.get(ConversationSession, session_id)
        assert session is not None
        assert session.ended_at is not None
    finally:
        db.close()


def test_end_missing_session_is_noop(db_factory) -> None:
    manager = ConversationManager(db_factory)
    manager.end_session(99999)  # must not raise


def test_ensure_session_creates_external_session(db_factory) -> None:
    manager = ConversationManager(db_factory)

    session_id = manager.ensure_session(42)
    manager.add_turn(session_id, "caregiver", "please try again")

    db = db_factory()
    try:
        turn = db.query(ConversationTurn).one()
        assert turn.session_id == 42
        assert turn.actor == "caregiver"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# add_turn
# ---------------------------------------------------------------------------


def test_add_turn_persists(db_factory) -> None:
    manager = ConversationManager(db_factory)
    session_id = manager.create_session()
    manager.add_turn(session_id, "user", "hello there")

    db = db_factory()
    try:
        turns = db.query(ConversationTurn).all()
        assert len(turns) == 1
        assert turns[0].actor == "user"
        assert turns[0].content == "hello there"
    finally:
        db.close()


def test_add_turn_strips_whitespace(db_factory) -> None:
    manager = ConversationManager(db_factory)
    session_id = manager.create_session()
    manager.add_turn(session_id, "user", "   padded   ")
    db = db_factory()
    try:
        turn = db.query(ConversationTurn).one()
        assert turn.content == "padded"
    finally:
        db.close()


def test_add_turn_empty_content_skipped(db_factory) -> None:
    manager = ConversationManager(db_factory)
    session_id = manager.create_session()
    manager.add_turn(session_id, "user", "   ")
    db = db_factory()
    try:
        assert db.query(ConversationTurn).count() == 0
    finally:
        db.close()


def test_add_turn_stores_metadata(db_factory) -> None:
    manager = ConversationManager(db_factory)
    session_id = manager.create_session()
    manager.add_turn(session_id, "assistant", "response", metadata={"model": "gemini"})
    db = db_factory()
    try:
        turn = db.query(ConversationTurn).one()
        assert turn.metadata_json == {"model": "gemini"}
    finally:
        db.close()


def test_caregiver_role_accepted(db_factory) -> None:
    manager = ConversationManager(db_factory)
    session_id = manager.create_session()

    manager.add_turn(session_id, "caregiver", "try the next step")

    db = db_factory()
    try:
        turn = db.query(ConversationTurn).one()
        assert turn.actor == "caregiver"
    finally:
        db.close()


def test_existing_roles_unchanged() -> None:
    assert {"user", "assistant", "orchestrator", "rules_engine", "system"}.issubset(ALLOWED_ACTORS)
    assert "caregiver" in ALLOWED_ACTORS


# ---------------------------------------------------------------------------
# get_history_text
# ---------------------------------------------------------------------------


def _backdate_turns(db_factory, session_id: int, rows: list[tuple[str, str, int]]) -> None:
    """Insert turns with explicit timestamps so ordering is deterministic.

    Each row is ``(actor, content, seconds_ago)``.
    """
    db = db_factory()
    try:
        now = datetime.now(UTC)
        for actor, content, seconds_ago in rows:
            db.add(
                ConversationTurn(
                    session_id=session_id,
                    actor=actor,
                    content=content,
                    timestamp=now - timedelta(seconds=seconds_ago),
                )
            )
        db.commit()
    finally:
        db.close()


def test_history_text_chronological_order(db_factory) -> None:
    manager = ConversationManager(db_factory)
    session_id = manager.create_session()
    _backdate_turns(
        db_factory,
        session_id,
        [("user", "first", 30), ("assistant", "second", 20), ("user", "third", 10)],
    )

    history = manager.get_history_text(session_id)
    lines = history.split("\n")
    assert lines == ["User: first", "Assistant: second", "User: third"]


def test_history_filters_by_ttl(db_factory) -> None:
    manager = ConversationManager(db_factory)
    manager.ttl_minutes = 10
    session_id = manager.create_session()

    # Insert an old turn directly so we can backdate the timestamp.
    db = db_factory()
    try:
        old = ConversationTurn(
            session_id=session_id,
            actor="user",
            content="ancient",
            timestamp=datetime.now(UTC) - timedelta(hours=1),
        )
        db.add(old)
        db.commit()
    finally:
        db.close()

    manager.add_turn(session_id, "user", "recent")
    history = manager.get_history_text(session_id)
    assert "ancient" not in history
    assert "recent" in history


def test_history_respects_max_turns(db_factory) -> None:
    manager = ConversationManager(db_factory)
    manager.max_turns = 2
    session_id = manager.create_session()
    _backdate_turns(
        db_factory,
        session_id,
        [("user", f"msg{i}", (5 - i) * 10) for i in range(5)],
    )

    history = manager.get_history_text(session_id)
    lines = history.split("\n")
    assert len(lines) == 2
    # Most recent two, in chronological order.
    assert lines[-1] == "User: msg4"
    assert lines[-2] == "User: msg3"


def test_history_other_session_isolated(db_factory) -> None:
    manager = ConversationManager(db_factory)
    s1 = manager.create_session()
    s2 = manager.create_session()
    manager.add_turn(s1, "user", "in session one")
    manager.add_turn(s2, "user", "in session two")

    assert "session one" in manager.get_history_text(s1)
    assert "session two" not in manager.get_history_text(s1)


# ---------------------------------------------------------------------------
# get_recent_turns
# ---------------------------------------------------------------------------


def test_get_recent_turns_returns_dicts(db_factory) -> None:
    manager = ConversationManager(db_factory)
    session_id = manager.create_session()
    manager.add_turn(session_id, "user", "hi", metadata={"k": "v"})

    turns = manager.get_recent_turns(session_id)
    assert len(turns) == 1
    assert turns[0]["actor"] == "user"
    assert turns[0]["content"] == "hi"
    assert turns[0]["metadata"] == {"k": "v"}
    assert turns[0]["timestamp"] is not None


def test_get_recent_turns_limit(db_factory) -> None:
    manager = ConversationManager(db_factory)
    session_id = manager.create_session()
    _backdate_turns(
        db_factory,
        session_id,
        [("user", f"m{i}", (5 - i) * 10) for i in range(5)],
    )

    turns = manager.get_recent_turns(session_id, limit=3)
    assert len(turns) == 3
    assert turns[-1]["content"] == "m4"


# ---------------------------------------------------------------------------
# prune_old_turns
# ---------------------------------------------------------------------------


def test_prune_removes_old_turns(db_factory) -> None:
    manager = ConversationManager(db_factory)
    manager.ttl_minutes = 10
    session_id = manager.create_session()

    db = db_factory()
    try:
        db.add(
            ConversationTurn(
                session_id=session_id,
                actor="user",
                content="ancient",
                timestamp=datetime.now(UTC) - timedelta(hours=1),
            )
        )
        db.add(
            ConversationTurn(
                session_id=session_id,
                actor="user",
                content="fresh",
                timestamp=datetime.now(UTC),
            )
        )
        db.commit()
    finally:
        db.close()

    count = manager.prune_old_turns()
    assert count == 1

    db = db_factory()
    try:
        remaining = db.query(ConversationTurn).all()
        assert len(remaining) == 1
        assert remaining[0].content == "fresh"
    finally:
        db.close()


def test_prune_nothing_to_delete(db_factory) -> None:
    manager = ConversationManager(db_factory)
    assert manager.prune_old_turns() == 0
