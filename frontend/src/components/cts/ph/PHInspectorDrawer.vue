<template>
  <div class="ph-drawer d-flex flex-column" style="height: 100%;">
    <!-- Loading -->
    <v-progress-linear v-if="detail.state.loading.value" indeterminate color="primary" />

    <!-- Header -->
    <div class="pa-4" v-if="detail.state.detail.value">
      <div class="d-flex align-center ga-3 mb-3">
        <v-chip
          :color="detail.state.detail.value.current_identity_id ? 'success' : 'warning'"
          size="small"
          variant="tonal"
        >
          {{ detail.state.detail.value.identity_display_name || detail.state.detail.value.current_identity_id || "UNKNOWN" }}
        </v-chip>
        <v-chip v-if="posteriorTopLabel" size="x-small" variant="text" class="text-caption">
          {{ posteriorTopLabel }} {{ (posteriorTopProb * 100).toFixed(0) }}%
        </v-chip>
        <v-spacer />
        <span class="text-caption text-medium-emphasis">{{ formatRelative(detail.state.detail.value.last_seen_at) }}</span>
      </div>

      <div class="d-flex flex-wrap ga-1 mb-3">
        <v-chip v-for="cid in detail.state.detail.value.active_cameras || []" :key="cid" size="x-small" variant="tonal">
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
          @click="toggleForm('correct')"
        >
          Correct identity
        </v-btn>
        <v-btn
          size="small"
          variant="outlined"
          prepend-icon="mdi-merge"
          @click="toggleForm('merge')"
        >
          Merge
        </v-btn>
        <v-btn
          size="small"
          variant="outlined"
          prepend-icon="mdi-call-split"
          @click="toggleForm('split')"
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
        :ph="detail.state.detail.value"
        :observations="detail.state.observations.value"
        :loading="detail.state.loading.value"
        :error="detail.state.panelErrors.value.detail"
      />

      <v-divider />

      <PHKeyframeStrip
        :keyframes="detail.state.keyframes.value"
        :error="detail.state.panelErrors.value.keyframes"
      />

      <v-divider />

      <!-- Observations timeline -->
      <PHObservationsTimeline
        :observations="detail.state.observations.value"
        :selected-observation-id="selectedObservationId"
        :error="detail.state.panelErrors.value.observations"
        @select="onObservationSelect"
      />

      <v-divider />

      <!-- Trail -->
      <PHTrailMiniFloorPlan
        :trail="detail.state.trail.value"
        :error="detail.state.panelErrors.value.trail"
      />

      <v-divider />

      <!-- Co-present -->
      <div class="pa-3">
        <div class="text-caption font-weight-medium mb-2">Co-present PHs</div>
        <v-alert
          v-if="detail.state.panelErrors.value.coPresent"
          type="error"
          density="compact"
          variant="tonal"
          class="mb-2"
        >
          {{ detail.state.panelErrors.value.coPresent }}
        </v-alert>
        <PHListPanel
          v-else
          :items="coPresentItems"
          empty-message="No co-present PHs within 5m"
          @select="(ph) => $emit('inspect-ph', ph.ph_id)"
        />
      </div>

      <!-- Correction forms -->
      <PHCorrectionForm
        v-if="activeForm"
        :ph-id="phId"
        :identities="identities"
        :saving="correction.state.saving.value"
        :mode="activeForm"
        :merge-candidates="coPresentItems"
        :observations="detail.state.observations.value"
        :selected-observation-id="selectedObservationId"
        @correct="onCorrectSubmit"
        @merge="onMergeSubmit"
        @split="onSplitSubmit"
      />

      <v-divider />

      <!-- Revision history -->
      <div class="pa-3">
        <div class="text-caption font-weight-medium mb-2">Revision History</div>
        <PHRevisionsFeed :ph-id="phId" :limit="20" />
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, watch, onMounted } from "vue";
import { formatRelative } from "@/composables/useFormatRelative";
import { identityColor } from "@/composables/useIdentityColor";
import { usePHDetail } from "@/composables/usePHDetail";
import { usePHCorrection } from "@/composables/usePHCorrection";
import { useNotify } from "@/composables/useNotify";
import { useConfirm } from "@/composables/useConfirm";
import PHPosteriorPanel from "./PHPosteriorPanel.vue";
import PHKeyframeStrip from "./PHKeyframeStrip.vue";
import PHObservationsTimeline from "./PHObservationsTimeline.vue";
import PHTrailMiniFloorPlan from "./PHTrailMiniFloorPlan.vue";
import PHCorrectionForm from "./PHCorrectionForm.vue";
import PHRevisionsFeed from "./PHRevisionsFeed.vue";
import PHListPanel from "./PHListPanel.vue";

export default {
  name: "PHInspectorDrawer",
  components: {
    PHPosteriorPanel,
    PHKeyframeStrip,
    PHObservationsTimeline,
    PHTrailMiniFloorPlan,
    PHCorrectionForm,
    PHRevisionsFeed,
    PHListPanel,
  },
  props: {
    phId: { type: String, required: true },
    mode: { type: String, default: "view" },
    identities: { type: Array, default: () => [] },
  },
  emits: ["apply", "close", "inspect-ph"],

  setup(props, { emit }) {
    const detail = usePHDetail();
    const { notify } = useNotify();
    const { require: confirm } = useConfirm();
    const correction = usePHCorrection(notify);

    const activeForm = ref(null);
    const selectedObservationId = ref("");

    const posteriorTopLabel = computed(() => {
      const ph = detail.state.detail.value;
      if (!ph) return null;
      return ph.posterior_top_label || ph.current_identity_id || null;
    });

    const posteriorTopProb = computed(() => {
      const ph = detail.state.detail.value;
      if (!ph?.posterior_top_prob) return 0;
      return ph.posterior_top_prob;
    });

    const coPresentItems = computed(() => detail.state.coPresent.value || []);

    onMounted(() => detail.actions.fetch(props.phId));

    watch(() => props.phId, (newId) => {
      if (newId) {
        selectedObservationId.value = "";
        detail.actions.fetch(newId);
      }
    });

    function toggleForm(formName) {
      activeForm.value = activeForm.value === formName ? null : formName;
    }

    function onObservationSelect(obs) {
      selectedObservationId.value = obs?.observation_id || "";
    }

    async function onCorrectSubmit({ new_identity_id, reason }) {
      try {
        await correction.actions.apply("correct", {
          ph_id: props.phId,
          new_identity_id,
          reason,
        });
        activeForm.value = null;
        emit("apply");
      } catch { /* error notified by correction composable */ }
    }

    async function onMergeSubmit({ target_ph_id, reason }) {
      const ok = await confirm(
        `Merge PH ${props.phId} into ${target_ph_id}? This cannot be undone.`,
        { confirmText: "Merge", color: "warning" }
      );
      if (!ok) return;
      try {
        await correction.actions.apply("merge", {
          source_ph_id: props.phId,
          target_ph_id,
          reason,
        });
        activeForm.value = null;
        emit("apply");
      } catch { /* error notified */ }
    }

    async function onSplitSubmit({ at_observation_id, reason }) {
      const ok = await confirm(
        `Split PH ${props.phId} at observation ${at_observation_id}? This will create a new PH.`,
        { confirmText: "Split", color: "warning" }
      );
      if (!ok) return;
      try {
        await correction.actions.apply("split", {
          ph_id: props.phId,
          at_observation_id,
          reason,
        });
        activeForm.value = null;
        emit("apply");
      } catch { /* error notified */ }
    }

    return {
      detail,
      correction,
      activeForm,
      selectedObservationId,
      posteriorTopLabel,
      posteriorTopProb,
      coPresentItems,
      formatRelative,
      identityColor,
      toggleForm,
      onObservationSelect,
      onCorrectSubmit,
      onMergeSubmit,
      onSplitSubmit,
    };
  },
};
</script>
