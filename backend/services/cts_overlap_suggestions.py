"""Suggest camera overlap groups from calibrated cameras' visibility polygons.

Polygons are in normalised [0, 1] floor-plan coordinates and exist only for cameras with a
homography, so suggestions cover calibrated cameras; an operator declares groups that involve
an uncalibrated camera from what they see on site. Two cameras whose floor coverage has an
intersection-over-union of at least ``OVERLAP_IOU_THRESHOLD`` see the same floor area; the
suggested groups are the connected components of those pairs. Nothing here is persisted: the
operator adopts a suggestion by creating the group.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from shapely.geometry import Polygon

from backend.core.logging import get_logger

logger = get_logger(__name__)

# Coverage IoU at or above which two cameras are suggested as sharing a view.
OVERLAP_IOU_THRESHOLD: float = 0.05


@dataclass(frozen=True)
class SuggestedOverlapGroup:
    camera_ids: list[str]
    # Mean pairwise coverage IoU of the overlapping pairs in the group.
    iou: float


@dataclass
class OverlapSuggestions:
    groups: list[SuggestedOverlapGroup] = field(default_factory=list)
    # Cameras without a usable visibility polygon (uncalibrated, or a degenerate polygon).
    skipped_camera_ids: list[str] = field(default_factory=list)


def suggest_overlap_groups(cameras: list[dict]) -> OverlapSuggestions:
    """Suggest overlap groups from each camera's ``visibility_polygon``.

    Args:
        cameras: dicts with ``id`` and ``visibility_polygon`` (``list[list[float]] | None``).

    Returns:
        Suggested groups (camera ids sorted, groups sorted by first camera id) and the cameras
        that had no usable polygon.
    """
    result = OverlapSuggestions()
    polys: dict[str, Polygon] = {}
    for cam in cameras:
        cid = cam["id"]
        raw = cam.get("visibility_polygon")
        if not raw or len(raw) < 3:
            result.skipped_camera_ids.append(cid)
            continue
        try:
            poly = Polygon([(pt[0], pt[1]) for pt in raw])
            if not poly.is_valid:
                poly = poly.buffer(0)
        except Exception:  # noqa: BLE001 - a malformed stored polygon skips that camera only
            logger.warning("cts_overlap_polygon_build_failed", camera_id=cid, exc_info=True)
            result.skipped_camera_ids.append(cid)
            continue
        if poly.is_empty:
            result.skipped_camera_ids.append(cid)
            continue
        polys[cid] = poly

    pair_iou: dict[tuple[str, str], float] = {}
    ids = sorted(polys)
    for i, id_a in enumerate(ids):
        for id_b in ids[i + 1 :]:
            union_area = polys[id_a].union(polys[id_b]).area
            iou = polys[id_a].intersection(polys[id_b]).area / union_area if union_area else 0.0
            if iou >= OVERLAP_IOU_THRESHOLD:
                pair_iou[(id_a, id_b)] = iou

    result.groups = _components(pair_iou)
    return result


def _components(pair_iou: dict[tuple[str, str], float]) -> list[SuggestedOverlapGroup]:
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in pair_iou:
        parent[find(a)] = find(b)

    members: dict[str, list[str]] = {}
    for cid in parent:
        members.setdefault(find(cid), []).append(cid)

    groups = []
    for cams in members.values():
        cams.sort()
        ious = [iou for (a, b), iou in pair_iou.items() if a in cams and b in cams]
        groups.append(SuggestedOverlapGroup(camera_ids=cams, iou=round(sum(ious) / len(ious), 4)))
    return sorted(groups, key=lambda g: g.camera_ids)
