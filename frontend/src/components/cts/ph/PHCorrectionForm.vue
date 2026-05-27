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
        <v-text-field
          v-model="mergeTargetId"
          label="Target PH ID"
          variant="outlined"
          density="compact"
          hide-details
          class="mb-2"
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
        <v-text-field
          v-model="splitObsId"
          label="Observation ID to split at"
          variant="outlined"
          density="compact"
          hide-details
          class="mb-2"
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
          @click="$emit('split', { at_observation_id: splitObsId, reason: splitReason })"
        >
          Split
        </v-btn>
      </div>
    </template>
  </div>
</template>

<script>
import { ref, computed } from "vue";

export default {
  name: "PHCorrectionForm",
  props: {
    phId: { type: String, required: true },
    identities: { type: Array, default: () => [] },
    saving: { type: Boolean, default: false },
    mode: { type: String, default: "correct" },
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

    return {
      correctIdentityId,
      correctReason,
      mergeTargetId,
      mergeReason,
      splitObsId,
      splitReason,
      identityItems,
    };
  },
};
</script>
