/**
 * Pure geometry for bounding-box editors (crop regions, keyframe annotations).
 *
 * Framework-agnostic helpers that operate on plain canvas-space rects, so the
 * interaction logic is shared across the crop canvas and the annotation
 * canvas without coupling their rendering, coordinate model, or selection UI.
 * Pure functions -> trivially unit-testable and zero reactivity.
 *
 * A "rect" is canvas-space corners `{ x1, y1, x2, y2 }` in pixels.
 * Corners use compass names: "nw" | "ne" | "se" | "sw".
 */

/** Pointer distance (px) within which a corner handle is considered hit. */
export const HANDLE_HIT_PX = 10;

/** Clamp a value to the [0, 1] ratio range. */
export function clamp01(v) {
  return Math.max(0, Math.min(1, v));
}

/** Order a possibly-inverted rect so `x1 <= x2` and `y1 <= y2`. */
export function normalizeRect(rect) {
  return {
    x1: Math.min(rect.x1, rect.x2),
    y1: Math.min(rect.y1, rect.y2),
    x2: Math.max(rect.x1, rect.x2),
    y2: Math.max(rect.y1, rect.y2),
  };
}

/**
 * Which part of `rect` the point (px, py) hits: a corner handle
 * ("nw"|"ne"|"se"|"sw"), the interior ("move"), or null. Corners win over the
 * interior so a drag near an edge resizes rather than moves.
 */
export function hitTestRect(px, py, rect, handle = HANDLE_HIT_PX) {
  const corners = {
    nw: [rect.x1, rect.y1],
    ne: [rect.x2, rect.y1],
    se: [rect.x2, rect.y2],
    sw: [rect.x1, rect.y2],
  };
  for (const [corner, [hx, hy]] of Object.entries(corners)) {
    if (Math.abs(px - hx) <= handle && Math.abs(py - hy) <= handle) return corner;
  }
  if (px >= rect.x1 && px <= rect.x2 && py >= rect.y1 && py <= rect.y2) return "move";
  return null;
}

/**
 * Apply a drag delta (dx, dy) to a `rect` for the given corner ("nw".."se") or
 * "move". Returns a new, possibly-inverted rect (run through `normalizeRect`
 * before use). Pure: does not mutate the input.
 */
export function applyCornerDrag(rect, corner, dx, dy) {
  const r = { ...rect };
  switch (corner) {
    case "move":
      r.x1 += dx;
      r.y1 += dy;
      r.x2 += dx;
      r.y2 += dy;
      break;
    case "nw":
      r.x1 += dx;
      r.y1 += dy;
      break;
    case "ne":
      r.x2 += dx;
      r.y1 += dy;
      break;
    case "se":
      r.x2 += dx;
      r.y2 += dy;
      break;
    case "sw":
      r.x1 += dx;
      r.y2 += dy;
      break;
  }
  return r;
}
