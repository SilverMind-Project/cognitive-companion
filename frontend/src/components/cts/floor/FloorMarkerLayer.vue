<template>
  <g>
    <PHMarker
      v-for="m in markers"
      :key="m.ph.ph_id || m.ph.identity_id"
      :ph="m.ph"
      :x="m.x"
      :y="m.y"
      :color="m.color"
      @click="$emit('phClick', m.ph)"
    />
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
import PHMarker from "./PHMarker.vue";

const props = defineProps({
  markers:  { type: Array,  required: true },
  phCount:  { type: Number, required: true },
  canvasH:  { type: Number, required: true },
});

defineEmits(["phClick"]);

const emptyFontSize = computed(() => Math.round(props.canvasH * 0.025));
</script>

<style scoped>
.layer-empty-text {
  fill: var(--cc-text-3);
}
</style>
