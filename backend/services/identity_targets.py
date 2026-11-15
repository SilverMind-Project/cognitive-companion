"""The household members an operator may say a face, body, or track belongs to.

Every identity decision in the admin UI picks from this one list: track and keyframe
corrections, ReID relabels, visitor attribution, and face calibration labels. The set of
identities an operator may assign is the active household roster, NOT the ReID gallery. The gallery can be empty, stale, or polluted; it must never
gate who a person can be corrected to. Gallery/review counts are attached only as
non-authoritative decoration, and an upstream gallery failure is surfaced
explicitly rather than hidden or allowed to empty the list.

This is the single service function behind the BFF endpoint (and any future MCP
tool), per the one-service-layer rule.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.exceptions import ValidationError
from backend.core.logging import get_logger
from backend.integrations.person_id_client import PersonIDClient, PersonIDUpstreamError
from backend.models.person import HouseholdMember

logger = get_logger(__name__)


@dataclass(frozen=True)
class IdentityTarget:
    identity_id: str
    display_name: str
    is_active: bool
    is_guest: bool
    # Non-authoritative gallery decoration; None when gallery is unavailable.
    gallery_entry_count: int | None = None
    gallery_verified_count: int | None = None
    # Has enrolled face photos in person identification; None when it could not be read.
    face_enrolled: bool | None = None


@dataclass
class IdentityTargetsResult:
    targets: list[IdentityTarget] = field(default_factory=list)
    # True when gallery decoration was fetched; False when the upstream errored.
    gallery_available: bool = True
    gallery_error: str | None = None
    # False when person identification could not be read (face_enrolled is then None).
    enrollment_available: bool = True


async def list_identity_targets(
    db: Session,
    orchestrator_client: object | None,
    person_id_client: PersonIDClient | None = None,
) -> IdentityTargetsResult:
    """Return active household members, decorated with optional gallery and enrollment state.

    Without a person identification client, ``face_enrolled`` stays None and
    ``enrollment_available`` reports False; members are never dropped for a missing decoration.
    """
    members = (
        db.execute(
            select(HouseholdMember)
            .where(HouseholdMember.is_active.is_(True))
            .order_by(HouseholdMember.name.asc())
        )
        .scalars()
        .all()
    )

    # Best-effort gallery decoration. A failure here must not drop targets.
    gallery_by_id: dict[str, dict] = {}
    gallery_available = True
    gallery_error: str | None = None
    if orchestrator_client is not None:
        try:
            identities = await orchestrator_client.get_identities(  # type: ignore[attr-defined]
                active_only=True
            )
            for ident in identities:
                ident_id = ident.get("identity_id") or ident.get("id")
                if ident_id:
                    gallery_by_id[str(ident_id)] = ident
        except Exception as exc:  # noqa: BLE001 - decoration is best-effort
            gallery_available = False
            gallery_error = str(exc)
            logger.warning("correction_targets_gallery_unavailable", error=str(exc))

    enrolled: set[str] | None = None
    if person_id_client is not None:
        try:
            enrolled = {
                m.person_id for m in await person_id_client.list_members() if m.embedding_count > 0
            }
        except PersonIDUpstreamError as exc:
            logger.warning("identity_targets_enrollment_unavailable", status=exc.status)

    targets: list[IdentityTarget] = []
    for m in members:
        decoration = gallery_by_id.get(m.id, {})
        targets.append(
            IdentityTarget(
                identity_id=m.id,
                display_name=m.name,
                is_active=m.is_active,
                is_guest=m.is_guest,
                gallery_entry_count=decoration.get("gallery_entry_count")
                if gallery_available
                else None,
                gallery_verified_count=decoration.get("gallery_verified_count")
                if gallery_available
                else None,
                face_enrolled=None if enrolled is None else m.id in enrolled,
            )
        )

    return IdentityTargetsResult(
        targets=targets,
        gallery_available=gallery_available,
        gallery_error=gallery_error,
        enrollment_available=enrolled is not None,
    )


class IdentityTargetsService:
    """The one target list behind every identity decision in the admin UI.

    Both upstream clients are optional decoration: with CTS disabled there are no gallery counts,
    and with person identification down ``face_enrolled`` is unknown, but the household members
    are always returned.
    """

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        person_id: PersonIDClient | None,
        orchestrator: object | None,
    ) -> None:
        self._session_factory = session_factory
        self._person_id = person_id
        self._orchestrator = orchestrator

    async def list_targets(self) -> IdentityTargetsResult:
        db = self._session_factory()
        try:
            return await list_identity_targets(db, self._orchestrator, self._person_id)
        finally:
            db.close()

    async def require_enrolled_member(self, identity_id: str) -> IdentityTarget:
        """The active member ``identity_id`` with enrolled faces, or a ValidationError.

        Attributing faces to someone needs their enrolled face to compare against; a guest
        without photos or an inactive member is not a valid target.
        """
        result = await self.list_targets()
        target = next((t for t in result.targets if t.identity_id == identity_id), None)
        if target is None:
            raise ValidationError(f"{identity_id} is not an active household member")
        if target.face_enrolled is False:
            raise ValidationError(f"{identity_id} has no enrolled face photos")
        return target
