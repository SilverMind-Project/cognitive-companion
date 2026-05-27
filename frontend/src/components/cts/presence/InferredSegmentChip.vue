<template>
  <v-chip
    size="x-small"
    color="warning"
    variant="tonal"
    prepend-icon="mdi-timer-sand"
    class="inferred-chip"
  >
    Inferred · {{ roomName }}
    <span v-if="since" class="ml-1">since {{ formatTimeOnly(since) }}</span>
  </v-chip>
</template>

<script setup>
import { formatTimeOnly } from "@/services/timezone.js";

defineProps({
  roomName: { type: String, required: true },
  since: { type: String, default: null },
});
</script>
