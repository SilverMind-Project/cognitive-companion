"""SignalRewriter: applies IdentityRevision messages to CC-side signals.

When the orchestrator emits an ``IdentityRevision`` (automatic or manual),
CC must:

1. Soft-delete the affected ``DementiaSignal`` rows by stamping
   ``superseded_by_revision_id = revision.revision_id``. The rows remain
   for audit.
2. If ``new_identity_id`` is not ``None``, insert replacement rows with
   the revised person_id.
3. Write to the first-class audit log.

The rewriter is idempotent: replaying the same revision is a no-op because
the match query excludes already-rewritten rows.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.models.cts_identity_revision_log import CtsIdentityRevisionLog
from backend.models.cts_signal import DementiaSignal
from backend.services.cts._time import parse_ts
from backend.services.cts.signal_store import derive_signal_id

logger = get_logger(__name__)


class SignalRewriter:
    """Apply identity revisions to CC signal tables.

    Parameters
    ----------
    db_factory:
        Session factory for the raw query path (revision row lookup).
    ws_manager:
        Optional :class:`ConnectionManager` to broadcast revision events.
    revision_horizon_s:
        Fallback supersession window (seconds) for automatic revisions that
        carry no explicit ``range_start``/``range_end``. Mirrors CTS
        ``resolver.revision_horizon_s``; change both together.
    """

    SOURCE = "cts"

    def __init__(
        self,
        db_factory: Callable[[], Session],
        ws_manager: Any = None,
        revision_horizon_s: float = 600.0,
    ) -> None:
        self._db_factory = db_factory
        self._ws_manager = ws_manager
        self._revision_horizon_s = revision_horizon_s

    async def apply(self, revision: dict[str, Any]) -> dict[str, Any]:
        """Apply one revision dict.  Returns a summary dict with row counts."""
        revision_id = revision["revision_id"]
        ph_id = revision.get("ph_id") or None
        previous_identity_id = revision.get("previous_identity_id") or None
        new_identity_id = revision.get("new_identity_id") or None
        applied_at = parse_ts(revision.get("revision_time"))

        if previous_identity_id == new_identity_id:
            return {
                "revision_id": revision_id,
                "rewritten": 0,
                "inserted": 0,
                "signals_superseded": 0,
            }

        db = self._db_factory()
        try:
            if not previous_identity_id and not ph_id:
                return {
                    "revision_id": revision_id,
                    "rewritten": 0,
                    "inserted": 0,
                    "signals_superseded": 0,
                }

            range_start = (
                parse_ts(revision.get("range_start")) if revision.get("range_start") else None
            )
            range_end = parse_ts(revision.get("range_end")) if revision.get("range_end") else None
            horizon_applied = False
            if range_start is None and range_end is None and applied_at is not None:
                range_start = applied_at - timedelta(seconds=self._revision_horizon_s)
                range_end = applied_at
                horizon_applied = True

            signals_superseded = _supersede_signals(
                db,
                revision_id=revision_id,
                previous_identity_id=previous_identity_id,
                new_identity_id=new_identity_id,
                range_start=range_start,
                range_end=range_end,
            )

            revision_kind = revision.get("revision_kind") or ""
            kind = "manual_correct" if revision_kind.startswith("operator") else "auto"
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
                rewritten_rows=signals_superseded,
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
            signals_superseded=signals_superseded,
            range_start=range_start.isoformat() if range_start else None,
            range_end=range_end.isoformat() if range_end else None,
            horizon_applied=horizon_applied,
        )

        return {
            "revision_id": revision_id,
            "rewritten": signals_superseded,
            "inserted": 0,
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
                    signal_id=derive_signal_id(
                        new_identity_id,
                        row.signal_type,
                        row.window_start.isoformat(),
                        row.window_end.isoformat(),
                    ),
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
