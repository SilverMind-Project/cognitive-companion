<template>
  <div class="mb-4">
    <div class="d-flex align-center ga-2 mb-2">
      <v-icon size="16" color="medium-emphasis">mdi-map-marker-path</v-icon>
      <span class="text-caption font-weight-medium text-uppercase">Trail (5 min)</span>
    </div>
    <div v-if="hasPoints" class="trail-svg-container">
      <svg :viewBox="viewBox" class="trail-svg">
        <polyline :points="polylinePoints" fill="none" stroke="var(--cc-primary)" stroke-width="2" />
        <circle
          v-if="lastPoint"
          :cx="lastPoint.x"
          :cy="lastPoint.y"
          r="3"
          fill="var(--cc-primary)"
        />
      </svg>
    </div>
    <span v-else class="text-caption text-medium-emphasis">No trail data available</span>
  </div>
</template>

<script>
export default {
  name: "TrailMiniMap",
  props: {
    points: { type: Array, default: () => [] },
  },
  computed: {
    hasPoints() {
      return this.points.length >= 2;
    },
    lastPoint() {
      if (!this.points.length) return null;
      const p = this.points[this.points.length - 1];
      return this.projectPoint(p);
    },
    polylinePoints() {
      return this.points.map((p) => this.projectPoint(p)).map((pt) => `${pt.x},${pt.y}`).join(" ");
    },
    viewBox() {
      return "0 0 400 200";
    },
  },
  methods: {
    projectPoint(p) {
      // Map ground coordinates (typically 0-10m x, 0-8m y) to SVG viewBox
      const groundX = p.ground_x != null ? p.ground_x : (p.x || 0);
      const groundY = p.ground_y != null ? p.ground_y : (p.y || 0);
      // Simple linear mapping with margins
      const x = 20 + (groundX / 10) * 360;
      const y = 180 - (groundY / 8) * 160;
      return { x: Math.max(0, Math.min(400, x)), y: Math.max(0, Math.min(200, y)) };
    },
  },
};
</script>

<style scoped>
.trail-svg-container {
  background: rgba(var(--v-theme-on-surface), 0.04);
  border-radius: 8px;
}
.trail-svg {
  width: 100%;
  height: 120px;
}
</style>
