<template>
  <div class="pa-3">
    <div class="text-caption font-weight-medium mb-2">Observations</div>
    <v-alert v-if="error" type="error" density="compact" variant="tonal" class="mb-2">
      {{ error }}
    </v-alert>
    <div v-else-if="observations.length === 0" class="text-caption text-medium-emphasis">
      No observations recorded.
    </div>
    <div
      v-for="obs in observations.slice(0, maxItems)"
      :key="obs.observation_id || obs.captured_at"
      class="observation-row d-flex align-center ga-2 py-1"
      :class="{ selected: obs.observation_id && obs.observation_id === selectedObservationId }"
      style="font-size: 0.75rem;"
      @click="$emit('select', obs)"
    >
      <span class="text-caption text-medium-emphasis" style="width: 80px; flex-shrink: 0;">
        {{ formatRelative(obs.captured_at) }}
      </span>
      <v-chip size="x-small" variant="tonal">{{ obs.camera_id }}</v-chip>
      <span class="text-caption">{{ obs.floor_x_m.toFixed(1) }}, {{ obs.floor_y_m.toFixed(1) }}</span>
    </div>
  </div>
</template>

<script>
import { formatRelative } from "@/composables/useFormatRelative";

export default {
  name: "PHObservationsTimeline",
  props: {
    observations: { type: Array, default: () => [] },
    maxItems: { type: Number, default: 50 },
    selectedObservationId: { type: String, default: "" },
    error: { type: String, default: "" },
  },
  emits: ["select"],
  setup() {
    return { formatRelative };
  },
};
</script>

<style scoped>
.observation-row {
  cursor: pointer;
  border-radius: var(--cc-radius-sm);
  padding-left: 4px;
  padding-right: 4px;
}

.observation-row:hover,
.observation-row.selected {
  background: var(--cc-surface-2);
}
</style>
