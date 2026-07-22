"""IdentityRevisionSubscriber: consume tracking.revisions (proto wire format).

Decodes ``IdentityRevision`` proto messages from the
``tracking.revisions`` Redis Stream and delegates to
:class:`SignalRewriter`.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine
from typing import Any

from backend.core.logging import get_logger
from backend.integrations.proto.continuoustracking.v1 import tracking_pb2
from backend.schemas.cts_ph_ws import PHCorrectionEvent
from backend.services.cts import metrics
from backend.services.cts._time import ns_to_iso
from backend.services.cts._types import ConnectionManager, PipelineExecutor
from backend.services.cts.signal_rewriter import SignalRewriter
from backend.services.cts.stream_consumer import ConsumerConfig, StreamConsumer

logger = get_logger(__name__)

FIELD = b"revision"


def _run_off_loop[T](coro: Coroutine[Any, Any, T]) -> Coroutine[Any, Any, T]:
    """Run a coroutine on a worker thread via its own event loop.

    ``SignalRewriter.apply`` and ``PersonLocationService.apply_identity_revision``
    are ``async def`` in name only: every ``await`` inside them resolves a
    synchronous, blocking SQLAlchemy call (no real async I/O). Awaiting them
    directly runs that blocking work on the shared event loop, so a large
    revision replay (hundreds of segments after downtime) froze the entire
    process -- HTTP requests, other CTS consumers, the scheduler -- for the
    whole drain. ``asyncio.run`` in a fresh thread gives the coroutine its
    own loop, safe because neither depends on the caller's loop or its state.
    """
    return asyncio.to_thread(asyncio.run, coro)


class IdentityRevisionSubscriber(StreamConsumer[dict[str, Any]]):
    """Consume ``tracking.revisions`` and apply each revision to CC state."""

    STREAM = "tracking.revisions"
    GROUP = "cognitive-companion-revisions"

    def __init__(
        self,
        redis_url: str,
        consumer_id: str,
        rewriter: SignalRewriter,
        pipeline: PipelineExecutor | None = None,
        ws_manager: ConnectionManager | None = None,
        person_location_service: object | None = None,
        orchestrator_client: object | None = None,
        backfill_projector: object | None = None,
    ) -> None:
        super().__init__(
            ConsumerConfig(
                redis_url=redis_url,
                stream=self.STREAM,
                group=self.GROUP,
                consumer_id=consumer_id,
                concurrency=1,
            )
        )
        self._rewriter = rewriter
        self._pipeline = pipeline
        self._ws_manager = ws_manager
        self._pls = person_location_service
        self._orchestrator = orchestrator_client
        self._backfill_projector = backfill_projector

    # -- StreamConsumer abstract methods -------------------------------------

    def decode(
        self, message_id: bytes, fields: dict[bytes | str, bytes | str]
    ) -> dict[str, Any] | None:
        payload = fields.get(FIELD) or fields.get(FIELD.decode())
        if payload is None:
            logger.warning("revision_missing_payload", message_id=message_id)
            return None
        if isinstance(payload, str):
            payload = payload.encode("latin-1")

        try:
            message = tracking_pb2.IdentityRevision.FromString(payload)
        except Exception:
            logger.exception("revision_proto_decode_error", message_id=message_id)
            metrics.cts_revisions_decode_errors.inc()
            return None

        if not message.revision_id or not message.ph_id:
            logger.warning(
                "revision_missing_required_fields",
                message_id=message_id,
                revision_id=message.revision_id,
                ph_id=message.ph_id,
            )
            return None

        try:
            evidence = json.loads(message.evidence_json) if message.evidence_json else {}
            if not isinstance(evidence, dict):
                evidence = {}
        except json.JSONDecodeError:
            logger.warning("revision_evidence_not_json", raw=message.evidence_json[:64])
            evidence = {}

        return {
            "revision_id": message.revision_id,
            "ph_id": message.ph_id,
            "previous_identity_id": message.previous_identity_id or None,
            "new_identity_id": message.new_identity_id or None,
            "reason": message.reason,
            "evidence": evidence,
            "revision_time": ns_to_iso(message.revision_time_unix_ns),
            # -- typed revision-range / projection metadata --
            "revision_kind": message.revision_kind or None,
            "range_start": ns_to_iso(message.range_start_unix_ns)
            if message.range_start_unix_ns
            else None,
            "range_end": ns_to_iso(message.range_end_unix_ns)
            if message.range_end_unix_ns
            else None,
            "range_authority": message.range_authority or None,
            "revision_range_id": message.revision_range_id or None,
            "correction_id": message.correction_id or None,
            "required_projections": list(message.required_projections),
            "revision_schema_version": message.revision_schema_version or "1",
        }

    async def handle(self, revision: dict[str, Any]) -> bool:
        metrics.cts_revisions_received.inc()

        # An inferred_backfill revision has no rows
        # to supersede (an Unknown segment was never attributed in the first
        # place), so it routes entirely to the projector instead of the
        # rewriter/apply_identity_revision/pipeline/WS-broadcast path below.
        # The projector owns its own ack, audit log, and WS broadcast.
        if revision.get("revision_kind") == "inferred_backfill":
            if self._backfill_projector is None:
                logger.warning(
                    "backfill_projector_unavailable", revision_id=revision.get("revision_id")
                )
                return False
            return await self._backfill_projector.project(revision)  # type: ignore[attr-defined]

        try:
            result = await _run_off_loop(self._rewriter.apply(revision))
        except Exception:
            logger.exception("identity_revision_apply_error", revision=revision)
            metrics.cts_revisions_dropped.inc()
            # Tell CTS this projection failed so the revision job is marked
            # failed and retried idempotently. Never acknowledge success.
            await self._ack_projection(revision, status="failed", counts={})
            return False

        metrics.cts_revisions_persisted.inc()

        # acknowledge the projection so CTS can complete the revision job.
        # Only revisions that explicitly require the "cc" projection expect an
        # ack; legacy automatic revisions carry no required_projections.
        await self._ack_projection(
            revision,
            status="acked",
            counts={
                "rewritten": int(result.get("rewritten", 0)),
                "inserted": int(result.get("inserted", 0)),
            },
        )

        # Apply revision to PersonLocationService for segment rewrites.
        if self._pls is not None:
            try:
                from datetime import UTC, datetime

                rev_time_str = revision.get("revision_time")
                if rev_time_str:
                    rev_time = datetime.fromisoformat(rev_time_str.replace("Z", "+00:00"))
                else:
                    rev_time = datetime.now(UTC)
                await _run_off_loop(
                    self._pls.apply_identity_revision(  # type: ignore[attr-defined]
                        old_person_id=revision.get("previous_identity_id") or "",
                        new_person_id=revision.get("new_identity_id"),
                        ph_id=revision.get("ph_id", ""),
                        revision_time=rev_time,
                    )
                )
            except Exception:
                logger.exception("identity_revision_pls_apply_error")

        if self._pipeline is not None:
            try:
                await self._pipeline.fire_event(
                    source="cts",
                    kind="identity_revision",
                    payload={
                        "revision_id": revision["revision_id"],
                        "ph_id": revision.get("ph_id"),
                        "previous_identity_id": revision.get("previous_identity_id"),
                        "new_identity_id": revision.get("new_identity_id"),
                        "reason": revision.get("reason"),
                        "rewritten_rows": result.get("rewritten", 0),
                    },
                )
            except Exception:
                logger.exception("identity_revision_pipeline_fire_error")

        if self._ws_manager is not None:
            try:
                evt = PHCorrectionEvent(
                    revision_id=revision["revision_id"],
                    ph_id=revision.get("ph_id", ""),
                    previous_identity_id=revision.get("previous_identity_id"),
                    new_identity_id=revision.get("new_identity_id"),
                    actor="",
                    reason=revision.get("reason", ""),
                    kind="auto",
                    applied_at=revision.get("revision_time"),
                )
                await self._ws_manager.broadcast(evt.model_dump(mode="json"))
            except Exception:
                logger.exception("cts_ph_correction_broadcast_error")

        return True

    async def _ack_projection(
        self, revision: dict[str, Any], *, status: str, counts: dict[str, int]
    ) -> None:
        """POST a projection ack back to CTS (M06), best-effort.

        Only revisions that list ``cc`` in ``required_projections`` expect an
        ack; legacy automatic revisions carry none and are skipped. Ack failure
        never undoes the local rewrite; CTS retries the job idempotently.
        """
        required = revision.get("required_projections") or []
        if self._orchestrator is None or "cc" not in required:
            return
        try:
            await self._orchestrator.post_projection_ack(  # type: ignore[attr-defined]
                revision_id=revision["revision_id"],
                consumer="cc",
                schema_version=revision.get("revision_schema_version") or "1",
                status=status,
                counts=counts,
            )
        except Exception:
            logger.exception("cts_projection_ack_failed", revision_id=revision.get("revision_id"))
