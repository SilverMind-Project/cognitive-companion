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

    <div v-if="state.loading" class="d-flex justify-center pa-8">
      <v-progress-circular indeterminate color="primary" />
    </div>

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
              <div class="text-medium-emphasis mt-2">
                {{ state.index + 1 }} of {{ state.queue.length }}{{ state.nextCursor ? "+" : "" }}
              </div>
            </div>
          </div>

          <ReviewVerdictBar
            class="mt-4"
            surface="face_calibration"
            :members="keyedResidents"
            :disabled="state.acting"
            @member="onMember"
            @verdict="onVerdict"
          />
          <div class="d-flex ga-2 mt-3">
            <v-btn size="small" variant="text" :disabled="state.acting" @click="actions.previous"
              >Previous</v-btn
            >
            <v-btn size="small" variant="text" :disabled="state.acting" @click="actions.next"
              >Skip</v-btn
            >
            <v-spacer />
            <v-btn
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
          <v-card-text class="text-grey text-h6">Nothing waiting to be labeled</v-card-text>
          <v-card-text v-if="captureOffNextAction" class="text-grey" data-test="capture-next">
            Capture is off, so there is nothing to label. Next:
            {{ captureOffNextAction }}.
            <router-link to="/admin/identity-setup">See identity setup</router-link>
          </v-card-text>
          <v-card-text v-else class="text-grey">
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
            Each resident needs many labeled faces across several separate walks, and some visitors
            must be labeled too, before calibration can be fitted.
          </div>
        </v-card>
      </v-col>
    </v-row>

    <v-dialog v-model="confirmDialog" max-width="400" persistent>
      <v-card rounded="xl">
        <v-card-title>{{ confirmTitle }}</v-card-title>
        <v-card-text>{{ confirmText }}</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="onCancel">Cancel</v-btn>
          <v-btn color="error" data-test="confirm-delete" @click="onConfirm">Delete</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from "vue";
import ReviewVerdictBar from "@/components/identity/ReviewVerdictBar.vue";
import type { ReviewVerdict } from "@/constants/identityReview";
import { useReviewKeys } from "@/composables/useReviewKeys";
import { useIdentityReviewStore } from "@/stores/identityReview";
import { useConfirm } from "@/composables/useConfirm.js";
import { useFaceCalibrationReview } from "@/composables/useFaceCalibrationReview";
import { useIdentityReadiness } from "@/composables/useIdentityReadiness";
import { ACTION_PRESENTATION, IDENTITY_CHAIN_LENGTH } from "@/constants/identityReadiness";
import { useNotify } from "@/composables/useNotify.js";
import { formatDateTime } from "@/services/timezone.js";

const { notify } = useNotify();
const { state, current, keyedResidents, actions } = useFaceCalibrationReview(notify);
const { confirmDialog, confirmTitle, confirmText, showConfirm, onConfirm, onCancel } = useConfirm();
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

async function onDelete() {
  if (await showConfirm("Delete capture", "The face crop and its label are deleted permanently.")) {
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
useReviewKeys({
  enabled: () => !confirmDialog.value && !state.acting && current.value !== null,
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
.calibration-crop {
  width: 224px;
  height: 224px;
  border-radius: var(--cc-radius-md);
  background: var(--cc-surface-2);
  image-rendering: pixelated;
}
</style>
