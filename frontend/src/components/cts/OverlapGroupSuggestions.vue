<template>
  <v-card v-if="pending.length" class="glass-card mb-3" data-testid="overlap-suggestions">
    <v-card-title class="text-body-1">Suggested from calibrated coverage</v-card-title>
    <v-card-subtitle class="text-caption text-wrap">
      These calibrated cameras see overlapping floor. Confirm on site before adding; add any
      uncalibrated camera that sees the same area too.
    </v-card-subtitle>
    <v-list density="compact">
      <v-list-item
        v-for="group in pending"
        :key="group.camera_ids.join('|')"
        :data-testid="`overlap-suggestion-${group.camera_ids.join('-')}`"
      >
        <v-list-item-title class="text-body-2">{{ names(group.camera_ids) }}</v-list-item-title>
        <v-list-item-subtitle class="text-caption">
          {{ Math.round(group.iou * 100) }}% shared coverage
        </v-list-item-subtitle>
        <template #append>
          <v-btn
            size="small"
            variant="tonal"
            color="primary"
            @click="emit('use', group.camera_ids)"
          >
            Use
          </v-btn>
        </template>
      </v-list-item>
    </v-list>
  </v-card>
</template>

<script setup>
import { computed } from "vue";

/** @typedef {{ camera_ids: string[], iou: number, declared: boolean }} Suggestion */

const props = defineProps({
  /** @type {import('vue').PropType<{ groups: Suggestion[], uncalibrated_camera_ids: string[] }>} */
  suggestions: { type: Object, required: true },
  /** @type {import('vue').PropType<Record<string, string>>} */
  cameraNames: { type: Object, required: true },
});

const emit = defineEmits(["use"]);

// A suggestion already covered by a declared group needs no action.
const pending = computed(() => (props.suggestions.groups || []).filter((g) => !g.declared));

function names(ids) {
  return ids.map((id) => props.cameraNames[id] || id).join(", ");
}
</script>
