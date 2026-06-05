<template>
  <g>
    <path
      :d="inkPath"
      :fill="resolvedFill"
      :stroke="inkStroke"
      stroke-width="1.5"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
    <text v-if="label" v-bind="labelAttrs" :x="cx" :y="cy">{{ label }}</text>
  </g>
</template>

<script setup>
import { computed } from "vue";
import { useRoughSketch } from "@/composables/useRoughSketch.js";
import { MAP_LABEL } from "@/composables/useAnnotationStyle.js";
import { ccToken } from "@/composables/useChartTheme.js";

const props = defineProps({
  points: { type: Array, required: true },
  canvasW: { type: Number, required: true },
  canvasH: { type: Number, required: true },
  seedKey: { type: String, default: "" },
  label: { type: String, default: "" },
  fill: { type: String, default: null },
});

const { actions } = useRoughSketch();

const seed = computed(() => actions.seedFrom(props.seedKey || "polygon"));

const scaledPts = computed(() =>
  props.points.map(([x, y]) => [x * props.canvasW, y * props.canvasH])
);

const inkPath = computed(() => actions.path(scaledPts.value, { seed: seed.value }));

const inkStroke = computed(() => ccToken("--cc-annotation-ink") || "#2a1d0e");

const resolvedFill = computed(
  () => props.fill ?? ccToken("--cc-room-fill") ?? "rgba(91,58,26,0.10)"
);

const cx = computed(() => {
  const pts = scaledPts.value;
  return pts.length ? pts.reduce((s, [x]) => s + x, 0) / pts.length : 0;
});

const cy = computed(() => {
  const pts = scaledPts.value;
  return pts.length ? pts.reduce((s, [, y]) => s + y, 0) / pts.length : 0;
});

const labelAttrs = computed(() => MAP_LABEL.attrs());
</script>
