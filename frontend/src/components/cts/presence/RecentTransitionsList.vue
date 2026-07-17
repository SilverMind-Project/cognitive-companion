<template>
  <v-card v-if="transitions.length > 0" class="glass-card mb-4">
    <v-card-title class="text-subtitle-2">Recent Transitions</v-card-title>
    <v-divider />
    <v-list density="compact">
      <v-list-item v-for="(t, i) in transitions" :key="'t-' + i">
        <template #prepend>
          <div class="mr-2">
            <v-icon size="14" color="medium-emphasis">mdi-arrow-right</v-icon>
          </div>
        </template>
        <v-list-item-title class="text-caption">
          {{ t.from_room_name || "Unknown" }} &rarr; {{ t.to_room_name }}
        </v-list-item-title>
        <v-list-item-subtitle class="text-caption text-medium-emphasis">
          {{ formatTimeOnly(t.transitioned_at) }}
        </v-list-item-subtitle>
      </v-list-item>
    </v-list>
  </v-card>
</template>

<script setup>
import { formatTimeOnly } from "@/services/timezone.js";

defineProps({
  transitions: { type: Array, required: true },
});
</script>
