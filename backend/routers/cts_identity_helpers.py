"""CTS identity helpers: shared DB query utilities for the identity router family."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.core.database import get_session
from backend.core.logging import get_logger
from backend.models.cts_identity_revision_log import CtsIdentityRevisionLog

logger = get_logger(__name__)


def latest_posterior(global_track_id: str) -> dict | None:
    """Fetch the latest posterior evidence for a global track from the log."""
    db = get_session()
    try:
        row = (
            db.query(CtsIdentityRevisionLog)
            .filter(
                CtsIdentityRevisionLog.global_track_id == global_track_id,
                CtsIdentityRevisionLog.evidence.isnot(None),
            )
            .order_by(CtsIdentityRevisionLog.applied_at.desc())
            .first()
        )
        if row is None or not row.evidence:
            return None
        return row.evidence
    finally:
        db.close()


def write_manual_revision_log(
    *,
    revision_id: str | None,
    global_track_id: str,
    previous_identity_id: str | None,
    new_identity_id: str | None,
    actor: str,
    reason: str,
    kind: str,
    evidence: dict[str, Any] | None,
) -> None:
    """Write a preliminary manual identity decision to the audit log.

    Uses ON CONFLICT DO NOTHING: when the revision later flows back through
    the subscriber and the rewriter processes it, the rewriter's upsert will
    update ``rewritten_rows`` with the actual count while preserving the
    ``kind`` from this preliminary entry.
    """
    if not revision_id:
        logger.error("manual_revision_log_missing_revision_id")
        raise RuntimeError("Orchestrator correction response did not include revision_id")

    db = get_session()
    try:
        stmt = pg_insert(CtsIdentityRevisionLog).values(
            revision_id=revision_id,
            global_track_id=global_track_id,
            previous_identity_id=previous_identity_id,
            new_identity_id=new_identity_id,
            actor=actor,
            reason=reason,
            applied_at=datetime.now(UTC),
            kind=kind,
            rewritten_rows=0,
            evidence=evidence or {},
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[CtsIdentityRevisionLog.revision_id],
            set_={
                "kind": kind,
                "actor": actor,
                "reason": reason,
            },
        )
        db.execute(stmt)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("manual_revision_log_write_error")
        raise
    finally:
        db.close()
