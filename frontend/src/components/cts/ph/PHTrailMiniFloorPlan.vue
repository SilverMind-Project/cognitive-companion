<template>
  <div class="pa-3">
    <div class="text-caption font-weight-medium mb-2">Floor Trail</div>
    <div v-if="trail.length === 0" class="text-caption text-medium-emphasis">
      No trail data.
    </div>
    <div v-else-if="trail.length === 1" class="text-caption text-medium-emphasis">
      Single point recorded.
    </div>
    <svg
      v-else
      :width="width"
      :height="height"
      class="d-block mx-auto"
      style="overflow: visible;"
    >
      <polyline
        :points="polylinePoints"
        fill="none"
        :stroke="strokeColor"
        stroke-width="2"
        stroke-linejoin="round"
      />
    </svg>
    <div v-if="trail.length > 1" class="text-caption text-medium-emphasis mt-1">
      {{ trail.length }} points recorded.
    </div>
  </div>
</template>

<script>
import { computed } from "vue";

export default {
  name: "PHTrailMiniFloorPlan",
  props: {
    trail: { type: Array, default: () => [] },
    width: { type: Number, default: 240 },
    height: { type: Number, default: 160 },
  },
  setup(props) {
    const strokeColor = "var(--cc-primary)";

    const polylinePoints = computed(() => {
      if (props.trail.length < 2) return "";
      const xs = props.trail.map((t) => t.floor_x_m || 0);
      const ys = props.trail.map((t) => t.floor_y_m || 0);
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);
      const pad = 10;
      const scaleX =
        maxX - minX > 0 ? (props.width - pad * 2) / (maxX - minX) : 1;
      const scaleY =
        maxY - minY > 0 ? (props.height - pad * 2) / (maxY - minY) : 1;
      const scale = Math.min(scaleX, scaleY, 100);
      return props.trail
        .map((t) => {
          const sx = pad + ((t.floor_x_m || 0) - minX) * scale;
          const sy = pad + ((t.floor_y_m || 0) - minY) * scale;
          return `${sx.toFixed(1)},${sy.toFixed(1)}`;
        })
        .join(" ");
    });

    return { strokeColor, polylinePoints };
  },
};
</script>
