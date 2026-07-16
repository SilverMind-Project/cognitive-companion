"""BFF service for the M07 grouped keyframe read model.

One service function powers the router and the MCP tool. It validates the
orchestrator's physical-frame envelope, derives the card summary, and maps
effective identity onto Cognitive Companion's internal ``person_id``. It never
re-queries the orchestrator or recomputes authority/confidence/conflict, which
are server-owned upstream.
"""

from __future__ import annotations

import logging

from pydantic import ValidationError

from backend.integrations.tracking_orchestrator_client import OrchestratorClient
from backend.schemas.cts_keyframe import (
    IdentitySummaryItem,
    KeyframeBboxView,
    KeyframePage,
    KeyframeTriggerView,
    PhysicalFrameCard,
    UpstreamBbox,
    UpstreamFrame,
    UpstreamKeyframePage,
)

logger = logging.getLogger(__name__)

_UPSTREAM = "tracking_orchestrator"
_GROUPED_PATH = "/internal/keyframes/grouped"


class KeyframeReadContractError(Exception):
    """Raised when the orchestrator's grouped envelope violates the contract.

    Routers map this to HTTP 502 so contract drift is a visible incident rather
    than an empty keyframe list.
    """


def _source_badge(bbox: UpstreamBbox) -> str:
    """One presentation badge for a bbox, derived server-side from provenance."""
    if bbox.conflict:
        return "Conflict"
    if bbox.authority == "operator":
        return "Operator"
    source = bbox.decision_source
    if source == "face":
        # Authoritative ArcFace vs weak/uncalibrated face evidence. "direct_face" is the
        # resolver's bounded IdentityAuthority vocabulary value (M07/F9) -- never an
        # identity id or the decision_source string "arcface_authority".
        return "ArcFace" if bbox.authority == "direct_face" else "ArcFace / Uncalibrated"
    if source == "reid":
        return "ReID"
    if source in {"temporal_prior", "prior"}:
        return "Prior"
    return source or "Unknown"


def _build_card(frame: UpstreamFrame) -> PhysicalFrameCard:
    bbox_views: list[KeyframeBboxView] = []
    # Group by effective identity for the card summary, in first-seen order.
    summary_order: list[str | None] = []
    counts: dict[str | None, int] = {}
    badges: dict[str | None, list[str]] = {}

    for b in frame.bboxes:
        # Effective identity is the household identity id, which is CC's
        # internal person_id; map directly at this boundary (no alias).
        person_id = b.effective_identity_id
        bbox_views.append(
            KeyframeBboxView(
                bbox_id=b.bbox_id,
                ph_id=b.ph_id,
                x1=b.x1,
                y1=b.y1,
                x2=b.x2,
                y2=b.y2,
                detection_confidence=b.detection_confidence,
                frame_width=b.frame_width,
                frame_height=b.frame_height,
                inferred_identity_id=b.inferred_identity_id,
                effective_identity_id=b.effective_identity_id,
                person_id=person_id,
                authority=b.authority,
                decision_source=b.decision_source,
                calibrated_confidence=b.calibrated_confidence,
                conflict=b.conflict,
                conflict_kind=b.conflict_kind,
                revision_id=b.revision_id,
                pending_review=b.pending_review,
                override_x1=b.override_x1,
                override_y1=b.override_y1,
                override_x2=b.override_x2,
                override_y2=b.override_y2,
            )
        )
        eid = b.effective_identity_id
        if eid not in counts:
            summary_order.append(eid)
            counts[eid] = 0
            badges[eid] = []
        counts[eid] += 1
        badge = _source_badge(b)
        if badge not in badges[eid]:
            badges[eid].append(badge)

    identity_summary = [
        IdentitySummaryItem(
            effective_identity_id=eid,
            person_id=eid,
            count=counts[eid],
            source_badges=sorted(badges[eid]),
        )
        for eid in summary_order
    ]

    return PhysicalFrameCard(
        physical_frame_id=frame.physical_frame_id,
        camera_id=frame.camera_id,
        minio_key=frame.minio_key,
        captured_at=frame.captured_at,
        frame_width=frame.frame_width,
        frame_height=frame.frame_height,
        triggers=[
            KeyframeTriggerView(keyframe_id=t.keyframe_id, ph_id=t.ph_id, tag_reason=t.tag_reason)
            for t in frame.triggers
        ],
        trigger_reasons=frame.trigger_reasons,
        identity_summary=identity_summary,
        unknown_count=frame.unknown_count,
        conflict_count=frame.conflict_count,
        pending_review_count=frame.pending_review_count,
        bboxes=bbox_views,
        keyframe_id=frame.physical_frame_id,
        sample_id=frame.physical_frame_id,
    )


class KeyframeReadService:
    """Compose browser-facing physical-frame cards from the orchestrator."""

    def __init__(self, client: OrchestratorClient) -> None:
        self._client = client

    async def list_frames(
        self,
        *,
        camera_id: str | None = None,
        tag_reason: str | None = None,
        after: str | None = None,
        before: str | None = None,
        effective_identity_id: str | None = None,
        explicit_unknown: bool = False,
        authority: str | None = None,
        decision_source: str | None = None,
        conflict_only: bool = False,
        pending_review_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> KeyframePage:
        params: dict[str, str] = {"limit": str(limit), "offset": str(offset)}
        if camera_id:
            params["camera_id"] = camera_id
        if tag_reason:
            params["tag_reason"] = tag_reason
        if after:
            params["after"] = after
        if before:
            params["before"] = before
        if effective_identity_id:
            params["effective_identity_id"] = effective_identity_id
        if explicit_unknown:
            params["explicit_unknown"] = "true"
        if authority:
            params["authority"] = authority
        if decision_source:
            params["decision_source"] = decision_source
        if conflict_only:
            params["conflict_only"] = "true"
        if pending_review_only:
            params["pending_review_only"] = "true"

        raw = await self._client.list_keyframe_frames(params)
        try:
            page = UpstreamKeyframePage.model_validate(raw)
        except ValidationError as exc:
            logger.error(
                "keyframe read model contract violation from %s%s: %s",
                _UPSTREAM,
                _GROUPED_PATH,
                exc,
            )
            raise KeyframeReadContractError(
                "orchestrator returned a malformed keyframe envelope"
            ) from exc

        cards = [_build_card(f) for f in page.frames]
        return KeyframePage(
            keyframes=cards,
            count=len(cards),
            total=page.total,
            truncated=page.truncated,
            limit=limit,
            offset=offset,
        )
