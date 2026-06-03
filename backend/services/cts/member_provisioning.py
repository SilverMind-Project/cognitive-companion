"""Auto-provision HouseholdMember rows for CTS-discovered identities.

``presence_segments`` and ``location_observations`` both carry a NOT-NULL FK
to ``household_members.id``, and the world tracker emits an ``identity_id``
that *is* the member id by convention. The legacy ``LocationRepository``
auto-created the member row to satisfy that FK; the
``PersonLocationService`` write path does not, so the CTS ingress boundary
must ensure the row exists before ingesting an identified observation.

Uses ``INSERT ... ON CONFLICT DO NOTHING`` so it is safe to call
concurrently with the legacy ``LocationWriter`` consuming the same stream.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.models.person import HouseholdMember

logger = get_logger(__name__)


def ensure_household_members(
    db_factory: Callable[[], Session], identity_ids: set[str]
) -> None:
    """Ensure a HouseholdMember row exists for each id in ``identity_ids``."""
    ids = {i for i in identity_ids if i}
    if not ids:
        return
    db = db_factory()
    try:
        rows = []
        for identity_id in ids:
            is_guest = identity_id == "unknown" or identity_id.startswith("unknown_")
            rows.append(
                {
                    "id": identity_id,
                    "name": "Guest" if is_guest else identity_id,
                    "is_guest": is_guest,
                }
            )
        stmt = pg_insert(HouseholdMember).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
        db.execute(stmt)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("ensure_household_members_error", count=len(ids))
        raise
    finally:
        db.close()
