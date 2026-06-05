<template>
  <g>
    <rect
      v-for="bin in bins"
      :key="bin.key"
      :x="bin.canvasX"
      :y="bin.canvasY"
      :width="bin.canvasSize"
      :height="bin.canvasSize"
      class="heatmap-bin"
      :opacity="bin.opacity"
    />
    <text
      v-if="!loading && !bins.length"
      x="50%"
      y="50%"
      text-anchor="middle"
      class="layer-empty-text"
      :font-size="emptyFontSize"
    >
      {{ error || 'Select a person and date range, then click Generate.' }}
    </text>
  </g>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  bins:    { type: Array,   required: true },
  loading: { type: Boolean, default: false },
  error:   { type: String,  default: null },
  canvasH: { type: Number,  required: true },
});

const emptyFontSize = computed(() => Math.round(props.canvasH * 0.025));
</script>

<style scoped>
/* Fill reads --cc-warning token; M2 parchment overrides this with an ink ramp. */
.heatmap-bin {
  fill: var(--cc-warning);
}
.layer-empty-text {
  fill: var(--cc-text-3);
}
</style>
