"""IdentityRevisionSubscriber: consume tracking.revisions.

Decodes the JSON payload produced by the orchestrator's
:class:`tracking_orchestrator.app.transport.revision_publisher.RevisionPublisher`
and delegates to :class:`IdentityRewriter`.
"""

from __future__ import annotations

import json
from typing import Any

from backend.core.logging import get_logger
from backend.services.cts.identity_rewriter import IdentityRewriter
from backend.services.cts.stream_consumer import ConsumerConfig, StreamConsumer

logger = get_logger(__name__)


class IdentityRevisionSubscriber(StreamConsumer[dict[str, Any]]):
    """Consume ``tracking.revisions`` and apply each revision to CC state."""

    STREAM = "tracking.revisions"
    GROUP = "cognitive-companion-revisions"

    def __init__(
        self,
        redis_url: str,
        consumer_id: str,
        rewriter: IdentityRewriter,
        pipeline: Any = None,
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

    def decode(self, message_id: bytes, fields: dict) -> dict[str, Any] | None:
        """Parse the flat-field JSON payload from the orchestrator.

        Fields that were JSON-encoded on the producer side (``tracklet_ids``,
        ``evidence``) are decoded here; the rest are passed through as strings.
        """
        try:
            decoded = {_k(k): _v(v) for k, v in fields.items()}
        except Exception:
            logger.warning("revision_decode_error", message_id=message_id)
            return None

        required = {"revision_id", "global_track_id", "revision_time"}
        if not required.issubset(decoded):
            logger.warning(
                "revision_missing_fields",
                message_id=message_id,
                missing=required - set(decoded.keys()),
            )
            return None

        tracklet_ids: list[str] = []
        raw_tracklets = decoded.get("tracklet_ids", "[]")
        try:
            parsed = json.loads(raw_tracklets) if raw_tracklets else []
            if isinstance(parsed, list):
                tracklet_ids = [str(x) for x in parsed]
        except json.JSONDecodeError:
            logger.warning("revision_tracklet_ids_not_json", raw=raw_tracklets[:64])

        evidence: dict[str, Any] = {}
        raw_ev = decoded.get("evidence", "{}")
        try:
            parsed_ev = json.loads(raw_ev) if raw_ev else {}
            if isinstance(parsed_ev, dict):
                evidence = parsed_ev
        except json.JSONDecodeError:
            logger.warning("revision_evidence_not_json", raw=raw_ev[:64])

        return {
            "revision_id": decoded["revision_id"],
            "global_track_id": decoded["global_track_id"],
            "tracklet_ids": tracklet_ids,
            "previous_identity_id": decoded.get("previous_identity_id") or None,
            "new_identity_id": decoded.get("new_identity_id") or None,
            "map_identity_id": decoded.get("map_identity_id", ""),
            "posterior_entropy": _to_float(decoded.get("posterior_entropy")),
            "reason": decoded.get("reason", ""),
            "evidence": evidence,
            "revision_time": decoded["revision_time"],
        }

    async def handle(self, revision: dict[str, Any]) -> bool:
        """Apply the revision; fire a pipeline event if a pipeline is attached."""
        try:
            result = await self._rewriter.apply(revision)
        except Exception:
            logger.exception("identity_revision_apply_error", revision=revision)
            return False

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _k(key: Any) -> str:
    return key.decode("utf-8") if isinstance(key, bytes | bytearray) else str(key)


def _v(value: Any) -> str:
    if isinstance(value, bytes | bytearray):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default
