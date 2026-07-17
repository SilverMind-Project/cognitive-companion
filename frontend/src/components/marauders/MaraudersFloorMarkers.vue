<template>
  <g>
    <!-- The shared asset-backed glyph is mirrored for alternating feet.
         Per-step transforms keep the immutable silhouette cheap to render. -->
    <MaraudersFootprintGlyph
      v-for="step in footsteps"
      :key="`${step.phId}-${step.seed}`"
      class="mm-footstep"
      :fill="inkColor"
      :opacity="step.opacity"
      :transform="`translate(${step.x},${step.y}) rotate(${step.angleDeg})`"
      :mirrored="step.foot === 'R'"
    />

    <!-- Head marker per person: a hand-drawn (rough ink) ring around a muted
         identity dot, with an ink label — parchment-toned, not a bright
         concentric-circle marker. The identity color is kept (low opacity) so
         "who is where" stays legible without clashing with the parchment. -->
    <g
      v-for="m in markers"
      :key="m.ph.ph_id || m.ph.identity_id"
      class="mm-head"
      data-testid="mm-head"
      :opacity="m.ph.state === 'coasting' ? 0.55 : 1"
      @click="$emit('phClick', m.ph)"
    >
      <circle :cx="m.x" :cy="m.y" :r="MARKER.innerR" :fill="m.color" fill-opacity="0.5" />
      <path
        :d="headRing(m.ph)"
        :transform="`translate(${m.x},${m.y})`"
        fill="none"
        :stroke="inkColor"
        stroke-width="1.4"
        stroke-linejoin="round"
        stroke-linecap="round"
      />
      <text
        v-bind="labelAttrs"
        :x="m.x + MARKER.innerR + 8"
        :y="m.y - MARKER.innerR + 2"
        :font-size="MARKER.labelSize"
        font-weight="500"
        class="mm-head-label"
      >
        {{ headLabel(m.ph) }}
      </text>
    </g>

    <!-- Empty state -->
    <text
      v-if="phCount === 0"
      x="50%"
      y="50%"
      text-anchor="middle"
      class="layer-empty-text"
      :font-size="emptyFontSize"
    >
      No active tracks. Waiting for live data&hellip;
    </text>
  </g>
</template>

<script setup>
import { computed } from "vue";
import { useFootprintTrail } from "@/composables/useFootprintTrail.js";
import { useRoughSketch } from "@/composables/useRoughSketch.js";
import { ccToken } from "@/composables/useChartTheme.js";
import { MARKER, MAP_LABEL } from "@/composables/useAnnotationStyle.js";
import MaraudersFootprintGlyph from "@/components/marauders/MaraudersFootprintGlyph.vue";

const props = defineProps({
  markers: { type: Array, required: true },
  phCount: { type: Number, required: true },
  canvasH: { type: Number, required: true },
  trails: { type: Object, required: true }, // reactive Map from trailBuffers
  nowMs: { type: Number, required: true },
  fpWidth: { type: Number, default: null },
  fpHeight: { type: Number, default: null },
  fpMpp: { type: Number, default: null },
  canvasW: { type: Number, default: null },
  reducedMotion: { type: Boolean, default: false },
});

defineEmits(["phClick"]);

const { actions: ftActions } = useFootprintTrail();
const {
  actions: { path: roughPath, seedFrom },
} = useRoughSketch();

// Build color map from markers so we only show footsteps for calibrated PHs.
const colorsByPh = computed(() => {
  const m = new Map();
  for (const marker of props.markers) {
    const id = marker.ph.ph_id || marker.ph.identity_id;
    if (id) m.set(id, marker.color);
  }
  return m;
});

const footsteps = computed(() => {
  const canvas = {
    fpWidth: props.fpWidth,
    fpHeight: props.fpHeight,
    fpMpp: props.fpMpp,
    canvasW: props.canvasW,
    canvasH: props.canvasH,
  };
  return ftActions.computeFootsteps(props.trails, colorsByPh.value, props.nowMs, canvas, {
    reducedMotion: props.reducedMotion,
  });
});

// Sepia ink for footstep edges and the hand-drawn head ring (parchment theme).
const inkColor = computed(() => ccToken("--cc-annotation-ink"));

// Hand-drawn ink ring for the head marker. Circle approximated as a polygon and
// drawn through rough.js; a stable per-PH seed keeps it from boiling per frame.
const _ringPts = (() => {
  const r = MARKER.innerR + 1.5;
  const pts = [];
  for (let i = 0; i < 18; i++) {
    const t = (i / 18) * Math.PI * 2;
    pts.push([r * Math.cos(t), r * Math.sin(t)]);
  }
  return pts;
})();

function headRing(ph) {
  const seed = seedFrom(`head-${ph.ph_id || ph.identity_id || ""}`);
  return roughPath(_ringPts, { seed, roughness: 0.9, bowing: 1.2 });
}

const labelAttrs = computed(() => MAP_LABEL.attrs());

function headLabel(ph) {
  return ph.identity_display_name || ph.identity_id || (ph.ph_id || "").slice(0, 8);
}

const emptyFontSize = computed(() => Math.round(props.canvasH * 0.025));
</script>

<style scoped>
.mm-head {
  cursor: pointer;
}
.mm-head-label {
  pointer-events: none;
}
.layer-empty-text {
  fill: var(--cc-text-3);
}
</style>
