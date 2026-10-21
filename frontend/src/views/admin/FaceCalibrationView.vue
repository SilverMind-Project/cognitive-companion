<template>
  <div>
    <div class="d-flex align-center flex-wrap ga-3 mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Face calibration</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Label faces captured by the household cameras so face matches can be turned into a
          trustworthy probability. Unlabeled captures are deleted after 30 days.
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

          <div class="d-flex flex-wrap ga-2 mt-4">
            <v-btn
              v-for="(resident, position) in keyedResidents"
              :key="resident.id"
              size="small"
              variant="tonal"
              :disabled="state.acting"
              :data-test="`resident-${resident.id}`"
              @click="actions.labelResident(position)"
            >
              <kbd class="mr-2">{{ position + 1 }}</kbd
              >{{ resident.name }}
            </v-btn>
            <v-btn
              size="small"
              variant="tonal"
              :disabled="state.acting"
              data-test="not-enrolled"
              @click="actions.labelNotEnrolled"
            >
              <kbd class="mr-2">n</kbd>Not enrolled
            </v-btn>
            <v-btn
              size="small"
              variant="tonal"
              :disabled="state.acting"
              data-test="not-a-face"
              @click="actions.labelNotAFace"
            >
              <kbd class="mr-2">x</kbd>Not a face
            </v-btn>
          </div>
          <div class="d-flex ga-2 mt-3">
            <v-btn size="small" variant="text" :disabled="state.acting" @click="actions.previous"
              >Previous</v-btn
            >
            <v-btn size="small" variant="text" :disabled="state.acting" @click="actions.next"
              >Skip</v-btn
            >
            <v-spacer />
            <v-btn size="small" variant="text" :disabled="state.acting" @click="actions.reject"
              >Unusable</v-btn
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
          <div class="text-caption text-medium-emphasis mt-2">
            Keys: number for a resident, n for someone not enrolled, x for not a face, arrows to
            move.
          </div>
        </v-card>

        <v-card v-else flat class="pa-8 text-center glass-card" data-test="empty-queue">
          <v-card-text class="text-grey text-h6">Nothing waiting to be labeled</v-card-text>
          <v-card-text class="text-grey">
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

    <v-dialog v-model="confirmDialog" max-width="400">
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
import { onBeforeUnmount, onMounted } from "vue";
import { useConfirm } from "@/composables/useConfirm.js";
import { useFaceCalibrationReview } from "@/composables/useFaceCalibrationReview";
import { useNotify } from "@/composables/useNotify.js";
import { formatDateTime } from "@/services/timezone.js";

const { notify } = useNotify();
const { state, current, keyedResidents, actions } = useFaceCalibrationReview(notify);
const { confirmDialog, confirmTitle, confirmText, showConfirm, onConfirm, onCancel } = useConfirm();

function residentName(id: string): string {
  return state.residents.find((r) => r.id === id)?.name ?? id;
}

async function onDelete() {
  if (await showConfirm("Delete capture", "The face crop and its label are deleted permanently.")) {
    await actions.remove();
  }
}

function onKeydown(event: KeyboardEvent) {
  const target = event.target as HTMLElement | null;
  if (confirmDialog.value || event.ctrlKey || event.metaKey || event.altKey) return;
  if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
  const key = event.key;
  if (/^[1-9]$/.test(key)) {
    void actions.labelResident(Number(key) - 1);
  } else if (key === "n") {
    void actions.labelNotEnrolled();
  } else if (key === "x") {
    void actions.labelNotAFace();
  } else if (key === "ArrowRight") {
    actions.next();
  } else if (key === "ArrowLeft") {
    actions.previous();
  } else {
    return;
  }
  event.preventDefault();
}

onMounted(() => {
  window.addEventListener("keydown", onKeydown);
  void actions.load();
});
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown));
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
