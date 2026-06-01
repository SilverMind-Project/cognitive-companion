<template>
  <g
    class="ph-marker"
    :class="{ 'ph-coasting': ph.state === 'coasting' }"
    :opacity="ph.state === 'coasting' ? 0.5 : 1"
    :data-testid="`ph-marker-${ph.ph_id}`"
    @click="$emit('click', ph)"
  >
    <!-- Trail polyline (shown on hover via parent) -->
    <polyline
      v-if="showTrail && trailPoints.length > 1"
      :points="trailPoints.join(' ')"
      :stroke="color"
      stroke-width="2"
      fill="none"
      opacity="0.4"
      stroke-linecap="round"
    />

    <!-- Outer ring -->
    <circle
      :cx="x"
      :cy="y"
      :r="M.outerR"
      :fill="color"
      fill-opacity="0.20"
      :stroke="color"
      stroke-width="2"
      :stroke-dasharray="ph.state === 'coasting' ? '6 4' : 'none'"
    />

    <!-- Inner dot -->
    <circle
      :cx="x"
      :cy="y"
      :r="M.innerR"
      :fill="color"
      stroke="#fff"
      stroke-width="2.5"
    />

    <!-- Posture badge -->
    <text
      :x="x"
      :y="y + 5"
      text-anchor="middle"
      :font-size="M.postureSize"
      fill="white"
      font-weight="bold"
    >
      {{ postureSymbol }}
    </text>

    <!-- Label: dark text on white halo (floor-plan / architectural drawing standard) -->
    <text
      v-bind="labelAttrs"
      :x="x + 22"
      :y="y - 13"
      :font-size="M.labelSize"
      font-weight="500"
      class="ph-marker-label"
    >
      {{ label }}
    </text>
  </g>
</template>

<script>
import { computed } from "vue";
import { MAP_LABEL, MARKER } from "@/composables/useAnnotationStyle.js";

export default {
  name: "PHMarker",
  props: {
    ph: { type: Object, required: true },
    x: { type: Number, default: 0 },
    y: { type: Number, default: 0 },
    color: { type: String, default: "#888" },
    showTrail: { type: Boolean, default: false },
    trailPoints: { type: Array, default: () => [] },
  },
  emits: ["click"],

  setup(props) {
    const label = computed(() => {
      if (props.ph.identity_display_name) return props.ph.identity_display_name;
      if (props.ph.identity_id) return props.ph.identity_id;
      return (props.ph.ph_id || "").slice(0, 8);
    });

    const postureSymbol = computed(() => {
      switch (props.ph.posture) {
        case "standing": return "S";
        case "sitting": return "s";
        case "lying": return "—";
        case "walking": return "W";
        default: return "";
      }
    });

    return { label, postureSymbol, M: MARKER, labelAttrs: MAP_LABEL.attrs() };
  },
};
</script>

<style scoped>
.ph-marker { cursor: pointer; }
.ph-marker-label { pointer-events: none; }
</style>
