/**
 * Uncertainty rationale: a homography's accuracy degrades with distance from the camera.
 * A uniformly-filled polygon overstates confidence at its far edge. We render coverage
 * with a near-to-far opacity falloff anchored at the camera position, so the far edge
 * reads as "roughly here" instead of "exactly here".
 */

export const FALLOFF_OPACITY_INNER = 1.0;
export const FALLOFF_OPACITY_OUTER = 0.15;
export const FALLOFF_STOP_INNER = "40%";
export const FALLOFF_STOP_OUTER = "100%";

export function toSvgPoints(polygon, imgW, imgH) {
  if (!imgW || !imgH || !polygon) return "";
  return polygon.map(([x, y]) => `${(x * imgW).toFixed(1)},${(y * imgH).toFixed(1)}`).join(" ");
}

export function falloffStops(anchor, polygon, imgW, imgH) {
  const cx = anchor.x_norm * imgW;
  const cy = anchor.y_norm * imgH;

  let maxDistSq = 0;
  for (const [vx_norm, vy_norm] of polygon) {
    const vx = vx_norm * imgW;
    const vy = vy_norm * imgH;
    const distSq = (vx - cx) ** 2 + (vy - cy) ** 2;
    if (distSq > maxDistSq) {
      maxDistSq = distSq;
    }
  }

  // Degenerate polygon (all vertices at anchor) yields a non-zero minimum radius to avoid NaN
  const r = Math.max(Math.sqrt(maxDistSq), 0.1);

  return {
    cx,
    cy,
    r,
    stops: [
      { offset: FALLOFF_STOP_INNER, opacity: FALLOFF_OPACITY_INNER },
      { offset: FALLOFF_STOP_OUTER, opacity: FALLOFF_OPACITY_OUTER },
    ],
  };
}
