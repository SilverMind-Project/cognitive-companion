<template>
  <div>
    <!-- Merge -->
    <template v-if="mode === 'merge'">
      <v-divider />
      <div class="pa-3">
        <div class="text-subtitle-2 mb-2">Merge PHs</div>
        <div v-if="mergeCandidates.length" class="merge-candidate-list mb-2">
          <button
            v-for="ph in mergeCandidates"
            :key="ph.ph_id"
            type="button"
            class="merge-candidate"
            :class="{ selected: mergeTargetId === ph.ph_id }"
            @click="mergeTargetId = ph.ph_id"
          >
            <div class="d-flex align-center ga-2">
              <v-chip
                :color="ph.current_identity_id ? 'success' : 'warning'"
                size="x-small"
                variant="tonal"
              >
                {{ ph.identity_display_name || ph.current_identity_id || "UNKNOWN" }}
              </v-chip>
              <span class="text-caption text-medium-emphasis">
                {{ ph.room_name || ph.last_seen_camera || "camera unknown" }}
              </span>
            </div>
            <div class="text-caption text-medium-emphasis mt-1">
              {{ formatRelative(ph.last_seen_at) }} · {{ shortPhId(ph.ph_id) }}
            </div>
          </button>
        </div>
        <v-alert v-else type="info" density="compact" variant="tonal" class="mb-2">
          No nearby or table-visible merge candidates. Filter the table to the likely track and inspect it from there.
        </v-alert>
        <v-text-field
          v-model="mergeReason"
          label="Reason"
          variant="outlined"
          density="compact"
          hide-details
          class="mb-3"
        />
        <v-btn
          block
          color="warning"
          :loading="saving"
          :disabled="!mergeTargetId"
          @click="$emit('merge', { target_ph_id: mergeTargetId, reason: mergeReason })"
        >
          Merge
        </v-btn>
      </div>
    </template>

    <!-- Split -->
    <template v-if="mode === 'split'">
      <v-divider />
      <div class="pa-3">
        <div class="text-subtitle-2 mb-2">Split PH</div>
        <v-select
          v-model="splitObsId"
          :items="observationItems"
          label="Observation to split at"
          variant="outlined"
          density="compact"
          hide-details
          class="mb-2"
          no-data-text="No observations available"
        />
        <v-text-field
          v-model="splitReason"
          label="Reason"
          variant="outlined"
          density="compact"
          hide-details
          class="mb-3"
        />
        <v-btn
          block
          color="primary"
          :loading="saving"
          :disabled="!splitObsId"
          @click="$emit('split', { at_observation_id: splitObsId, reason: splitReason })"
        >
          Split
        </v-btn>
      </div>
    </template>
  </div>
</template>

<script>
import { ref, computed, watch } from "vue";
import { formatRelative } from "@/composables/useFormatRelative";

export default {
  name: "PHLifecycleActions",
  props: {
    saving: { type: Boolean, default: false },
    mode: { type: String, default: "merge" }, // 'merge' | 'split'
    mergeCandidates: { type: Array, default: () => [] },
    observations: { type: Array, default: () => [] },
    selectedObservationId: { type: String, default: "" },
  },
  emits: ["merge", "split"],
  setup(props) {
    const mergeTargetId = ref("");
    const mergeReason = ref("manual");
    const splitObsId = ref("");
    const splitReason = ref("manual");

    const observationItems = computed(() =>
      props.observations
        .filter((obs) => obs.observation_id)
        .map((obs) => ({
          title: `${formatRelative(obs.captured_at)} · ${obs.camera_id || "camera"} · ${obs.observation_id}`,
          value: obs.observation_id,
        }))
    );

    function shortPhId(phId) {
      return phId ? phId.slice(0, 8) : "";
    }

    watch(
      () => props.selectedObservationId,
      (id) => {
        if (id) splitObsId.value = id;
      },
      { immediate: true }
    );

    return {
      mergeTargetId,
      mergeReason,
      splitObsId,
      splitReason,
      observationItems,
      formatRelative,
      shortPhId,
    };
  },
};
</script>

<style scoped>
.merge-candidate-list {
  display: grid;
  gap: 8px;
  max-height: 260px;
  overflow-y: auto;
}

.merge-candidate {
  width: 100%;
  text-align: left;
  padding: 10px;
  border: 1px solid var(--cc-divider);
  border-radius: var(--cc-radius-sm);
  background: var(--cc-surface-2);
  cursor: pointer;
}

.merge-candidate.selected {
  border-color: rgb(var(--v-theme-primary));
  box-shadow: 0 0 0 1px rgb(var(--v-theme-primary));
}
</style>
