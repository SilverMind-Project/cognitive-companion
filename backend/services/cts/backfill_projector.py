"""BackfillProjector: project an ``inferred_backfill`` IdentityRevision into the SSOT.

Identity-continuity M05 (dated-corrected design, 2026-07-19): CTS's Unknown-
backfill service (M04) emits one ``inferred_backfill`` revision per qualifying
first calibrated-face commit on a previously-Unknown Person Hypothesis. CC's
job is to make that recovered history visible to caregivers by inserting
closed presence segments into ``PersonLocationService`` (the SSOT since
hardening M32) for the revision's range.

This is a distinct responsibility from ``SignalRewriter``/the (deleted)
legacy ``IdentityRewriter``: their contract is "supersede existing attributed
rows"; this one's is "insert rows that never existed" (an Unknown segment has
no rows to supersede). ``IdentityRevisionSubscriber`` routes on
``revision_kind`` before either path runs.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.models.cts_identity_revision_log import CtsIdentityRevisionLog
from backend.models.room import Room
from backend.schemas.cts_ph_ws import PHCorrectionEvent
from backend.services.cts import metrics
from backend.services.cts._types import ConnectionManager
from backend.services.cts.member_provisioning import ensure_household_members
from backend.services.person_location.service import PersonLocationService
from backend.services.person_location.types import BackfillDwellInput

logger = get_logger(__name__)


class _BackfillRevision(BaseModel):
    """Validated shape of an ``inferred_backfill`` revision dict.

    ``model_config`` allows extra keys: the subscriber's ``decode()`` output
    carries fields (``reason``, ``evidence``, ``correction_id``, ...) this
    projector does not use.
    """

    model_config = {"extra": "ignore"}

    revision_id: str
    ph_id: str
    new_identity_id: str
    previous_identity_id: str | None = None
    range_start: datetime
    range_end: datetime
    revision_schema_version: str = "1"


@dataclass(frozen=True)
class ProjectionResult:
    outcome: str  # applied | skipped_duplicate | dropped_invalid | overlap_skipped
    rows_inserted: int = 0


class BackfillProjector:
    """Projects CTS ``inferred_backfill`` revisions into closed presence segments."""

    def __init__(
        self,
        *,
        db_factory: Callable[[], Session],
        orchestrator_client: object,
        person_location_service: PersonLocationService,
        ws_manager: ConnectionManager | None = None,
    ) -> None:
        self._db_factory = db_factory
        self._orchestrator = orchestrator_client
        self._person_location = person_location_service
        self._ws_manager = ws_manager

    async def project(self, revision: dict[str, Any]) -> bool:
        """Apply one ``inferred_backfill`` revision. Returns whether to XACK.

        ``True`` means the Redis message is safe to acknowledge: either the
        projection succeeded, or the input was malformed (a poison message
        must not wedge the consumer group). ``False`` (or a raised
        exception) means a transient failure -- the caller leaves the
        message pending for retry, matching the no-silent-fallback rule for
        stream consumers.
        """
        try:
            parsed = _BackfillRevision.model_validate(revision)
        except ValidationError:
            logger.warning("backfill_revision_invalid", revision=revision)
            metrics.cc_cts_backfill_projections_total.labels(outcome="dropped_invalid").inc()
            # A recognizable revision_id in an otherwise-malformed payload
            # still gets a failed ack: without it, CTS's job stays
            # "applying" forever with no signal that "cc" will never
            # complete it. No revision_id at all means there is no job to
            # unstick.
            await self._ack_failed_raw(revision)
            return True

        if parsed.previous_identity_id:
            logger.warning(
                "backfill_revision_has_previous_identity",
                revision_id=parsed.revision_id,
                previous_identity_id=parsed.previous_identity_id,
            )
            metrics.cc_cts_backfill_projections_total.labels(outcome="dropped_invalid").inc()
            await self._ack(parsed, rows_inserted=0, status="failed")
            return True

        if await self._person_location.has_backfill_segments(parsed.revision_id):
            logger.info(
                "backfill_revision_already_applied",
                revision_id=parsed.revision_id,
                ph_id=parsed.ph_id,
            )
            metrics.cc_cts_backfill_projections_total.labels(outcome="skipped_duplicate").inc()
            await self._ack(parsed, rows_inserted=0)
            return True

        # Upstream failure here is deliberately allowed to propagate: the
        # stream message must be retried (no XACK), never silently dropped.
        envelope = await self._orchestrator.list_room_dwells(  # type: ignore[attr-defined]
            ph_id=parsed.ph_id,
            start=parsed.range_start.isoformat(),
            end=parsed.range_end.isoformat(),
        )
        raw_dwells = envelope.get("dwells")
        if raw_dwells is None:
            # Contract failure, not "no dwells": a well-formed empty response
            # is {"dwells": []}. Treat a missing key as an upstream shape
            # violation and retry rather than silently projecting nothing.
            raise ValueError(f"trajectory/dwells envelope missing 'dwells' key: {envelope!r}")

        dwells = self._resolve_dwells(raw_dwells, still_open_exited_at=parsed.range_end)

        ensure_household_members(self._db_factory, {parsed.new_identity_id})

        result = await self._person_location.ingest_backfill_segments(
            revision_id=parsed.revision_id,
            person_id=parsed.new_identity_id,
            dwells=dwells,
            range_start=parsed.range_start,
            range_end=parsed.range_end,
        )

        self._write_audit_log(parsed, rows_inserted=result.inserted)
        await self._broadcast(parsed)
        await self._ack(parsed, rows_inserted=result.inserted)

        metrics.cc_cts_backfill_rows_inserted_total.inc(result.inserted)
        metrics.cc_cts_backfill_projections_total.labels(outcome="applied").inc()
        logger.info(
            "backfill_revision_applied",
            revision_id=parsed.revision_id,
            ph_id=parsed.ph_id,
            new_identity_id=parsed.new_identity_id,
            rows_inserted=result.inserted,
            dropped_unmapped_room=result.dropped_unmapped_room,
            dropped_zero_length=result.dropped_zero_length,
            overlap_skipped=result.overlap_skipped,
        )
        return True

    def _resolve_dwells(
        self, raw_dwells: list[dict[str, Any]], *, still_open_exited_at: datetime
    ) -> list[BackfillDwellInput]:
        """Resolve each dwell's ``room_name`` to a ``rooms.id`` by exact match.

        A dwell whose room cannot be resolved is dropped (logged and
        counted), never inserted with a fabricated room -- ``room_id`` is
        NOT NULL on ``presence_segments``. A dwell with ``exited_at is None``
        (the PH's live-edge room, still open when CTS answered the query)
        extends to ``still_open_exited_at`` (the revision's ``range_end``),
        rather than collapsing to a zero-length segment.
        """
        room_names = {raw["room_name"] for raw in raw_dwells}
        db = self._db_factory()
        try:
            rooms = db.query(Room).filter(Room.name.in_(room_names)).all()
            room_ids: dict[str, int] = {r.name: r.id for r in rooms}
        finally:
            db.close()

        resolved: list[BackfillDwellInput] = []
        for raw in raw_dwells:
            room_name = raw["room_name"]
            exited_at = (
                datetime.fromisoformat(raw["exited_at"])
                if raw["exited_at"]
                else still_open_exited_at
            )
            resolved.append(
                BackfillDwellInput(
                    room_id=room_ids.get(room_name),
                    room_name=room_name,
                    entered_at=datetime.fromisoformat(raw["entered_at"]),
                    exited_at=exited_at,
                    confidence=float(raw.get("entry_confidence", 0.5)),
                )
            )
        return resolved

    def _write_audit_log(self, parsed: _BackfillRevision, *, rows_inserted: int) -> None:
        db = self._db_factory()
        try:
            db.add(
                CtsIdentityRevisionLog(
                    revision_id=parsed.revision_id,
                    ph_id=parsed.ph_id,
                    previous_identity_id=None,
                    new_identity_id=parsed.new_identity_id,
                    actor="system",
                    reason="unknown_backfill",
                    kind="inferred_backfill",
                    rewritten_rows=rows_inserted,
                    evidence={
                        "range_start": parsed.range_start.isoformat(),
                        "range_end": parsed.range_end.isoformat(),
                    },
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("backfill_audit_log_write_failed", revision_id=parsed.revision_id)
            raise
        finally:
            db.close()

    async def _broadcast(self, parsed: _BackfillRevision) -> None:
        if self._ws_manager is None:
            return
        try:
            evt = PHCorrectionEvent(
                revision_id=parsed.revision_id,
                ph_id=parsed.ph_id,
                previous_identity_id=None,
                new_identity_id=parsed.new_identity_id,
                actor="system",
                reason="unknown_backfill",
                kind="inferred_backfill",
                applied_at=parsed.range_end,
            )
            await self._ws_manager.broadcast(evt.model_dump(mode="json"))
        except Exception:
            logger.exception("backfill_ws_broadcast_failed", revision_id=parsed.revision_id)

    async def _ack(
        self, parsed: _BackfillRevision, *, rows_inserted: int, status: str = "acked"
    ) -> None:
        try:
            await self._orchestrator.post_projection_ack(  # type: ignore[attr-defined]
                revision_id=parsed.revision_id,
                consumer="cc",
                schema_version=parsed.revision_schema_version,
                status=status,
                counts={"inserted": rows_inserted},
            )
        except Exception:
            logger.exception(
                "backfill_projection_ack_failed",
                revision_id=parsed.revision_id,
            )

    async def _ack_failed_raw(self, revision: dict[str, Any]) -> None:
        """Best-effort failed ack from the raw (unvalidated) revision dict.

        Used when ``_BackfillRevision`` validation itself fails but a
        ``revision_id`` string is still present: without this, CTS's
        projection job for that revision_id would stay ``applying`` forever
        with nothing ever telling it "cc" cannot complete it.
        """
        revision_id = revision.get("revision_id")
        if not revision_id:
            return
        try:
            await self._orchestrator.post_projection_ack(  # type: ignore[attr-defined]
                revision_id=revision_id,
                consumer="cc",
                schema_version=revision.get("revision_schema_version") or "1",
                status="failed",
                counts={},
            )
        except Exception:
            logger.exception("backfill_projection_ack_failed", revision_id=revision_id)
