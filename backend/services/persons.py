"""Shared household-member creation logic.

Extracted from ``routers/persons.py`` so the visitor-naming transaction
(identity-continuity M07) inserts a ``HouseholdMember`` row through the same
code path as the ordinary admin "create member" endpoint, instead of a second
copy that could drift. Conflict policy stays with each caller: the persons
router rejects an existing id outright, while the visitor-naming transaction
needs idempotent retry semantics (see ``backend/services/visitors.py``), so
this function does no existence check of its own.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.models.person import HouseholdMember


def insert_household_member(
    db: Session,
    *,
    id: str,
    name: str,
    is_guest: bool = False,
    metadata_json: dict | None = None,
) -> HouseholdMember:
    """Insert a new household member row. Caller must ensure ``id`` is free."""
    member = HouseholdMember(id=id, name=name, is_guest=is_guest, metadata_json=metadata_json)
    db.add(member)
    db.commit()
    db.refresh(member)
    return member
