/**
 * Canvas annotation style — shared across CTS spatial renderers.
 *
 * Three SVG surfaces consume these helpers; each operates in a different
 * coordinate space, so raw numbers differ but visual output is consistent:
 *
 *   CTSFloorPlanView (PHMarker)    viewBox = floor-plan pixel dims (~1200–2000 px)
 *   CTSCalibrationView             viewBox = camera natural resolution (~1920×1080)
 *   CTSLiveView (bbox overlays)    viewBox = camera natural resolution, scaled by layout
 *
 * All colors here must be legible against photographic / map backgrounds,
 * not UI surfaces, so they are theme-invariant.
 */

import { ccToken } from "./useChartTheme.js";

// ---------------------------------------------------------------------------
// Label legibility — two contexts, two standards (industry map annotation):
//
// Camera feeds (photographic, typically dark or mixed):
//   HALO — white text over dark semi-opaque stroke
//   Used by: CTSLiveView bbox overlay, CTSCalibrationView point labels
//
// Floor-plan maps (architectural drawings, typically light/white):
//   MAP_LABEL — dark slate text over white stroke
//   Used by: PHMarker name labels, floor plan room labels
//
// Both follow the cartographic standard: font-weight 500, paint-order stroke
// so the halo is painted before (behind) the text fill, stroke-width ~15% of
// font-size for thin legible separation without distorting letter shapes.
//
// strokeWidth guidance:
//   2   for display-px viewBox  (floor plan, polygon editor — font ≈ 12-14 px)
//   8   for camera-resolution viewBox  (calibration — font ≈ 48 SVG units)
//   Math.max(2, Math.round(fontSize * 0.15)) for dynamic scaling (live overlay)
// ---------------------------------------------------------------------------

// Camera / video feed context: white text fill with dark halo.
// For :style bindings (camelCase), access .color and .strokeLinejoin separately.
// .color is a getter so it reads the CSS token at call time, enabling parchment re-skin.
export const HALO = Object.freeze({
  get color() {
    return ccToken("--cc-annotation-halo") || "rgba(0,0,0,0.70)";
  },
  attrs(strokeWidth = 2) {
    return {
      "paint-order": "stroke",
      stroke: this.color,
      "stroke-width": strokeWidth,
      "stroke-linejoin": "round",
    };
  },
});

// Floor-plan map context: dark text with white halo.
// The dot/marker already carries the identity color; the label just needs
// to be readable on an architectural drawing background.
// .fill and .haloColor are getters so they read CSS tokens at call time.
export const MAP_LABEL = Object.freeze({
  get fill() {
    return ccToken("--cc-annotation-ink") || "#1e293b";
  },
  get haloColor() {
    return ccToken("--cc-annotation-halo-light") || "rgba(255,255,255,0.92)";
  },
  attrs(strokeWidth = 2) {
    return {
      fill: this.fill,
      "paint-order": "stroke",
      stroke: this.haloColor,
      "stroke-width": strokeWidth,
      "stroke-linejoin": "round",
    };
  },
});

// ---------------------------------------------------------------------------
// Quality colors — homography residual (metres) → semantic theme token.
// ---------------------------------------------------------------------------
// Thresholds match the UX copy in CTSCalibrationView tips panel:
//   < 0.05 m  excellent   → success
//   < 0.15 m  acceptable  → warning
//   ≥ 0.15 m  poor        → error
export function qualityColor(residualM) {
  if (residualM < 0.05) return ccToken("--cc-success");
  if (residualM < 0.15) return ccToken("--cc-warning");
  return ccToken("--cc-error");
}

// ---------------------------------------------------------------------------
// PHMarker geometry — floor-plan SVG pixel space.
// ---------------------------------------------------------------------------
// These are in viewBox units. A typical 1200 px floor plan is displayed at
// ~900 px, giving a ~0.75 display-px-per-SVG-unit ratio.
// outerR=18 → ~13.5 display px radius; innerR=9 → ~6.75 display px radius.
export const MARKER = Object.freeze({
  outerR: 18,
  innerR: 9,
  labelSize: 14, // SVG font-size for identity label
  postureSize: 11, // SVG font-size for posture badge (inside inner dot)
});

// ---------------------------------------------------------------------------
// Posture colors — semantic mapping used by live bbox overlay and PHMarker.
// Reads CSS tokens at call time so M2 parchment re-skin can override them.
// Fallbacks match the prior hardcoded values so default themes are unchanged.
// ---------------------------------------------------------------------------
const POSTURE_TOKENS = {
  standing: "--cc-posture-standing",
  sitting: "--cc-posture-sitting",
  walking: "--cc-posture-walking",
  lying: "--cc-posture-lying",
};
const POSTURE_FALLBACKS = {
  standing: "#4ade80",
  sitting: "#fbbf24",
  walking: "#60a5fa",
  lying: "#c084fc",
};

export function postureColor(posture) {
  const tokenName = POSTURE_TOKENS[posture];
  if (tokenName) return ccToken(tokenName) || POSTURE_FALLBACKS[posture];
  return ccToken("--cc-text-2");
}
