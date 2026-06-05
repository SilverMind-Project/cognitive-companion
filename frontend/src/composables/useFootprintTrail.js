/**
 * useFootprintTrail — footstep placement math for MaraudersFloorMarkers.
 *
 * Pure composable: takes trail data and canvas params, returns positioned
 * footstep descriptors. No fetching, no side effects.
 *
 * The asset-backed glyph is centered at (0,0); the consumer applies a per-step
 * transform="translate(x,y) rotate(deg)" so only position, angle, foot side,
 * and opacity vary.
 */

import { reactive } from "vue";
import { useRoughSketch } from "@/composables/useRoughSketch.js";

export const FOOT_FADE_MS = 6000;
const STRIDE_M = 0.35;
const GAIT_OFFSET_M = 0.15;
const PER_PERSON_CAP = 12;
const GLOBAL_CAP = 120;
const REDUCED_MOTION_N = 5;
const REDUCED_MOTION_OPACITY = 0.65;

/**
 * computeFootsteps — pure function, no Vue reactivity inside.
 *
 * @param {Map} trailsByPh  ph_id → [{x, y, t}] in floor metres
 * @param {Map} colorsByPh  ph_id → color string
 * @param {number} nowMs    current time (performance.now() or Date.now())
 * @param {object} canvas   {fpWidth, fpHeight, fpMpp, canvasW, canvasH}
 * @param {object} opts     {reducedMotion}
 * @returns {{ phId, x, y, angleDeg, foot, opacity, seed, color }[]}
 */
function computeFootsteps(trailsByPh, colorsByPh, nowMs, canvas, opts = {}) {
  const { fpWidth, fpHeight, fpMpp, canvasW, canvasH } = canvas;
  const { reducedMotion = false } = opts;

  if (!fpMpp || !fpWidth || !fpHeight || !canvasW || !canvasH) return [];

  const { actions: { seedFrom } } = useRoughSketch();

  const totalWidthM = fpWidth * fpMpp;
  const totalHeightM = fpHeight * fpMpp;

  function mToCanvas(mx, my) {
    return { cx: (mx / totalWidthM) * canvasW, cy: (my / totalHeightM) * canvasH };
  }

  const stridePx = (STRIDE_M / totalWidthM) * canvasW;
  const gaitOffsetPx = (GAIT_OFFSET_M / totalWidthM) * canvasW;

  const all = [];

  for (const [phId, trail] of trailsByPh) {
    if (!colorsByPh.has(phId)) continue; // only calibrated PHs with a head marker
    if (trail.length < 2) continue;

    const color = colorsByPh.get(phId);

    // Convert trail points to canvas coords, keeping timestamps.
    const pts = trail.map((p) => {
      const { cx, cy } = mToCanvas(p.x, p.y);
      return { cx, cy, t: p.t };
    });

    // Build cumulative arc lengths (in canvas px).
    const arcs = [0];
    for (let i = 1; i < pts.length; i++) {
      const dx = pts[i].cx - pts[i - 1].cx;
      const dy = pts[i].cy - pts[i - 1].cy;
      arcs.push(arcs[i - 1] + Math.sqrt(dx * dx + dy * dy));
    }

    const totalLen = arcs[arcs.length - 1];
    if (totalLen < stridePx) continue;

    // Find segment index for a given arc length s.
    function segAt(s) {
      let lo = 0;
      let hi = arcs.length - 2;
      while (lo < hi) {
        const mid = (lo + hi + 1) >> 1;
        if (arcs[mid] <= s) lo = mid;
        else hi = mid - 1;
      }
      return lo;
    }

    const phSteps = [];
    let footIndex = 0;

    for (let s = 0; s <= totalLen; s += stridePx) {
      const si = segAt(s);
      const segStart = arcs[si];
      const segEnd = arcs[si + 1] ?? segStart;
      const segLen = segEnd - segStart;
      const frac = segLen > 0 ? (s - segStart) / segLen : 0;

      const cx = pts[si].cx + frac * (pts[si + 1].cx - pts[si].cx);
      const cy = pts[si].cy + frac * (pts[si + 1].cy - pts[si].cy);
      const timestamp = pts[si].t + frac * (pts[si + 1].t - pts[si].t);

      const age = nowMs - timestamp;

      const foot = footIndex % 2 === 0 ? "L" : "R";

      // Direction of travel along this segment.
      const dx = pts[si + 1].cx - pts[si].cx;
      const dy = pts[si + 1].cy - pts[si].cy;
      const angle = Math.atan2(dy, dx);
      // The glyph's forward (toe) points along local -y, so a foot oriented
      // along travel direction theta needs rotate(theta + 90deg): SVG rotate(a)
      // maps local (0,-1) to (sin a, -cos a), which equals (cos theta, sin theta)
      // exactly when a = theta + 90.
      const angleDeg = (angle * 180) / Math.PI + 90;

      // Perpendicular gait offset (left/right of travel direction).
      const perpAngle = angle + Math.PI / 2;
      const sign = foot === "L" ? -1 : 1;
      const ox = sign * gaitOffsetPx * Math.cos(perpAngle);
      const oy = sign * gaitOffsetPx * Math.sin(perpAngle);

      let opacity;
      if (reducedMotion) {
        opacity = REDUCED_MOTION_OPACITY;
      } else {
        if (age >= FOOT_FADE_MS) {
          footIndex++;
          continue;
        }
        opacity = Math.max(0, 1 - age / FOOT_FADE_MS);
      }

      const seed = seedFrom(`${phId}:${footIndex}`);

      phSteps.push({ phId, x: cx + ox, y: cy + oy, angleDeg, foot, opacity, seed, color });
      footIndex++;
    }

    // Reduced motion: keep the N newest (highest arc length = closest to head).
    const kept = reducedMotion
      ? phSteps.slice(-REDUCED_MOTION_N)
      : phSteps.slice(-PER_PERSON_CAP);
    all.push(...kept);
  }

  return all.slice(-GLOBAL_CAP);
}

export function useFootprintTrail() {
  return {
    state: reactive({}),
    actions: { computeFootsteps },
  };
}
