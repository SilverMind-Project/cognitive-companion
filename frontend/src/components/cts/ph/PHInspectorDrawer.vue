<template>
  <!-- Plain div: the v-navigation-drawer provides the glass surface.
       v-card flat would inherit a border from the global theme rule. -->
  <div class="ph-inspector h-100 d-flex flex-column">
    <!-- Fixed header -->
    <v-card-title class="d-flex align-center py-3 px-4">
      <div v-if="detail.state.loading.value" class="d-flex align-center ga-2">
        <v-progress-circular indeterminate size="18" color="primary" />
        <span class="text-body-2 text-medium-emphasis">Loading…</span>
      </div>
      <template v-else-if="detail.state.detail.value">
        <v-chip
          :color="detail.state.detail.value.current_identity_id ? 'success' : 'warning'"
          size="small"
          variant="tonal"
        >
          {{ detail.state.detail.value.identity_display_name || detail.state.detail.value.current_identity_id || "UNKNOWN" }}
        </v-chip>
        <v-chip v-if="posteriorTopLabel" size="x-small" variant="text" class="text-caption ml-1">
          {{ posteriorTopLabel }} {{ (posteriorTopProb * 100).toFixed(0) }}%
        </v-chip>
      </template>
      <span v-else class="text-body-2 text-medium-emphasis">No data</span>
      <v-spacer />
      <span v-if="detail.state.detail.value" class="text-caption text-medium-emphasis mr-2">
        {{ formatRelative(detail.state.detail.value.last_seen_at) }}
      </span>
      <v-btn icon="mdi-close" variant="text" size="small" @click="$emit('close')" />
    </v-card-title>

    <!-- Camera chips + action buttons (shown after load) -->
    <div v-if="detail.state.detail.value" class="px-4 pb-3">
      <div class="d-flex align-center ga-2 mb-2 text-caption text-medium-emphasis">
        <span class="cc-code">{{ detail.state.detail.value.ph_id }}</span>
        <v-btn
          icon="mdi-content-copy"
          variant="text"
          size="x-small"
          title="Copy PH ID"
          @click="copyPhId"
        />
      </div>
      <div class="d-flex flex-wrap ga-1 mb-2">
        <v-chip v-for="cid in detail.state.detail.value.active_cameras || []" :key="cid" size="x-small" variant="tonal">
          <v-icon start size="12">mdi-cctv</v-icon> {{ cid }}
        </v-chip>
      </div>
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
    <div class="flex-grow-1 overflow-y-auto" style="min-height: 0">
      <!-- Posterior panel -->
      <PHPosteriorPanel
        :ph="detail.state.detail.value"
        :observations="detail.state.observations.value"
        :loading="detail.state.loading.value"
        :error="detail.state.panelErrors.value.detail"
      />

      <v-divider />

      <!-- Keyframe strip with click-to-expand -->
      <PHKeyframeStrip
        :keyframes="detail.state.keyframes.value"
        :error="detail.state.panelErrors.value.keyframes"
        @select="onKeyframeSelect"
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
        :merge-candidates="mergeCandidateItems"
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

    <KeyframeAnnotationDialog
      v-if="lightboxFrame"
      v-model="lightboxOpen"
      :image-url="annotationImageUrl"
      :keyframe-id="annotationKeyframeId"
      :identities="identities"
      @saved="onAnnotationSaved"
      @error="notify.error($event)"
    />

    <!-- Confirmation dialog: persistent so backdrop-click doesn't leave Promise hanging -->
    <v-dialog v-model="confirmDialogOpen" max-width="400" persistent>
      <v-card rounded="xl">
        <v-card-title>{{ confirmTitle }}</v-card-title>
        <v-card-text>{{ confirmText }}</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="onCancel">{{ cancelLabel }}</v-btn>
          <v-btn :color="confirmColor" variant="flat" @click="onConfirm">{{ confirmLabel }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script>
import { ref, computed, watch, onMounted } from "vue";
import { formatRelative } from "@/composables/useFormatRelative";
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
import KeyframeAnnotationDialog from "@/components/cts/keyframes/KeyframeAnnotationDialog.vue";

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
    KeyframeAnnotationDialog,
  },
  props: {
    phId: { type: String, required: true },
    mode: { type: String, default: "view" },
    identities: { type: Array, default: () => [] },
    mergeCandidates: { type: Array, default: () => [] },
  },
  emits: ["apply", "close", "inspect-ph"],

  setup(props, { emit }) {
    const detail = usePHDetail();
    const { notify } = useNotify();
    const {
      require: confirm,
      confirmDialog: confirmDialogOpen,
      confirmTitle,
      confirmText,
      confirmLabel,
      cancelLabel,
      confirmColor,
      onConfirm,
      onCancel,
    } = useConfirm();
    const correction = usePHCorrection(notify);

    const activeForm = ref(null);
    const selectedObservationId = ref("");

    // Lightbox state
    const lightboxOpen = ref(false);
    const lightboxFrame = ref(null);

    const annotationImageUrl = computed(() => {
      if (!lightboxFrame.value) return "";
      return lightboxFrame.value.image_url || lightboxFrame.value.latest_keyframe_image_url || "";
    });

    const annotationKeyframeId = computed(() =>
      lightboxFrame.value?.keyframe_id || lightboxFrame.value?.observation_id || ""
    );

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
    const mergeCandidateItems = computed(() => {
      const byId = new Map();
      for (const item of [...coPresentItems.value, ...props.mergeCandidates]) {
        if (!item?.ph_id || item.ph_id === props.phId) continue;
        byId.set(item.ph_id, item);
      }
      return [...byId.values()];
    });

    onMounted(() => detail.actions.fetch(props.phId));

    watch(() => props.phId, (newId) => {
      if (newId) {
        selectedObservationId.value = "";
        lightboxOpen.value = false;
        detail.actions.fetch(newId);
      }
    });

    function toggleForm(formName) {
      activeForm.value = activeForm.value === formName ? null : formName;
    }

    function onObservationSelect(obs) {
      selectedObservationId.value = obs?.observation_id || "";
    }

    function onKeyframeSelect(frame) {
      const keyframeId = frame?.keyframe_id || frame?.observation_id;
      if (!keyframeId) {
        notify.error("This keyframe is missing an annotation ID.");
        return;
      }
      lightboxFrame.value = frame;
      lightboxOpen.value = true;
    }

    async function onAnnotationSaved() {
      notify.success("Annotations saved");
      await detail.actions.fetch(props.phId);
    }

    async function copyPhId() {
      try {
        await navigator.clipboard.writeText(props.phId);
        notify("PH ID copied", "success");
      } catch {
        notify("Could not copy PH ID", "error");
      }
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
      lightboxOpen,
      lightboxFrame,
      annotationImageUrl,
      annotationKeyframeId,
      posteriorTopLabel,
      posteriorTopProb,
      coPresentItems,
      mergeCandidateItems,
      confirmDialogOpen,
      confirmTitle,
      confirmText,
      confirmLabel,
      cancelLabel,
      confirmColor,
      onConfirm,
      onCancel,
      formatRelative,
      toggleForm,
      onObservationSelect,
      onKeyframeSelect,
      onAnnotationSaved,
      copyPhId,
      onCorrectSubmit,
      onMergeSubmit,
      onSplitSubmit,
    };
  },
};
</script>
