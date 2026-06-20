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

from collections.abc import Callable
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.models.cts_identity_revision_log import CtsIdentityRevisionLog
from backend.models.cts_signal import DementiaSignal
from backend.models.person import PersonLocationHistory, PersonLocationState
from backend.services.cts._time import parse_ts

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
        db_factory: Callable[[], Session],
        ws_manager: Any = None,
    ) -> None:
        self._db_factory = db_factory
        self._ws_manager = ws_manager

    async def apply(self, revision: dict[str, Any]) -> dict[str, Any]:
        """Apply one revision dict.  Returns a summary dict with row counts."""
        revision_id = revision["revision_id"]
        ph_id = revision.get("ph_id") or None
        previous_identity_id = revision.get("previous_identity_id") or None
        new_identity_id = revision.get("new_identity_id") or None
        applied_at = parse_ts(revision.get("revision_time"))

        if previous_identity_id == new_identity_id:
            return {"revision_id": revision_id, "rewritten": 0, "inserted": 0}

        db = self._db_factory()
        try:
            if not previous_identity_id and not ph_id:
                # Nothing to rewrite; must know either who the prior identity
                # was or which global track carried the rewritten rows.
                return {"revision_id": revision_id, "rewritten": 0, "inserted": 0}

            query = db.query(PersonLocationHistory).filter(
                PersonLocationHistory.superseded_by_revision_id.is_(None),
            )
            if previous_identity_id:
                # Scope to the prior identity so we never rewrite the rows we
                # inserted for ``new_identity_id`` on an earlier pass.
                query = query.filter(PersonLocationHistory.person_id == previous_identity_id)
            if ph_id:
                query = query.filter(PersonLocationHistory.ph_id == ph_id)

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
                            ph_id=row.ph_id,
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

            # M06: supersede dementia-signal rows under the prior identity within
            # the corrected range and insert replacements under the new identity.
            # Originals are retained for audit.
            signals_superseded = _supersede_signals(
                db,
                revision_id=revision_id,
                previous_identity_id=previous_identity_id,
                new_identity_id=new_identity_id,
                range_start=parse_ts(revision.get("range_start"))
                if revision.get("range_start")
                else None,
                range_end=parse_ts(revision.get("range_end"))
                if revision.get("range_end")
                else None,
            )

            # Write to the first-class audit log.  Use ON CONFLICT DO UPDATE
            # for rewritten_rows so that a preliminary manual entry (written
            # by the corrections router with rewritten_rows=0) gets updated
            # with the actual count once the rewriter processes the revision.
            revision_kind = revision.get("revision_kind") or ""
            kind = "manual_correct" if revision_kind.startswith("operator") else "auto"
            # Retain the M06 revision-range lineage alongside the evidence so the
            # CC audit log mirrors the CTS operator record.
            evidence = dict(revision.get("evidence") or {})
            for key in (
                "revision_kind",
                "range_start",
                "range_end",
                "range_authority",
                "revision_range_id",
                "correction_id",
            ):
                value = revision.get(key)
                if value is not None:
                    evidence[key] = value

            _upsert_revision_log(
                db,
                revision_id=revision_id,
                ph_id=ph_id or "",
                previous_identity_id=previous_identity_id,
                new_identity_id=new_identity_id,
                actor=revision.get("actor") or "cts_resolver",
                reason=revision.get("reason"),
                applied_at=applied_at,
                kind=kind,
                rewritten_rows=rewritten,
                evidence=evidence,
            )

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
            ph_id=ph_id,
            previous_identity_id=previous_identity_id,
            new_identity_id=new_identity_id,
            rewritten=rewritten,
            inserted=inserted,
            signals_superseded=signals_superseded,
        )

        if self._ws_manager is not None:
            try:
                await self._ws_manager.broadcast(
                    {
                        "type": "cts_identity_revision",
                        "revision_id": revision_id,
                        "ph_id": ph_id,
                        "previous_identity_id": previous_identity_id,
                        "new_identity_id": new_identity_id,
                        "rewritten": rewritten,
                    }
                )
            except (
                Exception
            ):  # WS broadcast is a non-required side-effect; failure must not undo the DB revision
                logger.exception("cts_identity_revision_ws_error")

        return {
            "revision_id": revision_id,
            "rewritten": rewritten,
            "inserted": inserted,
            "signals_superseded": signals_superseded,
        }


def _supersede_signals(
    db: Session,
    *,
    revision_id: str,
    previous_identity_id: str | None,
    new_identity_id: str | None,
    range_start,
    range_end,
) -> int:
    """Supersede dementia-signal rows under the prior identity within the range.

    Each affected row is stamped with ``superseded_by_revision_id`` (retained for
    audit) and, when a new identity is given, copied under it. Idempotent on
    replay because already-superseded rows are filtered out. Returns the count of
    superseded rows.
    """
    if not previous_identity_id or range_start is None or range_end is None:
        return 0

    rows = (
        db.query(DementiaSignal)
        .filter(
            DementiaSignal.superseded_by_revision_id.is_(None),
            DementiaSignal.person_id == previous_identity_id,
            DementiaSignal.window_start >= range_start,
            DementiaSignal.window_start <= range_end,
        )
        .all()
    )
    superseded = 0
    for row in rows:
        row.superseded_by_revision_id = revision_id
        superseded += 1
        if new_identity_id:
            db.add(
                DementiaSignal(
                    signal_id=row.signal_id,
                    person_id=new_identity_id,
                    signal_type=row.signal_type,
                    severity=row.severity,
                    window_start=row.window_start,
                    window_end=row.window_end,
                    value=row.value,
                    baseline=row.baseline,
                    z_score=row.z_score,
                    context_json=row.context_json,
                    algorithm_version=row.algorithm_version,
                    evidence_grade=row.evidence_grade,
                )
            )
    return superseded


def _upsert_revision_log(
    db: Session,
    *,
    revision_id: str,
    ph_id: str,
    previous_identity_id: str | None,
    new_identity_id: str | None,
    actor: str,
    reason: str | None,
    applied_at,
    kind: str,
    rewritten_rows: int,
    evidence: dict | None,
) -> None:
    """Insert or update a row in ``cts_identity_revision_log``.

    Uses PostgreSQL ON CONFLICT to update ``rewritten_rows`` when a
    preliminary entry already exists (e.g. from a manual correction).
    """
    stmt = pg_insert(CtsIdentityRevisionLog).values(
        revision_id=revision_id,
        ph_id=ph_id,
        previous_identity_id=previous_identity_id,
        new_identity_id=new_identity_id,
        actor=actor,
        reason=reason,
        applied_at=applied_at,
        kind=kind,
        rewritten_rows=rewritten_rows,
        evidence=evidence,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[CtsIdentityRevisionLog.revision_id],
        set_={
            "rewritten_rows": stmt.excluded.rewritten_rows,
            "evidence": stmt.excluded.evidence,
        },
    )
    db.execute(stmt)
