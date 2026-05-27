<template>
  <div class="ph-drawer d-flex flex-column" style="height: 100%;">
    <!-- Loading -->
    <v-progress-linear v-if="detail.loading.value" indeterminate color="primary" />

    <!-- Header -->
    <div class="pa-4" v-if="detail.detail.value">
      <div class="d-flex align-center ga-3 mb-3">
        <v-chip
          :color="detail.detail.value.current_identity_id ? 'success' : 'warning'"
          size="small"
          variant="tonal"
        >
          {{ detail.detail.value.identity_display_name || detail.detail.value.current_identity_id || "UNKNOWN" }}
        </v-chip>
        <v-chip v-if="posteriorTopLabel" size="x-small" variant="text" class="text-caption">
          {{ posteriorTopLabel }} {{ (posteriorTopProb * 100).toFixed(0) }}%
        </v-chip>
        <v-spacer />
        <span class="text-caption text-medium-emphasis">{{ formatRelative(detail.detail.value.last_seen_at) }}</span>
      </div>

      <div class="d-flex flex-wrap ga-1 mb-3">
        <v-chip v-for="cid in detail.detail.value.active_cameras || []" :key="cid" size="x-small" variant="tonal">
          <v-icon start size="12">mdi-cctv</v-icon> {{ cid }}
        </v-chip>
      </div>

      <!-- Action buttons -->
      <div class="d-flex ga-2">
        <v-btn
          v-if="mode === 'correct' || mode === 'view'"
          size="small"
          variant="tonal"
          color="primary"
          prepend-icon="mdi-account-edit"
          data-testid="ph-drawer-correct-btn"
          @click="showCorrectForm = !showCorrectForm"
        >
          Correct identity
        </v-btn>
        <v-btn
          size="small"
          variant="outlined"
          prepend-icon="mdi-merge"
          @click="showMergeForm = !showMergeForm"
        >
          Merge
        </v-btn>
        <v-btn
          size="small"
          variant="outlined"
          prepend-icon="mdi-call-split"
          @click="showSplitForm = !showSplitForm"
        >
          Split
        </v-btn>
      </div>
    </div>

    <v-divider />

    <!-- Scrollable body -->
    <div class="flex-1-1-0 overflow-y-auto" style="min-height: 0;">
      <!-- Posterior panel -->
      <PHPosteriorPanel
        :ph="detail.detail.value"
        :observations="detail.observations.value"
      />

      <v-divider />

      <!-- Observations timeline -->
      <div class="pa-3">
        <div class="text-caption font-weight-medium mb-2">Observations</div>
        <div v-if="detail.observations.value.length === 0" class="text-caption text-medium-emphasis">
          No observations recorded.
        </div>
        <div
          v-for="obs in detail.observations.value.slice(0, 50)"
          :key="obs.observation_id || obs.captured_at"
          class="d-flex align-center ga-2 py-1"
          style="font-size: 0.75rem;"
        >
          <span class="text-caption text-medium-emphasis" style="width: 80px; flex-shrink: 0;">
            {{ formatRelative(obs.captured_at) }}
          </span>
          <v-chip size="x-small" variant="tonal">{{ obs.camera_id }}</v-chip>
          <span class="text-caption">{{ obs.floor_x_m.toFixed(1) }}, {{ obs.floor_y_m.toFixed(1) }}</span>
        </div>
      </div>

      <v-divider />

      <!-- Trail -->
      <div class="pa-3">
        <div class="text-caption font-weight-medium mb-2">Floor Trail</div>
        <div v-if="detail.trail.value.length === 0" class="text-caption text-medium-emphasis">
          No trail data.
        </div>
        <div v-else class="text-caption">
          {{ detail.trail.value.length }} points recorded.
        </div>
      </div>

      <v-divider />

      <!-- Co-present -->
      <div class="pa-3">
        <div class="text-caption font-weight-medium mb-2">Co-present PHs</div>
        <div v-if="detail.coPresent.value.length === 0" class="text-caption text-medium-emphasis">
          No co-present PHs within 5m.
        </div>
        <v-chip v-for="cp in detail.coPresent.value" :key="cp" size="x-small" variant="tonal" class="mr-1">
          {{ cp }}
        </v-chip>
      </div>

      <!-- Correction forms -->
      <template v-if="showCorrectForm">
        <v-divider />
        <div class="pa-3">
          <div class="text-subtitle-2 mb-2">Correct Identity</div>
          <v-autocomplete
            v-model="correctForm.new_identity_id"
            :items="identityItems"
            label="Select identity"
            variant="outlined"
            density="compact"
            hide-details
            class="mb-2"
            clearable
          />
          <v-text-field
            v-model="correctForm.reason"
            label="Reason"
            variant="outlined"
            density="compact"
            hide-details
            class="mb-3"
          />
          <v-btn
            block
            color="primary"
            :loading="correction.saving.value"
            @click="doCorrect"
          >
            Apply Correction
          </v-btn>
        </div>
      </template>

      <template v-if="showMergeForm">
        <v-divider />
        <div class="pa-3">
          <div class="text-subtitle-2 mb-2">Merge PHs</div>
          <v-text-field
            v-model="mergeForm.target_ph_id"
            label="Target PH ID"
            variant="outlined"
            density="compact"
            hide-details
            class="mb-2"
          />
          <v-text-field
            v-model="mergeForm.reason"
            label="Reason"
            variant="outlined"
            density="compact"
            hide-details
            class="mb-3"
          />
          <v-btn
            block
            color="warning"
            :loading="correction.saving.value"
            @click="doMerge"
          >
            Merge
          </v-btn>
        </div>
      </template>

      <template v-if="showSplitForm">
        <v-divider />
        <div class="pa-3">
          <div class="text-subtitle-2 mb-2">Split PH</div>
          <v-text-field
            v-model="splitForm.at_observation_id"
            label="Observation ID to split at"
            variant="outlined"
            density="compact"
            hide-details
            class="mb-2"
          />
          <v-text-field
            v-model="splitForm.reason"
            label="Reason"
            variant="outlined"
            density="compact"
            hide-details
            class="mb-3"
          />
          <v-btn
            block
            color="primary"
            :loading="correction.saving.value"
            @click="doSplit"
          >
            Split
          </v-btn>
        </div>
      </template>
    </div>
  </div>
</template>

<script>
import { ref, reactive, computed, watch, onMounted } from "vue";
import { formatRelative } from "@/composables/useFormatRelative";
import { identityColor } from "@/composables/useIdentityColor";
import { usePHDetail } from "@/composables/usePHDetail";
import { usePHCorrection } from "@/composables/usePHCorrection";
import PHPosteriorPanel from "./PHPosteriorPanel.vue";

export default {
  name: "PHInspectorDrawer",
  components: { PHPosteriorPanel },
  props: {
    phId: { type: String, required: true },
    mode: { type: String, default: "view" },
    identities: { type: Array, default: () => [] },
  },
  emits: ["apply", "close"],

  setup(props, { emit }) {
    const detail = usePHDetail();
    const notify = {
      success: (msg) => console.log("[ph-drawer] success:", msg),
      error: (msg) => console.error("[ph-drawer] error:", msg),
    };
    const correction = usePHCorrection(notify);

    const showCorrectForm = ref(false);
    const showMergeForm = ref(false);
    const showSplitForm = ref(false);

    const correctForm = reactive({ new_identity_id: null, reason: "manual" });
    const mergeForm = reactive({ target_ph_id: "", reason: "manual" });
    const splitForm = reactive({ at_observation_id: "", reason: "manual" });

    const posteriorTopLabel = computed(() => {
      const ph = detail.detail.value;
      if (!ph) return null;
      return ph.posterior_top_label || ph.current_identity_id || null;
    });

    const posteriorTopProb = computed(() => {
      const ph = detail.detail.value;
      if (!ph?.posterior_top_prob) return 0;
      return ph.posterior_top_prob;
    });

    const identityItems = computed(() =>
      props.identities.map((id) => ({
        title: id.display_name || id.identity_id,
        value: id.identity_id,
      }))
    );

    onMounted(() => detail.fetch(props.phId));

    watch(() => props.phId, (newId) => {
      if (newId) detail.fetch(newId);
    });

    async function doCorrect() {
      try {
        await correction.apply("correct", {
          ph_id: props.phId,
          new_identity_id: correctForm.new_identity_id,
          reason: correctForm.reason,
        });
        showCorrectForm.value = false;
        emit("apply");
      } catch { /* error already notified */ }
    }

    async function doMerge() {
      try {
        await correction.apply("merge", {
          source_ph_id: props.phId,
          target_ph_id: mergeForm.target_ph_id,
          reason: mergeForm.reason,
        });
        showMergeForm.value = false;
        emit("apply");
      } catch { /* error already notified */ }
    }

    async function doSplit() {
      try {
        await correction.apply("split", {
          ph_id: props.phId,
          at_observation_id: splitForm.at_observation_id,
          reason: splitForm.reason,
        });
        showSplitForm.value = false;
        emit("apply");
      } catch { /* error already notified */ }
    }

    return {
      detail,
      correction,
      showCorrectForm,
      showMergeForm,
      showSplitForm,
      correctForm,
      mergeForm,
      splitForm,
      posteriorTopLabel,
      posteriorTopProb,
      identityItems,
      formatRelative,
      identityColor,
      doCorrect,
      doMerge,
      doSplit,
    };
  },
};
</script>
