<template>
  <v-card class="glass-card">
    <v-card-title class="text-subtitle-2">Today's room dwell totals</v-card-title>
    <v-divider />
    <v-card-text>
      <div v-if="dwells.length === 0" class="text-caption text-medium-emphasis">
        No dwell data for this period.
      </div>
      <div v-for="d in sortedDwells" :key="d.room_id" class="d-flex align-center ga-2 mb-2">
        <span class="text-caption text-truncate" style="min-width: 100px; max-width: 120px">
          {{ d.room_name }}
        </span>
        <v-progress-linear
          :model-value="computedPercent(d)"
          color="primary"
          height="8"
          rounded
          style="flex: 1"
        />
        <span class="text-caption text-medium-emphasis" style="min-width: 55px; text-align: right">
          {{ formatDuration(d.total_seconds) }}
        </span>
      </div>
    </v-card-text>
  </v-card>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  dwells: { type: Array, required: true },
});

const maxSeconds = computed(() => Math.max(...props.dwells.map((d) => d.total_seconds), 1));

const sortedDwells = computed(() =>
  [...props.dwells].sort((a, b) => b.total_seconds - a.total_seconds),
);

function computedPercent(d) {
  if (d.percentage != null) return d.percentage;
  return (d.total_seconds / maxSeconds.value) * 100;
}

function formatDuration(secs) {
  if (!secs || secs < 0) return "0m";
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}
</script>
