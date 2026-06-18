"""Floor-meter geometry helpers for room zones."""

from __future__ import annotations

from shapely.geometry import Point, Polygon


def floor_meter_polygon(polygon_m: list[list[float]]) -> Polygon | None:
    """Build a floor-meter polygon, or None when fewer than three vertices exist.

    The vertices are in floor-plane METERS, the same space as
    ``location_observation.floor_x_m/floor_y_m``. This is never the normalised
    [0,1] image space of ``cts_cameras.visibility_polygon``.
    """
    if len(polygon_m) < 3:
        return None
    return Polygon(polygon_m)


def point_in_polygon(point_m: tuple[float, float], polygon_m: list[list[float]]) -> bool:
    """True if the floor-meter point lies within the floor-meter polygon.

    Both inputs are in floor-plane METERS, never the normalised [0,1] image space
    of ``cts_cameras.visibility_polygon``. See M0 D19.
    """
    polygon = floor_meter_polygon(polygon_m)
    if polygon is None:
        return False
    return polygon.covers(Point(point_m))
