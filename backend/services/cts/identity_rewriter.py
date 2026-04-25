"""IdentityRewriter: applies IdentityRevision messages to CC-side history.

When the orchestrator emits an ``IdentityRevision`` (automatic or manual),
CC must:

1. Soft-delete the affected ``PersonLocationHistory`` rows by stamping
   ``superseded_by_revision_id = revision.revision_id``. The rows remain
   for audit.
2. If ``new_identity_id`` is not ``None``, insert replacement rows with
   the revised person_id, copying the timing and room fields from the
   originals.
3. Upsert ``PersonLocationState`` for both the previous and new identities
   so current state reflects the correction.
4. Broadcast a ``cts_identity_revision`` WS event so any open Vue view can
   refresh.

The rewriter is idempotent: replaying the same revision is a no-op because
the match query (``superseded_by_revision_id IS NULL``) excludes already-
rewritten rows.

This implementation delegates persistence to a :class:`LocationRepository`
for consistency with :class:`LocationWriter` and testability.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.core.logging import get_logger
from backend.models.person import PersonLocationHistory, PersonLocationState

logger = get_logger(__name__)


class IdentityRewriter:
    """Apply identity revisions to CC location tables.

    Parameters
    ----------
    db_factory:
        Session factory for the raw query path (revision row lookup).
        The :class:`LocationRepository` handles structured writes, but
        the rewriter still needs a raw session for the multi-row UPDATE
        (stamping ``superseded_by_revision_id``) which doesn't map cleanly
        to the repository protocol.
    ws_manager:
        Optional :class:`ConnectionManager` to broadcast revision events.
    """

    SOURCE = "cts"

    def __init__(
        self,
        db_factory,
        ws_manager: Any = None,
    ) -> None:
        self._db_factory = db_factory
        self._ws_manager = ws_manager

    async def apply(self, revision: dict[str, Any]) -> dict[str, Any]:
        """Apply one revision dict.  Returns a summary dict with row counts."""
        revision_id = revision["revision_id"]
        global_track_id = revision.get("global_track_id") or None
        previous_identity_id = revision.get("previous_identity_id") or None
        new_identity_id = revision.get("new_identity_id") or None
        applied_at = _parse_ts(revision.get("revision_time"))

        if previous_identity_id == new_identity_id:
            return {"revision_id": revision_id, "rewritten": 0, "inserted": 0}

        db = self._db_factory()
        try:
            if not previous_identity_id and not global_track_id:
                # Nothing to rewrite; must know either who the prior identity
                # was or which global track carried the rewritten rows.
                return {"revision_id": revision_id, "rewritten": 0, "inserted": 0}

            query = db.query(PersonLocationHistory).filter(
                PersonLocationHistory.superseded_by_revision_id.is_(None),
            )
            if previous_identity_id:
                # Scope to the prior identity so we never rewrite the rows we
                # inserted for ``new_identity_id`` on an earlier pass.
                query = query.filter(
                    PersonLocationHistory.person_id == previous_identity_id
                )
            if global_track_id:
                query = query.filter(
                    PersonLocationHistory.global_track_id == global_track_id
                )

            affected = query.all()
            rewritten = 0
            inserted = 0

            for row in affected:
                row.superseded_by_revision_id = revision_id
                rewritten += 1

                if new_identity_id:
                    db.add(
                        PersonLocationHistory(
                            person_id=new_identity_id,
                            room_id=row.room_id,
                            room_name=row.room_name,
                            entered_at=row.entered_at,
                            exited_at=row.exited_at,
                            source=self.SOURCE,
                            direction_semantic=row.direction_semantic,
                            from_room_id=row.from_room_id,
                            from_room_name=row.from_room_name,
                            global_track_id=row.global_track_id,
                        )
                    )
                    inserted += 1

            # Update PersonLocationState for both prior + new identity so
            # live reads see the correction.
            if previous_identity_id and new_identity_id:
                prior = (
                    db.query(PersonLocationState)
                    .filter(PersonLocationState.person_id == previous_identity_id)
                    .first()
                )
                if prior is not None:
                    # Prior is no longer in that room from this track's POV.
                    prior.status = "unknown"

            if new_identity_id and affected:
                latest = max(affected, key=lambda r: r.entered_at)
                state = (
                    db.query(PersonLocationState)
                    .filter(PersonLocationState.person_id == new_identity_id)
                    .first()
                )
                if state is None:
                    state = PersonLocationState(
                        person_id=new_identity_id,
                        current_room_id=latest.room_id,
                        current_room_name=latest.room_name,
                        last_seen_at=applied_at,
                        last_sensor_id=self.SOURCE,
                        status="home",
                        confidence=1.0,
                    )
                    db.add(state)
                else:
                    state.current_room_id = latest.room_id
                    state.current_room_name = latest.room_name
                    state.last_seen_at = applied_at
                    state.last_sensor_id = self.SOURCE
                    state.status = "home"
                    state.confidence = 1.0

            db.commit()
        except Exception:
            db.rollback()
            logger.exception(
                "cts_identity_rewrite_error",
                revision_id=revision_id,
            )
            raise
        finally:
            db.close()

        logger.info(
            "cts_identity_revision_applied",
            revision_id=revision_id,
            global_track_id=global_track_id,
            previous_identity_id=previous_identity_id,
            new_identity_id=new_identity_id,
            rewritten=rewritten,
            inserted=inserted,
        )

        if self._ws_manager is not None:
            try:
                await self._ws_manager.broadcast(
                    {
                        "type": "cts_identity_revision",
                        "revision_id": revision_id,
                        "global_track_id": global_track_id,
                        "previous_identity_id": previous_identity_id,
                        "new_identity_id": new_identity_id,
                        "rewritten": rewritten,
                    }
                )
            except Exception:
                logger.exception("cts_identity_revision_ws_error")

        return {
            "revision_id": revision_id,
            "rewritten": rewritten,
            "inserted": inserted,
        }


def _parse_ts(value: str | datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
