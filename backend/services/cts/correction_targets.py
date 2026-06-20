"""Authoritative correction-target list for the identity correction UI (M06).

The set of identities an operator may assign is the active household roster, NOT
the ReID gallery. The gallery can be empty, stale, or polluted; it must never
gate who a person can be corrected to. Gallery/review counts are attached only as
non-authoritative decoration, and an upstream gallery failure is surfaced
explicitly rather than hidden or allowed to empty the list.

This is the single service function behind the BFF endpoint (and any future MCP
tool), per the one-service-layer rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.models.person import HouseholdMember

logger = get_logger(__name__)


@dataclass(frozen=True)
class CorrectionTarget:
    identity_id: str
    display_name: str
    is_active: bool
    is_guest: bool
    # Non-authoritative gallery decoration; None when gallery is unavailable.
    gallery_entry_count: int | None = None
    gallery_verified_count: int | None = None


@dataclass
class CorrectionTargetsResult:
    targets: list[CorrectionTarget] = field(default_factory=list)
    # True when gallery decoration was fetched; False when the upstream errored.
    gallery_available: bool = True
    gallery_error: str | None = None


async def list_correction_targets(
    db: Session,
    orchestrator_client: object | None,
) -> CorrectionTargetsResult:
    """Return active household members, decorated with optional gallery counts."""
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

    targets: list[CorrectionTarget] = []
    for m in members:
        decoration = gallery_by_id.get(m.id, {})
        targets.append(
            CorrectionTarget(
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
            )
        )

    return CorrectionTargetsResult(
        targets=targets,
        gallery_available=gallery_available,
        gallery_error=gallery_error,
    )
