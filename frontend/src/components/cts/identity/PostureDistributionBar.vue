<template>
  <div class="posture-wrap">
    <div v-if="loading" class="posture-bar posture-bar--skeleton">
      <div class="posture-seg posture-seg--ghost" style="width: 100%" />
    </div>
    <template v-else-if="segments.length">
      <div
        class="posture-bar"
        role="img"
        :aria-label="ariaLabel"
      >
        <div
          v-for="seg in segments"
          :key="seg.posture"
          class="posture-seg"
          :style="{ width: seg.pct + '%', background: seg.color }"
          :title="`${seg.label}: ${seg.pct.toFixed(0)}%`"
        />
      </div>
      <div class="d-flex flex-wrap ga-3 mt-1">
        <div
          v-for="seg in segments"
          :key="'leg-' + seg.posture"
          class="d-flex align-center ga-1"
        >
          <span class="posture-dot" :style="{ background: seg.color }" />
          <span class="text-caption text-medium-emphasis">{{ seg.label }}</span>
          <span class="text-caption font-weight-medium ml-1">{{ seg.pct.toFixed(0) }}%</span>
        </div>
      </div>
    </template>
    <span v-else class="text-caption text-disabled">No posture data</span>
  </div>
</template>

<script>
// Noise thresholds mirroring the orchestrator's trajectory_writer constants.
// walking without measurable movement → misclassification; drop it.
// lying with high kinetic energy → misclassification; drop it.
const WALKING_MIN_ENERGY = 0.015;
const LYING_MAX_ENERGY = 0.20;

const POSTURE_META = {
  standing: { label: "Standing", color: "#0a84ff" },
  sitting:  { label: "Sitting",  color: "#30d158" },
  walking:  { label: "Walking",  color: "#bf5af2" },
  lying:    { label: "Lying",    color: "#ff9f0a" },
};

function isNoisy(point) {
  const posture = point.posture;
  if (!posture || posture === "unknown") return true;
  const me = point.motion_energy;
  if (me === null || me === undefined) return false;
  if (posture === "walking" && me < WALKING_MIN_ENERGY) return true;
  if (posture === "lying"   && me > LYING_MAX_ENERGY)   return true;
  return false;
}

export default {
  name: "PostureDistributionBar",

  props: {
    points:  { type: Array,   default: () => [] },
    loading: { type: Boolean, default: false },
  },

  computed: {
    segments() {
      const clean = this.points.filter((p) => !isNoisy(p));
      if (!clean.length) return [];

      const counts = {};
      for (const p of clean) {
        counts[p.posture] = (counts[p.posture] || 0) + 1;
      }
      const total = clean.length;
      return Object.entries(counts)
        .sort((a, b) => b[1] - a[1])
        .map(([posture, count]) => {
          const meta = POSTURE_META[posture] || { label: posture, color: "#8e8e93" };
          return { posture, pct: (count / total) * 100, ...meta };
        });
    },

    ariaLabel() {
      return this.segments.map((s) => `${s.label} ${s.pct.toFixed(0)}%`).join(", ");
    },
  },
};
</script>

<style scoped>
.posture-bar {
  display: flex;
  height: 8px;
  border-radius: 4px;
  overflow: hidden;
  background: rgba(var(--v-theme-on-surface), 0.06);
  gap: 1px;
}

.posture-seg {
  transition: width 0.35s ease;
  min-width: 3px;
}

.posture-seg--ghost {
  background: rgba(var(--v-theme-on-surface), 0.08);
  animation: shimmer 1.4s ease-in-out infinite;
}

.posture-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

@keyframes shimmer {
  0%   { opacity: 0.4; }
  50%  { opacity: 0.8; }
  100% { opacity: 0.4; }
}
</style>
