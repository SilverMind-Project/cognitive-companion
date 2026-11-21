"""BFF service for inspecting and revoking wearable-taught artifacts per association segment."""

from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import HTTPException
from pydantic import ValidationError

from backend.core.exceptions import NotFoundError
from backend.core.logging import get_logger
from backend.core.upstream_errors import UpstreamError
from backend.integrations.tracking_orchestrator_client import OrchestratorClient
from backend.schemas.wearables import (
    PromotedAttestationOut,
    WearableAssociationTaughtOut,
    WearableDeviceAssociationsOut,
    WearableResumeTeachingResponse,
    WearableRevokeResponse,
    WearableTeachingHoldOut,
)
from backend.services.wearables.repositories import SqlAlchemyWearableRepository

logger = get_logger(__name__)


def _raise_upstream(exc: UpstreamError) -> HTTPException:
    code = "wearable_revocation.upstream"
    message = f"{exc.service} returned HTTP {exc.status}"
    try:
        detail = json.loads(exc.body).get("detail")
        if isinstance(detail, dict):
            code = str(detail.get("code") or code)
            message = str(detail.get("message") or message)
    except json.JSONDecodeError, AttributeError, TypeError:
        pass
    status_code = 502 if exc.status >= 500 else exc.status
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


class WearableTeachingRevocationService:
    """Coordinates wearable association inspection, revocation, and teaching resume via CTS."""

    def __init__(
        self,
        repo: SqlAlchemyWearableRepository,
        orchestrator: OrchestratorClient | None,
    ) -> None:
        self._repo = repo
        self._orchestrator = orchestrator

    def _require_orchestrator(self) -> OrchestratorClient:
        if self._orchestrator is None:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "wearable_revocation.unavailable",
                    "message": "Tracking orchestrator is not enabled",
                },
            )
        return self._orchestrator

    async def list_device_associations(
        self, device_id: uuid.UUID, *, limit: int = 25
    ) -> WearableDeviceAssociationsOut:
        with self._repo.session() as db:
            device = self._repo.get_device(db, device_id)
            if device is None:
                raise NotFoundError(f"Wearable device {device_id} not found")
            resolved_device_id = device.id
            tag_id = device.tag_id
        client = self._require_orchestrator()
        try:
            raw_assocs, raw_holds = await asyncio.gather(
                client.list_wearable_associations(tag_id=tag_id, limit=limit),
                client.list_wearable_holds(),
            )
        except UpstreamError as exc:
            raise _raise_upstream(exc) from exc

        try:
            holds = [WearableTeachingHoldOut.model_validate(h) for h in raw_holds]
        except (ValidationError, TypeError) as exc:
            logger.warning("wearable_holds_contract_violation", error=type(exc).__name__)
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "wearable_revocation.upstream_contract",
                    "message": "malformed wearable holds envelope",
                },
            ) from exc

        open_hold = next((h for h in holds if h.tag_id == tag_id and h.cleared_at is None), None)

        async def _taught(seg: dict) -> dict | None:
            seg_id = seg.get("segment_id")
            if not isinstance(seg_id, str) or not seg_id:
                return None
            try:
                return await client.get_wearable_association_taught(seg_id)
            except UpstreamError:
                return None

        taught_rows = await asyncio.gather(*(_taught(seg) for seg in raw_assocs))
        associations: list[WearableAssociationTaughtOut] = []
        try:
            for seg, taught in zip(raw_assocs, taught_rows, strict=True):
                merged = {
                    "segment_id": seg["segment_id"],
                    "ph_id": seg["ph_id"],
                    "tag_id": seg["tag_id"],
                    "identity_id": seg["identity_id"],
                    "started_at": seg["started_at"],
                    "ended_at": seg.get("ended_at"),
                    "attestation_grade": seg["attestation_grade"],
                    "swap_suspected": seg.get("swap_suspected", False),
                    "close_reason": seg.get("close_reason"),
                    "revoked_at": seg.get("revoked_at"),
                    "revoked_by": seg.get("revoked_by"),
                    "revoke_reason": seg.get("revoke_reason"),
                }
                if isinstance(taught, dict):
                    merged.update(
                        {
                            "gallery_rows_by_state": taught.get("gallery_rows_by_state") or {},
                            "gallery_rows_total": taught.get("gallery_rows_total", 0),
                            "attested_faces_total": taught.get("attested_faces_total"),
                            "attested_faces_active": taught.get("attested_faces_active"),
                            "attested_faces_revoked": taught.get("attested_faces_revoked"),
                            "attested_faces_promoted": taught.get("attested_faces_promoted"),
                            "inferred_ranges_live": taught.get("inferred_ranges_live", 0),
                            "inferred_ranges_total": taught.get("inferred_ranges_total", 0),
                        }
                    )
                associations.append(WearableAssociationTaughtOut.model_validate(merged))
        except (KeyError, TypeError, ValidationError) as exc:
            logger.warning("wearable_associations_contract_violation", error=type(exc).__name__)
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "wearable_revocation.upstream_contract",
                    "message": "malformed wearable associations envelope",
                },
            ) from exc

        return WearableDeviceAssociationsOut(
            device_id=resolved_device_id,
            tag_id=tag_id,
            teaching_held=open_hold is not None,
            open_hold=open_hold,
            associations=associations,
        )

    async def revoke_association(
        self, segment_id: str, *, actor: str
    ) -> WearableRevokeResponse:
        client = self._require_orchestrator()
        try:
            raw = await client.revoke_wearable_association(
                segment_id, actor=actor, reason="operator"
            )
        except UpstreamError as exc:
            raise _raise_upstream(exc) from exc
        try:
            return WearableRevokeResponse(
                segment_id=raw["segment_id"],
                tag_id=raw["tag_id"],
                reason=raw["reason"],
                actor=raw["actor"],
                already_revoked=bool(raw["already_revoked"]),
                gallery_rows_demoted=int(raw["gallery_rows_demoted"]),
                attested_faces_revoked=raw.get("attested_faces_revoked"),
                already_promoted_faces=[
                    PromotedAttestationOut.model_validate(item)
                    for item in (raw.get("already_promoted_faces") or [])
                ],
                inferred_ranges_compensated=int(raw["inferred_ranges_compensated"]),
                hold=WearableTeachingHoldOut.model_validate(raw["hold"]),
            )
        except (KeyError, TypeError, ValidationError) as exc:
            logger.warning("wearable_revoke_contract_violation", error=type(exc).__name__)
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "wearable_revocation.upstream_contract",
                    "message": "malformed wearable revoke envelope",
                },
            ) from exc

    async def resume_tag_teaching(
        self, tag_id: str, *, actor: str
    ) -> WearableResumeTeachingResponse:
        client = self._require_orchestrator()
        try:
            raw = await client.resume_wearable_tag_teaching(tag_id, actor=actor)
        except UpstreamError as exc:
            raise _raise_upstream(exc) from exc
        try:
            hold_raw = raw.get("hold")
            return WearableResumeTeachingResponse(
                tag_id=str(raw["tag_id"]),
                resumed=bool(raw["resumed"]),
                hold=WearableTeachingHoldOut.model_validate(hold_raw) if hold_raw else None,
            )
        except (KeyError, TypeError, ValidationError) as exc:
            logger.warning("wearable_resume_contract_violation", error=type(exc).__name__)
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "wearable_revocation.upstream_contract",
                    "message": "malformed wearable resume envelope",
                },
            ) from exc
