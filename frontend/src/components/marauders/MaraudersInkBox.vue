<template>
  <path
    :d="inkPath"
    fill="none"
    :stroke="resolvedColor"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
  />
</template>

<script setup>
import { computed } from "vue";
import { useRoughSketch } from "@/composables/useRoughSketch.js";
import { ccToken } from "@/composables/useChartTheme.js";

const props = defineProps({
  x: { type: Number, required: true },
  y: { type: Number, required: true },
  w: { type: Number, required: true },
  h: { type: Number, required: true },
  seedKey: { type: String, default: "" },
  color: { type: String, default: null },
});

const { actions } = useRoughSketch();

const seed = computed(() => actions.seedFrom(props.seedKey || "box"));

const boxPts = computed(() => [
  [props.x, props.y],
  [props.x + props.w, props.y],
  [props.x + props.w, props.y + props.h],
  [props.x, props.y + props.h],
]);

const inkPath = computed(() => actions.path(boxPts.value, { seed: seed.value }));

const resolvedColor = computed(
  () => props.color ?? ccToken("--cc-annotation-ink") ?? "#2a1d0e"
);
</script>
