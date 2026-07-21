<template>
  <div class="identity-correction-workflow" data-testid="identity-correction-workflow">
    <!-- ════════════ Job phase: show async status until terminal ════════════ -->
    <template v-if="state.job.value">
      <CorrectionJobStatus :job="state.job.value" @retry="onRetry" />
      <div class="d-flex justify-end mt-3">
        <v-btn variant="text" @click="$emit('close')">Close</v-btn>
      </div>
    </template>

    <!-- ════════════════════════ Correction form ═══════════════════════════ -->
    <template v-else>
      <!-- Current evidence for the bbox/PH being corrected -->
      <div v-if="bbox" class="mb-3">
        <div class="text-caption text-medium-emphasis mb-1">Current</div>
        <IdentityEvidenceBadges :bbox="bbox" :targets="state.targets.value" detailed />
      </div>

      <!-- Targets: loading / error+retry / forbidden / empty / success -->
      <div v-if="state.targetsLoading.value" class="d-flex align-center ga-2 py-3">
        <v-progress-circular indeterminate size="18" color="primary" />
        <span class="text-body-2 text-medium-emphasis">Loading household members…</span>
      </div>

      <v-alert
        v-else-if="state.targetsError.value"
        type="error"
        density="compact"
        variant="tonal"
        class="mb-2"
      >
        <div class="d-flex align-center ga-2">
          <span>{{ state.targetsError.value }}</span>
          <v-spacer />
          <v-btn size="x-small" variant="tonal" @click="actions.loadTargets()">Retry</v-btn>
        </div>
      </v-alert>

      <v-alert
        v-else-if="!state.targets.value.length"
        type="info"
        density="compact"
        variant="tonal"
        class="mb-2"
      >
        No active household members. Add or activate a member to correct identity.
      </v-alert>

      <template v-else>
        <!-- Stale-version banner: forces re-review of the changed range -->
        <v-alert
          v-if="state.staleConflict.value"
          type="warning"
          density="compact"
          variant="tonal"
          class="mb-2"
          data-testid="stale-conflict"
        >
          The track changed since you started. Review the updated range below and confirm again.
        </v-alert>

        <!-- Identity selector. Clearing it never submits. -->
        <v-autocomplete
          v-model="selectedTarget"
          :items="targetItems"
          item-title="title"
          item-value="value"
          label="Correct to"
          placeholder="Select household member"
          variant="outlined"
          density="compact"
          clearable
          hide-details
          class="mb-2"
        />

        <!-- Reason + optional note -->
        <v-select
          v-model="reasonCode"
          :items="REASON_OPTIONS"
          label="Reason"
          variant="outlined"
          density="compact"
          hide-details
          class="mb-2"
        />
        <v-textarea
          v-model="note"
          label="Note (optional)"
          variant="outlined"
          density="compact"
          rows="2"
          auto-grow
          hide-details
          class="mb-3"
        />

        <!-- Proposal: loading / error / range selector -->
        <div v-if="state.proposalLoading.value" class="d-flex align-center ga-2 mb-2">
          <v-progress-circular indeterminate size="16" color="primary" />
          <span class="text-caption text-medium-emphasis">Proposing segment…</span>
        </div>
        <v-alert
          v-else-if="state.proposalError.value"
          type="error"
          density="compact"
          variant="tonal"
          class="mb-2"
        >
          {{ state.proposalError.value }}
        </v-alert>
        <CorrectionRangeSelector
          v-else-if="state.proposal.value"
          v-model:scope-mode="scopeMode"
          v-model:start-id="startId"
          v-model:end-id="endId"
          :proposal="state.proposal.value"
          :observations="observations"
          :allow-frame-only="allowFrameOnly"
          class="mb-3"
        />

        <!-- ReID verify gate: only when the server marks the crop eligible.
             The producing side (eligibility + quality reasons) lands with the
             ReID review queue; until then no eligible flag is returned, so
             the action stays hidden. Client-side override is never allowed. -->
        <div v-if="reidVerification" class="mb-3">
          <v-checkbox
            v-if="reidVerification.eligible"
            v-model="verifyReidCrop"
            label="Verify ReID crop"
            density="compact"
            hide-details
          />
          <v-alert v-else type="info" density="compact" variant="tonal">
            ReID crop not eligible for verification:
            {{ (reidVerification.quality_reasons || []).join(", ") || "quality gate not met" }}
          </v-alert>
        </div>

        <!-- Actions: explicit Set to Unknown is its own action -->
        <div class="d-flex flex-wrap ga-2">
          <v-btn
            color="primary"
            variant="flat"
            :loading="state.applying.value"
            :disabled="!canApply"
            data-testid="apply-correction"
            @click="submit({ setUnknown: false })"
          >
            Apply correction
          </v-btn>
          <v-btn
            variant="outlined"
            :loading="state.applying.value"
            :disabled="state.applying.value || !state.proposal.value"
            data-testid="set-unknown"
            @click="submit({ setUnknown: true })"
          >
            Set to Unknown
          </v-btn>
          <v-spacer />
          <v-btn variant="text" @click="$emit('close')">Cancel</v-btn>
        </div>
      </template>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from "vue";
import { useIdentityCorrection } from "@/composables/useIdentityCorrection.js";
import { useNotify } from "@/composables/useNotify.js";
import IdentityEvidenceBadges from "./IdentityEvidenceBadges.vue";
import CorrectionRangeSelector from "./CorrectionRangeSelector.vue";
import CorrectionJobStatus from "./CorrectionJobStatus.vue";

const props = defineProps({
  phId: { type: String, required: true },
  // PH inspector: a selected observation scopes the proposal.
  observationId: { type: String, default: "" },
  // Keyframe: the physical frame's capture time + bbox provenance.
  frameCapturedAt: { type: String, default: "" },
  reviewedFrameId: { type: String, default: "" },
  reviewedBbox: { type: Object, default: null },
  bbox: { type: Object, default: null },
  sourceView: { type: String, default: "ph_inspector" },
  // From a keyframe bbox: frame-only is the default with segment as an option.
  defaultScope: { type: String, default: "segment" },
  observations: { type: Array, default: () => [] },
  // Optional injected composable (tests / shared instance).
  controller: { type: Object, default: null },
});

const emit = defineEmits(["applied", "close"]);

const { notify } = useNotify();
const correction = props.controller || useIdentityCorrection(notify);
const { state, actions } = correction;

const REASON_OPTIONS = [
  { title: "Wrong person", value: "wrong_person" },
  { title: "Identity uncertain", value: "identity_uncertain" },
  { title: "Track handoff", value: "track_handoff" },
  { title: "Duplicate hypothesis", value: "duplicate_hypothesis" },
  { title: "Bad bounding box", value: "bad_bbox" },
  { title: "Other", value: "other" },
];

const selectedTarget = ref(null);
const reasonCode = ref("wrong_person");
const note = ref("");
const scopeMode = ref(props.defaultScope);
const startId = ref("");
const endId = ref("");
const verifyReidCrop = ref(false);

const allowFrameOnly = computed(() => props.sourceView === "keyframe");

// ReID verification eligibility is server-owned; surfaced only when present.
const reidVerification = computed(() => props.bbox?.reid_verification || null);

const targetItems = computed(() =>
  state.targets.value.map((t) => ({
    title: t.display_name || t.identity_id,
    value: t.identity_id,
  })),
);

// A correction needs an explicit target (Set to Unknown is a separate action),
// a fresh proposal, and not be mid-submit. Clearing the selector never submits.
const canApply = computed(
  () => !!selectedTarget.value && !!state.proposal.value && !state.applying.value,
);

onMounted(async () => {
  await actions.loadTargets().catch(() => {});
  await refreshProposal();
});

watch(
  () => [props.phId, props.observationId],
  async () => {
    actions.reset();
    scopeMode.value = props.defaultScope;
    await refreshProposal();
  },
);

// When a stale conflict re-proposes, reset the boundaries to the new segment.
watch(
  () => state.proposal.value,
  (p) => {
    if (p) {
      startId.value = p.start.observation_id;
      endId.value = p.end.observation_id;
    }
  },
);

async function refreshProposal() {
  try {
    await actions.propose({
      ph_id: props.phId,
      observation_id: props.observationId || null,
      at: props.frameCapturedAt || null,
    });
  } catch {
    /* surfaced via state.proposalError */
  }
}

function capturedAtFor(id) {
  const p = state.proposal.value;
  if (p?.start.observation_id === id) return p.start.captured_at;
  if (p?.end.observation_id === id) return p.end.captured_at;
  const obs = props.observations.find((o) => o.observation_id === id);
  return obs?.captured_at || null;
}

function buildPayload({ setUnknown }) {
  const p = state.proposal.value;
  const isFrame = scopeMode.value === "frame_only";
  const start = isFrame
    ? props.frameCapturedAt || capturedAtFor(startId.value) || p.start.captured_at
    : capturedAtFor(startId.value) || p.start.captured_at;
  const end = isFrame ? start : capturedAtFor(endId.value) || p.end.captured_at;
  return {
    ph_id: props.phId,
    reason_code: reasonCode.value,
    observation_start: start,
    observation_end: end,
    base_ph_version: p.ph_version,
    target_identity_id: setUnknown ? null : selectedTarget.value,
    set_unknown: setUnknown,
    frame_only: isFrame,
    note: note.value || null,
    source_view: props.sourceView,
    reviewed_frame_id: props.reviewedFrameId || null,
    reviewed_bbox: props.reviewedBbox || null,
    at_observation_id: props.observationId || null,
  };
}

async function submit({ setUnknown }) {
  if (!state.proposal.value) return;
  if (!setUnknown && !selectedTarget.value) return; // empty selection is not a correction
  let result;
  try {
    result = await actions.apply(buildPayload({ setUnknown }));
  } catch {
    return; // stale conflict re-proposes; other errors are notified
  }
  // Drive the async job to a terminal state; only then is the correction done.
  await actions.pollJob(result.revision_id).catch(() => {});
  if (state.job.value?.status === "completed") {
    emit("applied", result);
  }
}

async function onRetry() {
  const revisionId = state.job.value?.revision_id;
  if (revisionId) await actions.pollJob(revisionId).catch(() => {});
  if (state.job.value?.status === "completed") emit("applied", { revision_id: revisionId });
}
</script>
