<template>
  <v-card class="glass-card">
    <v-card-title class="text-body-1">Camera Handoffs</v-card-title>
    <v-card-subtitle class="text-caption text-wrap">
      How often tracking has handed a person from one camera to another, and how long after the
      first camera's track closed the person was picked up again. Learned automatically; nothing to
      edit, and it does not change how tracking decides.
    </v-card-subtitle>
    <v-divider class="mt-2" />
    <div v-if="error" class="pa-4 text-body-2 text-medium-emphasis">
      Tracking is not reachable, so handoffs cannot be shown.
    </div>
    <div v-else-if="!transitions.length" class="pa-4 text-body-2 text-medium-emphasis">
      No handoffs yet. They appear after people move between cameras.
    </div>
    <v-table v-else density="compact">
      <thead>
        <tr>
          <th>From</th>
          <th>To</th>
          <th class="text-right">Handoffs</th>
          <th class="text-right">Picked up after close</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="t in transitions"
          :key="`${t.from_camera}->${t.to_camera}`"
          :data-testid="`transition-${t.from_camera}-${t.to_camera}`"
        >
          <td>{{ name(t.from_camera) }}</td>
          <td>{{ name(t.to_camera) }}</td>
          <td class="text-right">{{ t.observation_count }}</td>
          <td class="text-right">
            {{ t.mean_transit_s.toFixed(1) }} s
            <span class="text-medium-emphasis">± {{ t.std_transit_s.toFixed(1) }}</span>
          </td>
        </tr>
      </tbody>
    </v-table>
  </v-card>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { cts } from "@/services/cts.js";

const props = defineProps({
  /** @type {import('vue').PropType<Record<string, string>>} */
  cameraNames: { type: Object, required: true },
});

const transitions = ref([]);
const error = ref(false);

function name(id) {
  return props.cameraNames[id] || id;
}

onMounted(async () => {
  try {
    transitions.value = (await cts.getLearnedTransitions()).transitions || [];
  } catch (err) {
    console.warn("cts_learned_transitions_load_failed", err);
    error.value = true;
  }
});
</script>
