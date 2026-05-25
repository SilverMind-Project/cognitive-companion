"""Infer camera adjacency edges and overlap groups from visibility polygons.

Uses Shapely for polygon intersection.  All input polygons are in normalised
[0, 1] floor-plan coordinates.

Definitions:
- **Overlap group**: two cameras whose polygons have intersection-over-union (IoU)
  above OVERLAP_IOU_THRESHOLD share a physical viewing zone.  An operator-facing
  overlap edge has transit bounds of 0-2 s and ``overlap=True``.
- **Adjacent (non-overlapping)**: two cameras whose polygon boundaries are within
  ADJACENCY_GAP_NORM of each other (but IoU below overlap threshold).  Assigned
  transit bounds of 2-15 s and ``overlap=False``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Threshold above which two cameras are considered to have overlapping coverage.
OVERLAP_IOU_THRESHOLD: float = 0.05
# Max normalised centroid distance to qualify as adjacent (not overlapping).
ADJACENCY_GAP_NORM: float = 0.35
# Default transit bounds for detected pairs.
OVERLAP_TRANSIT_MIN_S: float = 0.0
OVERLAP_TRANSIT_MAX_S: float = 2.0
ADJACENT_TRANSIT_MIN_S: float = 2.0
ADJACENT_TRANSIT_MAX_S: float = 15.0


@dataclass
class InferredEdge:
    from_camera: str
    to_camera: str
    min_transit_s: float
    max_transit_s: float
    overlap: bool
    iou: float


@dataclass
class InferredOverlapGroup:
    camera_ids: list[str]
    iou: float


@dataclass
class InferenceResult:
    edges: list[InferredEdge] = field(default_factory=list)
    overlap_groups: list[InferredOverlapGroup] = field(default_factory=list)
    skipped_camera_ids: list[str] = field(default_factory=list)


def infer_adjacency(
    cameras: list[dict],
) -> InferenceResult:
    """Infer adjacency from visibility polygons.

    Args:
        cameras: list of dicts with keys:
            - ``id``: camera ID string
            - ``visibility_polygon``: list[list[float]] | None - normalised [0,1] coords
            Any camera without a polygon is skipped and reported in ``skipped_camera_ids``.

    Returns:
        ``InferenceResult`` with edges, overlap groups, and skipped camera IDs.
    """
    from shapely.geometry import Polygon

    result = InferenceResult()
    polys: dict[str, Polygon] = {}

    for cam in cameras:
        cid = cam["id"]
        raw: list[list[float]] | None = cam.get("visibility_polygon")
        if not raw or len(raw) < 3:
            result.skipped_camera_ids.append(cid)
            continue
        try:
            poly = Polygon([(pt[0], pt[1]) for pt in raw])
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_empty:
                result.skipped_camera_ids.append(cid)
                continue
            polys[cid] = poly
        except Exception:
            result.skipped_camera_ids.append(cid)

    ids = sorted(polys.keys())
    overlap_pairs: set[frozenset[str]] = set()

    for i, id_a in enumerate(ids):
        for id_b in ids[i + 1 :]:
            pa = polys[id_a]
            pb = polys[id_b]

            try:
                inter_area = pa.intersection(pb).area
                union_area = pa.union(pb).area
                iou = inter_area / union_area if union_area > 0 else 0.0
            except Exception:
                iou = 0.0

            if iou >= OVERLAP_IOU_THRESHOLD:
                overlap_pairs.add(frozenset({id_a, id_b}))
                result.edges.append(
                    InferredEdge(
                        from_camera=id_a,
                        to_camera=id_b,
                        min_transit_s=OVERLAP_TRANSIT_MIN_S,
                        max_transit_s=OVERLAP_TRANSIT_MAX_S,
                        overlap=True,
                        iou=round(iou, 4),
                    )
                )
                result.edges.append(
                    InferredEdge(
                        from_camera=id_b,
                        to_camera=id_a,
                        min_transit_s=OVERLAP_TRANSIT_MIN_S,
                        max_transit_s=OVERLAP_TRANSIT_MAX_S,
                        overlap=True,
                        iou=round(iou, 4),
                    )
                )
                continue

            ca = pa.centroid
            cb = pb.centroid
            dist = ((ca.x - cb.x) ** 2 + (ca.y - cb.y) ** 2) ** 0.5
            if dist <= ADJACENCY_GAP_NORM:
                result.edges.append(
                    InferredEdge(
                        from_camera=id_a,
                        to_camera=id_b,
                        min_transit_s=ADJACENT_TRANSIT_MIN_S,
                        max_transit_s=ADJACENT_TRANSIT_MAX_S,
                        overlap=False,
                        iou=round(iou, 4),
                    )
                )
                result.edges.append(
                    InferredEdge(
                        from_camera=id_b,
                        to_camera=id_a,
                        min_transit_s=ADJACENT_TRANSIT_MIN_S,
                        max_transit_s=ADJACENT_TRANSIT_MAX_S,
                        overlap=False,
                        iou=round(iou, 4),
                    )
                )

    result.overlap_groups = _build_overlap_groups(overlap_pairs, polys)

    return result


def _build_overlap_groups(
    pairs: set[frozenset[str]],
    polys: dict[str, object],
) -> list[InferredOverlapGroup]:
    """Union-find clustering for overlap groups."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        p = parent.get(x)
        if p is None:
            return x
        root = find(p)
        parent[x] = root
        return root

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for pair in pairs:
        a, b = tuple(pair)
        union(a, b)

    clusters: dict[str, list[str]] = {}
    for cid in {c for pair in pairs for c in pair}:
        root = find(cid)
        clusters.setdefault(root, []).append(cid)

    groups = []
    for members in clusters.values():
        if len(members) < 2:
            continue
        inter_areas = []
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                try:
                    ia = polys[members[i]].intersection(polys[members[j]]).area
                    ua = polys[members[i]].union(polys[members[j]]).area
                    inter_areas.append(ia / ua if ua > 0 else 0.0)
                except Exception:
                    pass
        mean_iou = sum(inter_areas) / len(inter_areas) if inter_areas else 0.0
        groups.append(
            InferredOverlapGroup(
                camera_ids=sorted(members),
                iou=round(mean_iou, 4),
            )
        )

    return groups
