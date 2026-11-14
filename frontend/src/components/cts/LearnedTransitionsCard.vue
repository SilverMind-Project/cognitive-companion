<template>
  <v-card class="glass-card">
    <v-card-title class="text-body-1">Learned Transitions</v-card-title>
    <v-card-subtitle class="text-caption text-wrap">
      How long people take to walk from one camera's view to another's, learned from tracking. A
      pair checks new handoffs once it has {{ minObservations }} or more walks: a crossing much
      faster than usual is not treated as the same person. Nothing to edit here.
    </v-card-subtitle>
    <v-divider class="mt-2" />
    <div v-if="error" class="pa-4 text-body-2 text-medium-emphasis">
      Tracking is not reachable, so learned transitions cannot be shown.
    </div>
    <div v-else-if="!transitions.length" class="pa-4 text-body-2 text-medium-emphasis">
      No transitions learned yet. They appear after people walk between cameras.
    </div>
    <v-table v-else density="compact">
      <thead>
        <tr>
          <th>From</th>
          <th>To</th>
          <th class="text-right">Usual walk</th>
          <th class="text-right">Walks seen</th>
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
          <td class="text-right">
            {{ t.mean_transit_s.toFixed(1) }} s
            <span class="text-medium-emphasis">± {{ t.std_transit_s.toFixed(1) }}</span>
          </td>
          <td class="text-right">
            {{ t.observation_count }}
            <span v-if="!t.gates_revival" class="text-caption text-medium-emphasis">
              (learning)
            </span>
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
const minObservations = ref(3);
const error = ref(false);

function name(id) {
  return props.cameraNames[id] || id;
}

onMounted(async () => {
  try {
    const body = await cts.getLearnedTransitions();
    transitions.value = body.transitions || [];
    minObservations.value = body.min_observations_to_gate;
  } catch (err) {
    console.warn("cts_learned_transitions_load_failed", err);
    error.value = true;
  }
});
</script>
