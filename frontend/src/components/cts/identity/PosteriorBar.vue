<template>
  <div class="mb-4">
    <div class="d-flex align-center ga-2 mb-2">
      <v-icon size="16" color="medium-emphasis">mdi-chart-bar</v-icon>
      <span class="text-caption font-weight-medium text-uppercase">Evidence</span>
    </div>
    <div v-if="hasDistribution" class="posterior-bar">
      <div
        v-for="seg in segments"
        :key="seg.label"
        class="posterior-segment"
        :style="{ width: seg.pct + '%', background: seg.color }"
        :title="`${seg.label}: ${(seg.prob * 100).toFixed(1)}%`"
      />
    </div>
    <div v-if="hasDistribution" class="d-flex flex-wrap ga-1 mt-1">
      <span v-for="seg in segments" :key="seg.label" class="text-caption text-medium-emphasis">
        <v-icon size="10" :color="seg.color">mdi-circle</v-icon>
        {{ seg.label }}: {{ (seg.prob * 100).toFixed(0) }}%
      </span>
    </div>
    <span v-else class="text-caption text-medium-emphasis">No probability data available</span>
  </div>
</template>

<script>
import { identityColor } from "@/composables/useIdentityColor";

export default {
  name: "PosteriorBar",
  props: {
    posterior: { type: Object, default: null },
  },
  computed: {
    hasDistribution() {
      return this.posterior && this.posterior.distribution && Object.keys(this.posterior.distribution).length > 0;
    },
    segments() {
      if (!this.hasDistribution) return [];
      const dist = this.posterior.distribution;
      const entries = Object.entries(dist).sort((a, b) => b[1] - a[1]);
      return entries.map(([label, prob]) => ({
        label,
        prob,
        pct: Math.max(prob * 100, 2), // minimum width for visibility
        color: label === "UNKNOWN" ? "#9E9E9E" : identityColor(label),
      }));
    },
  },
};
</script>

<style scoped>
.posterior-bar {
  display: flex;
  height: 8px;
  border-radius: 4px;
  overflow: hidden;
  background: rgba(var(--v-theme-on-surface), 0.08);
}
.posterior-segment {
  transition: width 0.3s ease;
  min-width: 2px;
}
</style>
