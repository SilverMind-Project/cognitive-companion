<template>
  <div>
    <!-- Correct identity form -->
    <template v-if="mode === 'correct'">
      <v-divider />
      <div class="pa-3">
        <div class="text-subtitle-2 mb-2">Correct Identity</div>
        <v-autocomplete
          v-model="correctIdentityId"
          :items="identityItems"
          label="Select identity"
          variant="outlined"
          density="compact"
          hide-details
          class="mb-2"
          clearable
        />
        <v-text-field
          v-model="correctReason"
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
          @click="$emit('correct', { new_identity_id: correctIdentityId, reason: correctReason })"
        >
          Apply Correction
        </v-btn>
      </div>
    </template>

    <!-- Merge form -->
    <template v-if="mode === 'merge'">
      <v-divider />
      <div class="pa-3">
        <div class="text-subtitle-2 mb-2">Merge PHs</div>
        <v-autocomplete
          v-model="mergeTargetId"
          :items="mergeTargetItems"
          label="Target PH"
          variant="outlined"
          density="compact"
          hide-details
          class="mb-2"
          no-data-text="No co-present PHs available"
          clearable
        />
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

    <!-- Split form -->
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
  name: "PHCorrectionForm",
  props: {
    phId: { type: String, required: true },
    identities: { type: Array, default: () => [] },
    saving: { type: Boolean, default: false },
    mode: { type: String, default: "correct" },
    mergeCandidates: { type: Array, default: () => [] },
    observations: { type: Array, default: () => [] },
    selectedObservationId: { type: String, default: "" },
  },
  emits: ["correct", "merge", "split"],
  setup(props) {
    const correctIdentityId = ref(null);
    const correctReason = ref("manual");
    const mergeTargetId = ref("");
    const mergeReason = ref("manual");
    const splitObsId = ref("");
    const splitReason = ref("manual");

    const identityItems = computed(() =>
      props.identities.map((id) => ({
        title: id.display_name || id.identity_id,
        value: id.identity_id,
      }))
    );

    const mergeTargetItems = computed(() =>
      props.mergeCandidates.map((ph) => ({
        title: [
          ph.identity_display_name || ph.current_identity_id || "UNKNOWN",
          ph.room_name || ph.last_seen_camera || ph.ph_id,
        ].filter(Boolean).join(" · "),
        value: ph.ph_id,
      }))
    );

    const observationItems = computed(() =>
      props.observations
        .filter((obs) => obs.observation_id)
        .map((obs) => ({
          title: `${formatRelative(obs.captured_at)} · ${obs.camera_id || "camera"} · ${obs.observation_id}`,
          value: obs.observation_id,
        }))
    );

    watch(
      () => props.selectedObservationId,
      (id) => {
        if (id) splitObsId.value = id;
      },
      { immediate: true }
    );

    return {
      correctIdentityId,
      correctReason,
      mergeTargetId,
      mergeReason,
      splitObsId,
      splitReason,
      identityItems,
      mergeTargetItems,
      observationItems,
    };
  },
};
</script>
