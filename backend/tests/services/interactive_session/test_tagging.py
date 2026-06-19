from __future__ import annotations

from backend.services.interactive_session.tagging import (
    _PREFIX_BUILDERS,
    prefix_for_delivery,
    register_session_prefix,
)


def test_prefix_for_quiz_matches_legacy() -> None:
    assert (
        prefix_for_delivery({"delivery_type": "quiz_start", "session_id": 7}) == "[quiz session 7]"
    )


def test_prefix_for_unknown_delivery_type_returns_empty() -> None:
    assert prefix_for_delivery({"delivery_type": "unknown", "session_id": 7}) == ""


def test_prefix_for_missing_session_id_returns_empty() -> None:
    assert prefix_for_delivery({"delivery_type": "quiz_start"}) == ""


def test_register_session_prefix_adds_builder() -> None:
    previous_builders = dict(_PREFIX_BUILDERS)
    try:
        register_session_prefix("sample", lambda session_id: f"[sample {session_id}]")

        assert prefix_for_delivery({"delivery_type": "sample", "session_id": 9}) == "[sample 9]"
    finally:
        _PREFIX_BUILDERS.clear()
        _PREFIX_BUILDERS.update(previous_builders)


def test_prefix_for_empty_metadata_returns_empty() -> None:
    assert prefix_for_delivery(None) == ""
