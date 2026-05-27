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
      r="12"
      :fill="color"
      fill-opacity="0.18"
      :stroke="color"
      stroke-width="1.5"
      :stroke-dasharray="ph.state === 'coasting' ? '5 3' : 'none'"
    />

    <!-- Inner dot -->
    <circle
      :cx="x"
      :cy="y"
      r="6"
      :fill="color"
      stroke="#fff"
      stroke-width="2"
    />

    <!-- Posture badge -->
    <text
      :x="x"
      :y="y + 4"
      text-anchor="middle"
      font-size="9"
      fill="white"
      font-weight="bold"
    >
      {{ postureSymbol }}
    </text>

    <!-- Label -->
    <text
      :x="x + 14"
      :y="y - 10"
      :fill="color"
      font-size="12"
      font-weight="bold"
      class="ph-marker-label"
    >
      {{ label }}
    </text>
  </g>
</template>

<script>
import { computed } from "vue";

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

    return { label, postureSymbol };
  },
};
</script>

<style scoped>
.ph-marker { cursor: pointer; }
.ph-marker-label { pointer-events: none; }
</style>
