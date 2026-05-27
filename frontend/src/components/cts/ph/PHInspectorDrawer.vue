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
      />

      <v-divider />

      <!-- Observations timeline -->
      <PHObservationsTimeline :observations="detail.state.observations.value" />

      <v-divider />

      <!-- Trail -->
      <PHTrailMiniFloorPlan :trail="detail.state.trail.value" />

      <v-divider />

      <!-- Co-present -->
      <div class="pa-3">
        <div class="text-caption font-weight-medium mb-2">Co-present PHs</div>
        <PHListPanel
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
import PHObservationsTimeline from "./PHObservationsTimeline.vue";
import PHTrailMiniFloorPlan from "./PHTrailMiniFloorPlan.vue";
import PHCorrectionForm from "./PHCorrectionForm.vue";
import PHRevisionsFeed from "./PHRevisionsFeed.vue";
import PHListPanel from "./PHListPanel.vue";

export default {
  name: "PHInspectorDrawer",
  components: {
    PHPosteriorPanel,
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

    const coPresentItems = computed(() =>
      detail.state.coPresent.value.map((id) => ({ ph_id: id }))
    );

    onMounted(() => detail.actions.fetch(props.phId));

    watch(() => props.phId, (newId) => {
      if (newId) detail.actions.fetch(newId);
    });

    function toggleForm(formName) {
      activeForm.value = activeForm.value === formName ? null : formName;
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
      posteriorTopLabel,
      posteriorTopProb,
      coPresentItems,
      formatRelative,
      identityColor,
      toggleForm,
      onCorrectSubmit,
      onMergeSubmit,
      onSplitSubmit,
    };
  },
};
</script>
