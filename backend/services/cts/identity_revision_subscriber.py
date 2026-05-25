"""IdentityRevisionSubscriber: consume tracking.revisions (proto wire format).

Decodes ``IdentityRevision`` proto messages from the
``tracking.revisions`` Redis Stream and delegates to
:class:`IdentityRewriter`.
"""

from __future__ import annotations

import json
from typing import Any

from backend.core.logging import get_logger
from backend.integrations.proto.continuoustracking.v1 import tracking_pb2
from backend.services.cts import metrics
from backend.services.cts._time import ns_to_iso
from backend.services.cts._types import PipelineExecutor
from backend.services.cts.identity_rewriter import IdentityRewriter
from backend.services.cts.stream_consumer import ConsumerConfig, StreamConsumer

logger = get_logger(__name__)

FIELD = b"revision"


class IdentityRevisionSubscriber(StreamConsumer[dict[str, Any]]):
    """Consume ``tracking.revisions`` and apply each revision to CC state."""

    STREAM = "tracking.revisions"
    GROUP = "cognitive-companion-revisions"

    def __init__(
        self,
        redis_url: str,
        consumer_id: str,
        rewriter: IdentityRewriter,
        pipeline: PipelineExecutor | None = None,
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

        if not message.revision_id or not message.global_track_id:
            logger.warning(
                "revision_missing_required_fields",
                message_id=message_id,
                revision_id=message.revision_id,
                global_track_id=message.global_track_id,
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
            "global_track_id": message.global_track_id,
            "tracklet_ids": list(message.tracklet_ids),
            "previous_identity_id": message.previous_identity_id or None,
            "new_identity_id": message.new_identity_id or None,
            "map_identity_id": message.map_identity_id,
            "posterior_entropy": float(message.posterior_entropy),
            "reason": message.reason,
            "evidence": evidence,
            "revision_time": ns_to_iso(message.revision_time_unix_ns),
        }

    async def handle(self, revision: dict[str, Any]) -> bool:
        metrics.cts_revisions_received.inc()
        try:
            result = await self._rewriter.apply(revision)
        except Exception:
            logger.exception("identity_revision_apply_error", revision=revision)
            metrics.cts_revisions_dropped.inc()
            return False

        metrics.cts_revisions_persisted.inc()

        if self._pipeline is not None:
            try:
                await self._pipeline.fire_event(
                    source="cts",
                    kind="identity_revision",
                    payload={
                        "revision_id": revision["revision_id"],
                        "global_track_id": revision.get("global_track_id"),
                        "previous_identity_id": revision.get("previous_identity_id"),
                        "new_identity_id": revision.get("new_identity_id"),
                        "reason": revision.get("reason"),
                        "rewritten_rows": result.get("rewritten", 0),
                    },
                )
            except Exception:
                logger.exception("identity_revision_pipeline_fire_error")

        return True
