<template>
  <g class="marauders-heatmap-layer">
    <g
      v-if="stains.length"
      class="marauders-heat-stains"
      data-testid="marauders-heat-stains"
      filter="url(#marauders-heat-blur)"
    >
      <circle
        v-for="stain in stains"
        :key="stain.key"
        class="marauders-heat-stain"
        :cx="stain.cx"
        :cy="stain.cy"
        :r="stain.radius"
        :fill="stain.fill"
        :data-ramp-weight="stain.weight"
      />
    </g>

    <text
      v-if="!loading && !bins.length"
      x="50%"
      y="50%"
      text-anchor="middle"
      class="layer-empty-text"
      :font-size="emptyFontSize"
    >
      {{ error || "Select a person and date range, then click Generate." }}
    </text>

    <g
      v-if="stains.length"
      class="marauders-heat-legend"
      data-testid="marauders-heat-legend"
      aria-label="Presence intensity from faint ink to deep ink"
    >
      <text x="3%" :y="legendLabelY" class="legend-text" :font-size="legendFontSize">
        Presence
      </text>
      <rect
        x="3%"
        :y="legendRampY"
        width="18%"
        :height="legendRampHeight"
        rx="3"
        fill="url(#marauders-heat-ramp)"
      />
      <text x="3%" :y="legendValueY" class="legend-text" :font-size="legendFontSize"> Faint </text>
      <text
        x="21%"
        :y="legendValueY"
        text-anchor="end"
        class="legend-text"
        :font-size="legendFontSize"
      >
        Deep
      </text>
    </g>
  </g>
</template>

<script setup>
import { computed } from "vue";

const MIN_BIN_OPACITY = 0.2;
const STAIN_RADIUS_SCALE = 0.72;

const props = defineProps({
  bins: { type: Array, required: true },
  loading: { type: Boolean, default: false },
  error: { type: String, default: null },
  canvasH: { type: Number, required: true },
});

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function normalizedWeight(opacity) {
  const numericOpacity = Number(opacity);
  if (!Number.isFinite(numericOpacity)) return 0;
  return clamp((numericOpacity - MIN_BIN_OPACITY) / (1 - MIN_BIN_OPACITY), 0, 1);
}

function rampFill(weight) {
  const highPercent = Math.round(weight * 10000) / 100;
  const lowPercent = Math.round((100 - highPercent) * 100) / 100;
  return `color-mix(in srgb, var(--cc-heat-ink-low) ${lowPercent}%, var(--cc-heat-ink-high) ${highPercent}%)`;
}

const stains = computed(() =>
  props.bins.map((bin) => {
    const weight = normalizedWeight(bin.opacity);
    return {
      key: bin.key,
      cx: bin.canvasX + bin.canvasSize / 2,
      cy: bin.canvasY + bin.canvasSize / 2,
      radius: bin.canvasSize * STAIN_RADIUS_SCALE,
      weight,
      fill: rampFill(weight),
    };
  }),
);

const emptyFontSize = computed(() => Math.round(props.canvasH * 0.025));
const legendFontSize = computed(() => Math.max(10, Math.round(props.canvasH * 0.016)));
const legendRampHeight = computed(() => Math.max(8, Math.round(props.canvasH * 0.012)));
const legendLabelY = computed(
  () => props.canvasH - legendRampHeight.value - legendFontSize.value * 1.8,
);
const legendRampY = computed(
  () => props.canvasH - legendRampHeight.value - legendFontSize.value * 1.35,
);
const legendValueY = computed(() => props.canvasH - legendFontSize.value * 0.2);
</script>

<style scoped>
.marauders-heat-stains,
.marauders-heat-legend {
  pointer-events: none;
}

.layer-empty-text,
.legend-text {
  fill: var(--cc-text-3);
}
</style>
