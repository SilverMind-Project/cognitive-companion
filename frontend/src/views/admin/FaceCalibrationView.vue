<template>
  <div>
    <div class="d-flex align-center flex-wrap ga-3 mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Face calibration</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Label faces captured by the household cameras so face matches can be turned into a
          trustworthy probability. Unlabeled captures are deleted after 30 days.
        </div>
        <div class="text-caption mt-1">
          <router-link to="/admin/identity-setup" data-test="setup-link"
            >Step 3 of {{ IDENTITY_CHAIN_LENGTH }} in identity setup</router-link
          >
        </div>
      </div>
      <v-spacer />
      <CcSegmentedToggle
        :model-value="showAttested ? 'attested' : queueState"
        :options="QUEUE_STATE_OPTIONS"
        size="default"
        data-test="queue-state-toggle"
        @update:model-value="onQueueStateChange"
      />
      <v-chip
        v-if="state.summary"
        size="small"
        variant="tonal"
        :color="state.summary.capture_enabled ? 'success' : undefined"
        data-test="capture-chip"
      >
        Capture {{ state.summary.capture_enabled ? "on" : "off" }}
      </v-chip>
    </div>

    <AttestedFacesPanel
      v-if="showAttested"
      :audit="attested"
      :resident-name="residentName"
      :keys-enabled="!confirmDialog"
      @promote="onPromoteAttested"
    />

    <template v-else>
      <v-alert
        v-if="state.forbidden"
        type="warning"
        variant="tonal"
        class="mb-4"
        data-test="forbidden"
      >
        Labeling faces for calibration needs the face calibration review permission, which only
        caregiver admins hold.
      </v-alert>

      <v-alert v-if="state.error" type="error" variant="tonal" class="mb-4" data-test="load-error">
        {{ state.error }}
        <template #append>
          <v-btn size="small" variant="text" @click="actions.load">Retry</v-btn>
        </template>
      </v-alert>

      <ReviewSelectionToolbar
        v-if="
          queueState === 'unlabeled' && !state.loading && !state.forbidden && state.queue.length
        "
        class="mb-4"
        :active="state.selecting"
        :selectable-count="state.queue.length"
        :selected-count="state.selection.length"
        @update:active="actions.setSelecting"
        @select-all="actions.selectAll"
        @clear="actions.clearSelection"
      >
        <v-btn
          v-for="verdict in batchVerdicts"
          :key="verdict.verdict"
          size="small"
          variant="outlined"
          :disabled="!state.selection.length"
          :loading="state.acting"
          :data-test="`batch-${verdict.verdict}`"
          @click="onBatch(verdict.verdict)"
        >
          {{ VERDICT_LABELS[verdict.verdict] }}
        </v-btn>
        <span class="text-caption text-medium-emphasis">
          Members are labeled one face at a time.
        </span>
      </ReviewSelectionToolbar>

      <div v-if="state.loading" class="d-flex justify-center pa-8">
        <v-progress-circular indeterminate color="primary" />
      </div>

      <v-row
        v-else-if="!state.forbidden && state.selecting && state.queue.length"
        data-test="selection-grid"
      >
        <v-col v-for="capture in state.queue" :key="capture.candidate_id" cols="6" sm="3" md="2">
          <button
            type="button"
            class="calibration-tile"
            :class="{
              'calibration-tile--selected': state.selection.includes(capture.candidate_id),
            }"
            :aria-pressed="state.selection.includes(capture.candidate_id)"
            :data-test="`tile-${capture.candidate_id}`"
            @click="actions.toggleSelection(capture.candidate_id)"
          >
            <img
              v-if="capture.crop_url"
              :src="capture.crop_url"
              alt="Aligned face crop"
              class="calibration-tile__crop"
            />
            <span v-else class="text-caption">Crop unavailable</span>
          </button>
        </v-col>
      </v-row>

      <v-row v-else-if="!state.forbidden">
        <v-col cols="12" md="7">
          <v-card v-if="current" class="glass-card pa-4" data-test="current-capture">
            <div class="d-flex ga-4 flex-wrap">
              <img
                v-if="current.crop_url"
                :src="current.crop_url"
                alt="Aligned face crop"
                class="calibration-crop"
              />
              <div v-else class="calibration-crop d-flex align-center justify-center text-caption">
                Crop unavailable
              </div>
              <div class="text-body-2">
                <div><strong>Camera</strong> {{ current.camera_id }}</div>
                <div><strong>Captured</strong> {{ formatDateTime(current.captured_at) }}</div>
                <div><strong>Face quality</strong> {{ current.quality_score.toFixed(2) }}</div>
                <div v-if="current.pose_bin"><strong>Pose</strong> {{ current.pose_bin }}</div>
                <div>
                  <strong>Eye distance</strong>
                  {{
                    current.interocular_px == null
                      ? "unmeasured"
                      : `${current.interocular_px.toFixed(0)} px`
                  }}
                </div>
                <div>
                  <strong>Closest member</strong> {{ current.nearest_person_id ?? "none" }}
                  <span class="text-medium-emphasis">
                    (similarity {{ current.nearest_similarity.toFixed(2) }})
                  </span>
                </div>
                <div
                  v-if="queueState === 'labeled'"
                  class="d-flex align-center flex-wrap ga-2 mt-2"
                >
                  <v-chip size="small" variant="tonal" color="primary" data-test="label-chip">
                    {{ labelSummary(current) }}
                  </v-chip>
                  <v-chip
                    v-if="current.promoted"
                    size="small"
                    variant="tonal"
                    color="success"
                    data-test="promoted-chip"
                  >
                    Promoted
                  </v-chip>
                </div>
                <div class="text-medium-emphasis mt-2">
                  {{ state.index + 1 }} of {{ state.queue.length }}{{ state.nextCursor ? "+" : "" }}
                </div>
              </div>
            </div>

            <ReviewVerdictBar
              v-if="queueState === 'unlabeled'"
              class="mt-4"
              surface="face_calibration"
              :members="keyedResidents"
              :disabled="state.acting"
              @member="onMember"
              @verdict="onVerdict"
            />

            <div
              v-else-if="current.label_kind === 'member'"
              class="d-flex align-center flex-wrap ga-3 mt-4"
              data-test="promotion-bar"
            >
              <v-btn
                size="small"
                color="primary"
                variant="flat"
                :disabled="state.acting || current.promoted || !current.promotion_eligible"
                :loading="state.acting"
                :title="promotionReason(current)"
                data-test="promote"
                @click="onPromote"
              >
                Use for recognition
              </v-btn>
              <span
                v-if="promotionReason(current)"
                class="text-caption text-medium-emphasis"
                data-test="promotion-reason"
              >
                {{ promotionReason(current) }}
              </span>
            </div>
            <div class="d-flex ga-2 mt-3">
              <v-btn size="small" variant="text" :disabled="state.acting" @click="actions.previous"
                >Previous</v-btn
              >
              <v-btn size="small" variant="text" :disabled="state.acting" @click="actions.next">{{
                queueState === "labeled" ? "Next" : "Skip"
              }}</v-btn>
              <v-spacer />
              <v-btn
                v-if="queueState === 'unlabeled'"
                size="small"
                variant="text"
                :disabled="state.acting"
                title="Unusable for any purpose: the capture is set aside and deleted with the rest"
                data-test="reject"
                @click="actions.reject"
                >Reject capture</v-btn
              >
              <v-btn
                size="small"
                variant="text"
                color="error"
                :disabled="state.acting"
                data-test="delete"
                @click="onDelete"
              >
                Delete
              </v-btn>
            </div>
          </v-card>

          <v-card v-else flat class="pa-8 text-center glass-card" data-test="empty-queue">
            <v-card-text class="text-medium-emphasis text-h6">{{
              queueState === "labeled" ? "No labeled captures yet" : "Nothing waiting to be labeled"
            }}</v-card-text>
            <v-card-text
              v-if="captureOffNextAction"
              class="text-medium-emphasis"
              data-test="capture-next"
            >
              Capture is off, so there is nothing to label. Next:
              {{ captureOffNextAction }}.
              <router-link to="/admin/identity-setup">See identity setup</router-link>
            </v-card-text>
            <v-card-text v-else class="text-medium-emphasis">
              Captures appear here while calibration capture is switched on in the person
              identification service settings.
            </v-card-text>
          </v-card>
        </v-col>

        <v-col cols="12" md="5">
          <v-card v-if="state.summary" class="glass-card pa-4" data-test="progress">
            <div class="text-subtitle-1 font-weight-bold mb-2">Progress</div>
            <div
              v-for="identity in state.summary.identities"
              :key="identity.identity_id"
              class="mb-3"
            >
              <div class="d-flex text-body-2">
                <span>{{ residentName(identity.identity_id) }}</span>
                <v-spacer />
                <span
                  >{{ identity.labeled_faces }} / {{ identity.target_labeled_faces }} faces,
                  {{ identity.episodes }} walks</span
                >
              </div>
              <v-progress-linear
                :model-value="
                  Math.min(100, (100 * identity.labeled_faces) / identity.target_labeled_faces)
                "
                rounded
                height="6"
              />
            </div>
            <div class="text-body-2">
              Visitors (not enrolled): {{ state.summary.not_enrolled_episodes }} walks
            </div>
            <div class="text-caption text-medium-emphasis mt-2">
              Each resident needs many labeled faces across several separate walks, and some
              visitors must be labeled too, before calibration can be fitted.
            </div>
          </v-card>
        </v-col>
      </v-row>
    </template>

    <v-dialog v-model="confirmDialog" max-width="400" persistent>
      <v-card rounded="xl">
        <v-card-text class="pt-6">{{ confirmText }}</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="onCancel">{{ cancelLabel }}</v-btn>
          <v-btn :color="confirmColor" variant="flat" data-test="confirm" @click="onConfirm">{{
            confirmLabel
          }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import CcSegmentedToggle from "@/components/common/CcSegmentedToggle.vue";
import AttestedFacesPanel from "@/components/identity/AttestedFacesPanel.vue";
import { useAttestedFaceAudit } from "@/composables/useAttestedFaceAudit";
import ReviewSelectionToolbar from "@/components/identity/ReviewSelectionToolbar.vue";
import ReviewVerdictBar from "@/components/identity/ReviewVerdictBar.vue";
import { VERDICT_LABELS, type ReviewVerdict } from "@/constants/identityReview";
import { useReviewKeys } from "@/composables/useReviewKeys";
import { useIdentityReviewStore } from "@/stores/identityReview";
import { useConfirm } from "@/composables/useConfirm.js";
import {
  useFaceCalibrationReview,
  type CalibrationQueueState,
} from "@/composables/useFaceCalibrationReview";
import { useIdentityReadiness } from "@/composables/useIdentityReadiness";
import { ACTION_PRESENTATION, IDENTITY_CHAIN_LENGTH } from "@/constants/identityReadiness";
import { useNotify } from "@/composables/useNotify.js";
import { formatDateTime } from "@/services/timezone.js";
import type { CalibrationCandidateView } from "@/services/modules/face_calibration";

const QUEUE_STATE_OPTIONS = [
  { value: "unlabeled", label: "Unlabeled" },
  { value: "labeled", label: "Labeled" },
  { value: "attested", label: "Attested faces" },
];

const { notify } = useNotify();
const { state, current, keyedResidents, actions } = useFaceCalibrationReview(notify);
const queueState = computed<CalibrationQueueState>(() => state.queueState ?? "unlabeled");
// Faces a wearable labeled are audited apart from the labeling queue (they are machine labels).
const showAttested = ref(false);
const attested = useAttestedFaceAudit(notify);
const {
  confirmDialog,
  confirmText,
  confirmLabel,
  cancelLabel,
  confirmColor,
  require: confirmRequire,
  onConfirm,
  onCancel,
} = useConfirm();
// Readiness only adds a hint to the empty queue; if it fails to load the page works without it.
const readiness = useIdentityReadiness();

const captureOffNextAction = computed(() => {
  if (!state.summary || state.summary.capture_enabled) return "";
  const step = readiness.stepByKey.value.capture;
  if (!step || step.next_action === "none") return "";
  return ACTION_PRESENTATION[step.next_action].text;
});

function residentName(id: string): string {
  return state.residents.find((r) => r.identity_id === id)?.display_name ?? id;
}

function labelSummary(candidate: CalibrationCandidateView): string {
  if (candidate.label_kind === "member" && candidate.label_identity_id) {
    return residentName(candidate.label_identity_id);
  }
  if (candidate.label_kind === "not_enrolled") return "Not in household";
  if (candidate.label_kind === "not_a_face") return "Not usable";
  return candidate.label_state;
}

function promotionReason(candidate: CalibrationCandidateView): string {
  if (candidate.promoted) return "Already added to gallery.";
  if (!candidate.promotion_eligible) {
    return candidate.promotion_ineligible_reason ?? "Not eligible for promotion.";
  }
  return "";
}

function onQueueStateChange(nextState: string) {
  if (nextState === "attested") {
    showAttested.value = true;
    void attested.actions.load();
  } else if (nextState === "unlabeled" || nextState === "labeled") {
    showAttested.value = false;
    void actions.setQueueState(nextState);
  }
}

async function onPromoteAttested(face: CalibrationCandidateView) {
  const who = residentName(face.label_identity_id ?? "");
  const ok = await confirmRequire(
    `Add this ${face.pose_bin || "frontal"} face, which a wearable labeled as ${who}, to ${who}'s recognition gallery? Check that it really is ${who}. Calibrated recognition authority for ${who} will pause until the next calibration fit.`,
    { confirmText: "Use for recognition", color: "primary" },
  );
  if (ok) await attested.actions.promote(face.candidate_id);
}

async function onPromote() {
  const candidate = current.value;
  if (!candidate || !candidate.label_identity_id) return;
  const who = residentName(candidate.label_identity_id);
  const pose = candidate.pose_bin || "frontal";
  const ok = await confirmRequire(
    `Add this ${pose} capture to ${who}'s recognition gallery? Calibrated recognition authority for ${who} will pause until the next calibration fit.`,
    { confirmText: "Use for recognition", color: "primary" },
  );
  if (ok) {
    await actions.promote(candidate.candidate_id);
  }
}

async function onDelete() {
  const ok = await confirmRequire(
    "Delete this capture? The face crop and its calibration label are deleted permanently. If this capture was already promoted, its promoted embedding stays in the gallery.",
    { confirmText: "Delete" },
  );
  if (ok) {
    await actions.remove();
  }
}

// No member is highlighted here: these labels are ground truth for the calibration fit, and
// pointing at the closest match would bias the labeler toward the model's own guess.
function onMember(identityId: string) {
  const position = keyedResidents.value.findIndex((r) => r.identity_id === identityId);
  if (position >= 0) void actions.labelResident(position);
}

function onVerdict(verdict: ReviewVerdict) {
  if (verdict === "not_enrolled") void actions.labelNotEnrolled();
  else if (verdict === "not_usable") void actions.labelNotAFace();
}

const review = useIdentityReviewStore();
// The server says which verdicts may apply to several captures at once (never a member label).
const batchVerdicts = computed(
  () => review.surface("face_calibration")?.verdicts.filter((v) => v.batch) ?? [],
);

async function onBatch(verdict: ReviewVerdict) {
  if (verdict !== "not_enrolled" && verdict !== "not_usable") return;
  const n = state.selection.length;
  const ok = await confirmRequire(
    `Label ${n} face${n === 1 ? "" : "s"} "${VERDICT_LABELS[verdict]}"? ` +
      review.effect("face_calibration", verdict),
    { confirmText: VERDICT_LABELS[verdict], color: "primary" },
  );
  if (ok) await actions.reviewSelected(verdict);
}

useReviewKeys({
  enabled: () =>
    !showAttested.value &&
    queueState.value === "unlabeled" &&
    !confirmDialog.value &&
    !state.acting &&
    !state.selecting &&
    current.value !== null,
  verdicts: () => review.surface("face_calibration")?.verdicts.map((v) => v.verdict) ?? [],
  onMember: (position) => void actions.labelResident(position),
  onVerdict,
  onNext: actions.next,
  onPrevious: actions.previous,
});

onMounted(() => {
  void actions.load();
  void readiness.actions.load();
});
</script>

<style scoped>
.calibration-tile {
  display: block;
  width: 100%;
  aspect-ratio: 1;
  padding: 0;
  border: 2px solid transparent;
  border-radius: var(--cc-radius-md);
  background: var(--cc-surface-2);
  overflow: hidden;
  cursor: pointer;
}
.calibration-tile--selected {
  border-color: var(--cc-brand);
}
.calibration-tile__crop {
  width: 100%;
  height: 100%;
  object-fit: cover;
  image-rendering: pixelated;
}
.calibration-crop {
  width: 224px;
  height: 224px;
  border-radius: var(--cc-radius-md);
  background: var(--cc-surface-2);
  image-rendering: pixelated;
}
</style>
