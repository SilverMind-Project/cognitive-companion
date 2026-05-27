<template>
  <v-card class="glass-card pa-4">
    <div class="text-caption text-medium-emphasis mb-1">Currently in</div>
    <div v-if="currentRoom" class="text-h5 font-weight-bold">{{ currentRoom }}</div>
    <div v-else class="text-h5 font-weight-bold text-medium-emphasis">Unknown</div>

    <div v-if="since" class="text-caption text-medium-emphasis mt-1">
      Since {{ formatTimeOnly(since) }} · In for {{ formattedDuration }}
    </div>

    <div v-if="isInferred" class="mt-2">
      <v-chip size="x-small" color="warning" variant="tonal" prepend-icon="mdi-timer-sand">
        Inferred presence
      </v-chip>
    </div>
  </v-card>
</template>

<script setup>
import { computed } from "vue";
import { formatTimeOnly } from "@/services/timezone.js";

const props = defineProps({
  currentRoom: { type: String, default: null },
  since: { type: String, default: null },
  isInferred: { type: Boolean, default: false },
  activeDuration: { type: Number, default: 0 },
});

const formattedDuration = computed(() => {
  const secs = props.activeDuration;
  if (!secs || secs < 0) return "0m";
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
});
</script>
