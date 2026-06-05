<!--
  MaraudersAmbientLayer — DECORATIVE ONLY. An invisible, magical four-legged
  creature walks slowly across the floor plan; its paws stamp prints one at a
  time in a walking gait, and each print stays on the floor and fades behind it.

  IT CARRIES NO TRACKING MEANING. The paws are NOT derived from any real person
  and must never be read as presence data. They are unmistakably decorative:
  a distinct paw glyph (never the human footstep), no name label, very low
  opacity, small, and following a synthetic looping path no person walks.

  Animation: positions are derived from the `nowMs` clock prop (the same rAF
  fade clock the real footprints use — no second requestAnimationFrame driver).
  Each gait beat (STEP_INTERVAL_MS) one paw is stamped at that foot's ground
  position; the most recent few stay visible, fading by age, so prints appear
  sequentially in gait order. Under reduced motion the clock is frozen (and this
  component also pins to a fixed time) so the paws render static.
  One-flag disable: set MARAUDERS_AMBIENT = false to remove this entirely
  without touching the real-data rendering path.
-->
<template>
  <g v-if="MARAUDERS_AMBIENT" class="ambient-layer" aria-hidden="true">
    <g
      v-for="paw in paws"
      :key="paw.key"
      class="ambient-paw"
      :transform="`translate(${paw.x},${paw.y}) rotate(${paw.angleDeg}) scale(${PAW_SCALE})`"
      :opacity="paw.opacity"
    >
      <!-- Paw-print: oval pad with three toe dots ahead of it (toes point along
           local -y, i.e. the direction of travel after the +90 rotation). -->
      <ellipse cx="0" cy="1" rx="2.8" ry="2" :fill="inkColor" />
      <circle cx="-2.5" cy="-2.2" r="1.1" :fill="inkColor" />
      <circle cx="0"    cy="-3.2" r="1.1" :fill="inkColor" />
      <circle cx="2.5"  cy="-2.2" r="1.1" :fill="inkColor" />
    </g>
  </g>
</template>

<script>
// Re-export so tests can do: import { MARAUDERS_AMBIENT } from ".../MaraudersAmbientLayer.vue"
export { MARAUDERS_AMBIENT } from "@/constants/maraudersConfig.js";
</script>

<script setup>
import { computed } from "vue";
import { ccToken } from "@/composables/useChartTheme.js";
import { MARAUDERS_AMBIENT } from "@/constants/maraudersConfig.js";

const PERIOD_MS = 48000;        // slow loop of the wandering body path
const STEP_INTERVAL_MS = 750;   // time between individual paw stamps (gait beat)
const VISIBLE = 4;              // prints kept on the floor — "four at a time"
const FADE_MS = STEP_INTERVAL_MS * VISIBLE; // oldest fades as the newest lands
const MAX_OPACITY = 0.22;       // faint — clearly decorative, never a "presence"
const PAW_SCALE = 1.8;          // small paw glyph
const BODY_LEN = 15;            // half front-to-back foot spread (canvas px)
const BODY_WID = 9;             // half left-to-right foot spread (canvas px)
const MARGIN = 0.16;            // keep the body path inside this canvas inset
const STATIC_NOW_MS = 100000;   // fixed clock value used under reduced motion

// Diagonal walking gait order: front-left, back-right, front-right, back-left.
// Each entry is [forward sign (+front/-back), side sign (-left/+right)].
const GAIT = [
  [1, -1],
  [-1, 1],
  [1, 1],
  [-1, -1],
];

const props = defineProps({
  canvasW:       { type: Number, required: true },
  canvasH:       { type: Number, required: true },
  nowMs:         { type: Number, default: 0 },
  reducedMotion: { type: Boolean, default: false },
});

// Reads the theme token directly; ccMarauders defines --cc-annotation-ink.
const inkColor = computed(() => ccToken("--cc-annotation-ink"));

// Figure-8 (Lissajous 1:2) wandering body path, in canvas units, plus tangent.
function pathPoint(phi, w, h) {
  const ax = (0.5 - MARGIN) * w;
  const ay = (0.5 - MARGIN) * h;
  const a = 2 * Math.PI * phi;
  return {
    x: 0.5 * w + ax * Math.sin(a),
    y: 0.5 * h + ay * Math.sin(2 * a),
    dx: ax * Math.cos(a),          // d/dphi — used only for the heading angle
    dy: ay * 2 * Math.cos(2 * a),
  };
}

const paws = computed(() => {
  const w = props.canvasW;
  const h = props.canvasH;
  if (!w || !h) return [];

  const now = props.reducedMotion ? STATIC_NOW_MS : props.nowMs;
  const currentStep = Math.floor(now / STEP_INTERVAL_MS);

  const out = [];
  for (let k = 0; k < VISIBLE; k++) {
    const stepN = currentStep - k;
    if (stepN < 0) continue;

    const placeTime = stepN * STEP_INTERVAL_MS;
    const age = now - placeTime; // >= 0
    if (age >= FADE_MS) continue;

    // The body is where it was when this paw stamped down (the print then stays
    // put while the creature walks on).
    const bodyPhi = (((placeTime / PERIOD_MS) % 1) + 1) % 1;
    const pt = pathPoint(bodyPhi, w, h);
    const heading = Math.atan2(pt.dy, pt.dx);

    const fwd = { x: Math.cos(heading), y: Math.sin(heading) };
    const side = { x: -Math.sin(heading), y: Math.cos(heading) }; // "right"
    const [fwdSign, sideSign] = GAIT[((stepN % 4) + 4) % 4];

    const x = pt.x + fwdSign * BODY_LEN * fwd.x + sideSign * BODY_WID * side.x;
    const y = pt.y + fwdSign * BODY_LEN * fwd.y + sideSign * BODY_WID * side.y;

    // Paw toes point along local -y, so align with heading via +90deg.
    const angleDeg = (heading * 180) / Math.PI + 90;

    // Newest stamp brightest; trailing prints fade out behind the creature.
    const opacity = MAX_OPACITY * (1 - age / FADE_MS);

    out.push({ key: `paw-${stepN}`, x, y, angleDeg, opacity });
  }
  return out;
});
</script>

<style scoped>
.ambient-layer { pointer-events: none; }
</style>
