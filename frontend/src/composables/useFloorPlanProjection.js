/**
 * Project a single detection to floor-plan canvas coordinates.
 *
 * Returns null when projection is not safe (no calibration, no floor plan,
 * or upstream sent a zero-default floor point). Callers MUST treat null as
 * "do not render on the floor plan."
 *
 * @param {object} det - Detection payload from cts_live_frame.
 * @param {object} fp  - { width, height, mpp, canvasW, canvasH }
 * @returns {{x:number,y:number}|null}
 */
export function projectDetectionToCanvas(det, fp) {
  if (!fp.width || !fp.height || !fp.mpp) return null;
  if (!det.floor_calibrated) return null;
  if (det.floor_x == null || det.floor_y == null) return null;
  const fx = (det.floor_x / (fp.width * fp.mpp)) * fp.canvasW;
  const fy = (det.floor_y / (fp.height * fp.mpp)) * fp.canvasH;
  if (!Number.isFinite(fx) || !Number.isFinite(fy)) return null;
  return { x: fx, y: fy };
}

/**
 * Stable trail key for a detection. Prefer identity_id when committed;
 * fall back to ph_id so UNKNOWN tracks still have a stable key.
 *
 * @param {object} det - Detection payload.
 * @returns {string|null}
 */
export function trailKeyFor(det) {
  const id = (det.identity_id || "").trim();
  if (id) return `id:${id}`;
  if (det.ph_id) return `ph:${det.ph_id}`;
  return null;
}

/** Ray-casting polygon containment test. Polygon is in normalised [0,1] coords. */
export function pointInPolygon(x, y, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i];
    const [xj, yj] = poly[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

/**
 * Return the room name whose polygon contains the given canvas point,
 * or null if no room matches.
 *
 * @param {number} x - Canvas x coordinate.
 * @param {number} y - Canvas y coordinate.
 * @param {number} canvasW - Canvas width.
 * @param {number} canvasH - Canvas height.
 * @param {Array} rooms - Array of room objects with floor_polygon.
 * @returns {string|null}
 */
export function roomForCanvasPoint(x, y, canvasW, canvasH, rooms) {
  const nx = x / canvasW;
  const ny = y / canvasH;
  for (const r of rooms) {
    if (r.floor_polygon && r.floor_polygon.length >= 3 && pointInPolygon(nx, ny, r.floor_polygon)) {
      return r.name;
    }
  }
  return null;
}
