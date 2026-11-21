<template>
  <div data-test="attested-faces">
    <v-alert type="info" variant="tonal" density="comfortable" class="mb-4">
      A wearable labeled these faces automatically: it placed a household member on the track the
      face came from. Judge a random sample so the labels can be trusted for calibration. Nothing
      here changes recognition unless you choose "Use for recognition" on a face.
    </v-alert>

    <v-alert
      v-if="state.forbidden"
      type="warning"
      variant="tonal"
      class="mb-4"
      data-test="attested-forbidden"
    >
      Auditing attested faces needs the face calibration review permission.
    </v-alert>
    <v-alert
      v-if="state.error"
      type="error"
      variant="tonal"
      class="mb-4"
      data-test="attested-error"
    >
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
        <v-card v-if="current" class="glass-card pa-4" data-test="audit-current">
          <div class="d-flex ga-4 flex-wrap">
            <img
              v-if="current.crop_url"
              :src="current.crop_url"
              alt="Aligned face crop"
              class="attested-crop"
            />
            <div v-else class="attested-crop d-flex align-center justify-center text-caption">
              Crop unavailable
            </div>
            <div class="text-body-2">
              <div>
                <strong>Wearable says</strong>
                {{ residentName(current.label_identity_id ?? "") }}
              </div>
              <div>
                <strong>How sure</strong>
                {{ GRADE_TEXT[current.attestation_grade ?? "room"] }}
              </div>
              <div><strong>Camera</strong> {{ current.camera_id }}</div>
              <div><strong>Captured</strong> {{ formatDateTime(current.captured_at) }}</div>
              <div><strong>Face quality</strong> {{ current.quality_score.toFixed(2) }}</div>
              <div class="text-medium-emphasis mt-2">
                {{ state.index + 1 }} of {{ state.sample.length }} in this sample
              </div>
            </div>
          </div>
          <div class="d-flex align-center flex-wrap ga-2 mt-4" data-test="audit-bar">
            <v-btn
              v-for="option in AUDIT_OPTIONS"
              :key="option.verdict"
              size="small"
              :variant="option.verdict === 'correct' ? 'flat' : 'outlined'"
              :color="option.verdict === 'correct' ? 'primary' : undefined"
              :disabled="state.acting"
              :data-test="`audit-${option.verdict}`"
              @click="actions.audit(option.verdict)"
            >
              {{ option.label }} <kbd class="ml-2">{{ option.key }}</kbd>
            </v-btn>
          </div>
          <div class="text-caption text-medium-emphasis mt-2">
            An audit records whether the label is right. It changes no label, gallery, or
            recognition.
          </div>
          <div class="d-flex ga-2 mt-3">
            <v-btn size="small" variant="text" :disabled="state.acting" @click="actions.previous">
              Previous
            </v-btn>
            <v-btn size="small" variant="text" :disabled="state.acting" @click="actions.next">
              Skip
            </v-btn>
          </div>
        </v-card>
        <v-card v-else flat class="pa-8 text-center glass-card" data-test="audit-empty">
          <v-card-text class="text-grey text-h6">Nothing waiting to be audited</v-card-text>
          <v-card-text class="text-grey">
            Attested faces appear while wearables are in use and face attestation is switched on.
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" md="5">
        <v-card v-if="state.summary" class="glass-card pa-4" data-test="audit-summary">
          <div class="text-subtitle-1 font-weight-bold mb-2">Audit</div>
          <div class="text-body-2">
            {{ state.summary.audited }} of {{ state.summary.attested }} attested faces audited:
            {{ state.summary.correct }} right, {{ state.summary.wrong }} wrong,
            {{ state.summary.not_a_face }} not a face.
          </div>
          <div class="text-body-2 mt-1" data-test="audit-bound">
            Precision at least {{ boundText }}
            <span class="text-medium-emphasis"
              >(needed: {{ state.summary.min_audited }} audited and
              {{ percent(state.summary.min_precision_lower_bound) }})</span
            >
          </div>
          <v-progress-linear
            class="mt-2"
            :model-value="Math.min(100, (100 * state.summary.audited) / state.summary.min_audited)"
            rounded
            height="6"
          />
          <v-chip
            class="mt-3"
            size="small"
            variant="tonal"
            :color="state.summary.meets_bar ? 'success' : undefined"
            data-test="audit-bar-chip"
          >
            {{
              state.summary.meets_bar
                ? "Labels may be used for calibration"
                : "Not yet trusted for calibration"
            }}
          </v-chip>
        </v-card>
      </v-col>
    </v-row>

    <template v-if="!state.loading && !state.forbidden && state.exemplars.length">
      <div class="text-subtitle-1 font-weight-bold mt-6 mb-2">Best attested faces</div>
      <v-row data-test="exemplar-grid">
        <v-col
          v-for="face in state.exemplars"
          :key="face.candidate_id"
          cols="6"
          sm="3"
          md="2"
          :data-test="`exemplar-${face.candidate_id}`"
        >
          <img v-if="face.crop_url" :src="face.crop_url" alt="Aligned face crop" class="tile" />
          <div class="text-caption mt-1">
            {{ residentName(face.label_identity_id ?? "") }}, {{ face.pose_bin }}
          </div>
          <v-btn
            size="x-small"
            variant="tonal"
            color="primary"
            class="mt-1"
            :disabled="state.acting || face.promoted || !face.promotion_eligible"
            :title="face.promotion_ineligible_reason ?? ''"
            :data-test="`promote-${face.candidate_id}`"
            @click="emit('promote', face)"
          >
            {{ face.promoted ? "In gallery" : "Use for recognition" }}
          </v-btn>
        </v-col>
      </v-row>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from "vue";
import type { useAttestedFaceAudit } from "@/composables/useAttestedFaceAudit";
import type {
  AttestationAuditVerdict,
  CalibrationCandidateView,
} from "@/services/modules/face_calibration";
import { formatDateTime } from "@/services/timezone.js";

type Audit = ReturnType<typeof useAttestedFaceAudit>;

const props = defineProps<{
  audit: Audit;
  residentName: (identityId: string) => string;
  /** Suspends the keyboard while a confirm dialog is open. */
  keysEnabled: boolean;
}>();
const emit = defineEmits<{ promote: [face: CalibrationCandidateView] }>();

const state = props.audit.state;
const current = props.audit.current;
const actions = props.audit.actions;

const AUDIT_OPTIONS: { verdict: AttestationAuditVerdict; label: string; key: string }[] = [
  { verdict: "correct", label: "Right person", key: "c" },
  { verdict: "wrong", label: "Wrong person", key: "w" },
  { verdict: "not_a_face", label: "Not a face", key: "x" },
];
const GRADE_TEXT: Record<"room" | "trajectory", string> = {
  trajectory: "The wearable's path matched this person's path",
  room: "This person was alone in the room with the wearable",
};

function percent(value: number): string {
  return `${(100 * value).toFixed(1)}%`;
}

const boundText = computed(() => {
  const bound = state.summary?.precision_lower_bound;
  return bound == null ? "unknown (no audits yet)" : percent(bound);
});

function onKey(event: KeyboardEvent) {
  if (!props.keysEnabled || state.acting || !current.value) return;
  const target = event.target as HTMLElement | null;
  if (target && ["INPUT", "TEXTAREA"].includes(target.tagName)) return;
  const option = AUDIT_OPTIONS.find((o) => o.key === event.key);
  if (option) {
    event.preventDefault();
    void actions.audit(option.verdict);
  } else if (event.key === "ArrowRight") {
    actions.next();
  } else if (event.key === "ArrowLeft") {
    actions.previous();
  }
}

onMounted(() => window.addEventListener("keydown", onKey));
onBeforeUnmount(() => window.removeEventListener("keydown", onKey));
</script>

<style scoped>
.attested-crop {
  width: 224px;
  height: 224px;
  border-radius: var(--cc-radius-md);
  background: var(--cc-surface-2);
  image-rendering: pixelated;
}
.tile {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  border-radius: var(--cc-radius-md);
  background: var(--cc-surface-2);
  image-rendering: pixelated;
}
</style>
