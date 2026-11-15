<template>
  <div class="reid-review">
    <div class="d-flex align-center flex-wrap ga-3 mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">ReID Review Queue</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Verify body-appearance samples before they help recognize household members.
        </div>
      </div>
      <v-spacer />
      <BlurToggle />
      <v-btn
        variant="tonal"
        prepend-icon="mdi-refresh"
        :loading="state.listLoading.value"
        @click="refreshAll"
      >
        Refresh
      </v-btn>
    </div>

    <!-- Forbidden -->
    <v-alert v-if="forbidden" type="error" variant="tonal" class="mb-4">
      You do not have the gallery-review permission. This surface requires
      <code>cts.identity.gallery_review</code>, which is separate from identity correction.
    </v-alert>

    <template v-else>
      <!-- Lifecycle state picker (with queue counts) and filters -->
      <div class="d-flex align-center flex-wrap ga-3 mb-4">
        <CcSegmentedToggle
          :model-value="state.filters.value.state"
          :options="stateOptions"
          @update:model-value="(v) => actions.setFilter('state', v)"
        />
        <v-chip
          v-if="state.countsError.value"
          size="small"
          color="warning"
          variant="tonal"
          prepend-icon="mdi-alert-outline"
          :title="state.countsError.value"
        >
          Counts unavailable
        </v-chip>
        <v-spacer />
        <v-text-field
          :model-value="state.filters.value.identity_id"
          placeholder="Identity"
          aria-label="Filter by identity"
          prepend-inner-icon="mdi-account-outline"
          variant="outlined"
          density="compact"
          hide-details
          clearable
          class="filter-control"
          @update:model-value="(v) => actions.setFilter('identity_id', v || null)"
        />
        <v-text-field
          :model-value="state.filters.value.camera_id"
          placeholder="Camera"
          aria-label="Filter by camera"
          prepend-inner-icon="mdi-cctv"
          variant="outlined"
          density="compact"
          hide-details
          clearable
          class="filter-control"
          @update:model-value="(v) => actions.setFilter('camera_id', v || null)"
        />
        <v-text-field
          :model-value="state.filters.value.model_version"
          placeholder="Model version"
          aria-label="Filter by model version"
          prepend-inner-icon="mdi-tag-outline"
          variant="outlined"
          density="compact"
          hide-details
          clearable
          class="filter-control"
          @update:model-value="(v) => actions.setFilter('model_version', v || null)"
        />
      </div>

      <!-- Batch decisions: negative verdicts only; approval needs individual visual review -->
      <ReviewSelectionToolbar
        class="mb-3"
        :active="selectMode"
        :selectable-count="selectableIds.length"
        :selected-count="state.selectedIds.value.length"
        @update:active="toggleSelectMode"
        @select-all="selectAllPending"
        @clear="actions.clearSelection()"
      >
        <v-btn
          size="small"
          variant="outlined"
          prepend-icon="mdi-account-off-outline"
          :disabled="!state.selectedIds.value.length"
          :loading="state.acting.value"
          data-test="batch-not-enrolled"
          @click="confirmBatchNotEnrolled"
        >
          {{ VERDICT_LABELS.not_enrolled }}
        </v-btn>
        <v-btn
          size="small"
          variant="outlined"
          prepend-icon="mdi-close-circle-outline"
          :disabled="!state.selectedIds.value.length"
          :loading="state.acting.value"
          data-test="batch-not-usable"
          @click="openBatchReject"
        >
          {{ VERDICT_LABELS.not_usable }}
        </v-btn>
      </ReviewSelectionToolbar>

      <v-alert v-if="state.listError.value" type="error" variant="tonal" class="mb-3">
        {{ state.listError.value }}
        <template #append>
          <v-btn size="small" variant="text" @click="refreshAll">Retry</v-btn>
        </template>
      </v-alert>

      <v-card class="glass-card">
        <v-table density="comfortable">
          <thead>
            <tr>
              <th v-if="selectMode" style="width: 44px"></th>
              <th>State</th>
              <th>Pending age</th>
              <th>Proposed identity</th>
              <th>Camera / time</th>
              <th>Quality</th>
              <th>Orientation</th>
              <th>Model</th>
              <th>Source</th>
              <th class="text-right">Review</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="state.listLoading.value && !state.candidates.value.length">
              <td :colspan="columnCount" class="text-center py-8">
                <v-progress-circular indeterminate size="28" />
              </td>
            </tr>
            <tr v-else-if="!state.candidates.value.length">
              <td :colspan="columnCount" class="text-center py-10">
                <template v-if="queueEmpty">
                  <v-icon size="40" color="medium-emphasis" class="mb-2">
                    mdi-account-search-outline
                  </v-icon>
                  <div class="text-body-1 font-weight-medium mb-1">The review queue is empty</div>
                  <div class="text-body-2 text-medium-emphasis empty-explainer mx-auto">
                    The tracking system proposes a body-appearance sample only when a calibrated
                    face match confirms the person a track is already following. Samples appear here
                    as household members are recognized by face on camera.
                  </div>
                  <div
                    v-if="calibratedFacesNotLive"
                    class="text-body-2 empty-explainer mx-auto mt-2"
                    data-test="not-proposable"
                  >
                    Calibrated faces are not live yet, so no samples can be proposed.
                    <router-link to="/admin/identity-setup">See identity setup</router-link>
                  </div>
                </template>
                <span v-else class="text-medium-emphasis">
                  No candidates match the current filters.
                </span>
              </td>
            </tr>
            <tr
              v-for="c in state.candidates.value"
              :key="c.candidate_id"
              class="row-clickable"
              @click="actions.openDetail(c.candidate_id)"
            >
              <td v-if="selectMode" @click.stop>
                <v-checkbox
                  :model-value="state.selected.value.has(c.candidate_id)"
                  density="compact"
                  hide-details
                  :disabled="c.state !== 'pending_review'"
                  @update:model-value="actions.toggleSelected(c.candidate_id)"
                />
              </td>
              <td>
                <v-chip size="x-small" :color="stateColor(c.state)" variant="tonal">
                  {{ stateLabel(c.state) }}
                </v-chip>
              </td>
              <td>{{ relativeAge(c.created_at || c.seen_at) }}</td>
              <td>{{ c.proposed_identity_id || c.identity_id || "Unknown" }}</td>
              <td>
                <div class="text-body-2">{{ c.camera_id || "-" }}</div>
                <div class="text-caption text-medium-emphasis">{{ fmt(c.capture_time) }}</div>
              </td>
              <td>{{ pct(c.quality) }}</td>
              <td>{{ orientationLabel(c.orientation) }}</td>
              <td>
                <span :class="{ 'text-error': c.model_version && !modelOk(c) }">
                  {{ c.model_version || "-" }}
                </span>
              </td>
              <td>{{ c.candidate_reason || "-" }}</td>
              <td class="text-right" @click.stop>
                <v-btn
                  icon="mdi-eye-outline"
                  size="x-small"
                  variant="text"
                  title="Review candidate"
                  @click="actions.openDetail(c.candidate_id)"
                />
              </td>
            </tr>
          </tbody>
        </v-table>
      </v-card>

      <div class="d-flex justify-center mt-4">
        <v-pagination
          :model-value="state.page.value"
          :length="state.pageCount.value"
          :total-visible="7"
          density="comfortable"
          @update:model-value="actions.goToPage"
        />
      </div>
    </template>

    <!-- Detail drawer -->
    <v-navigation-drawer
      :model-value="!!state.detail.value || state.detailLoading.value"
      location="right"
      temporary
      width="640"
      class="cc-drawer-right"
      @update:model-value="(v) => !v && actions.closeDetail()"
    >
      <div class="h-100 d-flex flex-column">
        <div class="d-flex align-center px-4 py-3">
          <span class="text-subtitle-1 font-weight-semibold">Candidate</span>
          <v-chip
            v-if="detailCandidate.state"
            size="x-small"
            :color="stateColor(detailCandidate.state)"
            variant="tonal"
            class="ml-2"
          >
            {{ stateLabel(detailCandidate.state) }}
          </v-chip>
          <v-spacer />
          <v-btn icon="mdi-close" size="small" variant="text" @click="actions.closeDetail()" />
        </div>
        <v-divider />
        <div class="flex-grow-1 overflow-y-auto" style="min-height: 0">
          <div v-if="state.detailLoading.value" class="pa-8 text-center">
            <v-progress-circular indeterminate />
          </div>
          <div v-else-if="state.detailError.value" class="pa-4">
            <v-alert type="error" variant="tonal">{{ state.detailError.value }}</v-alert>
          </div>
          <div v-else-if="state.detail.value" class="pa-4">
            <!-- Eligibility -->
            <v-alert
              :type="!isReviewable ? 'info' : eligibility.eligible ? 'success' : 'warning'"
              variant="tonal"
              density="compact"
              class="mb-3"
            >
              <template v-if="!isReviewable">
                Already reviewed: {{ detailCandidate.state }}.
              </template>
              <template v-else-if="detailCandidate.state === 'auto_verified'">
                Auto-verified by a calibrated face match; already voting at reduced trust. Approve
                to fully verify, or demote to un-trust it back to pending review.
              </template>
              <template v-else-if="eligibility.eligible">Eligible for approval.</template>
              <template v-else>
                Not eligible for approval: {{ eligibility.reasons.join(", ") }}.
              </template>
            </v-alert>

            <!-- Body crop -->
            <div class="mb-3">
              <div class="text-overline">Body crop</div>
              <img
                v-if="detailCandidate.crop_url"
                :src="displaySrc(detailCandidate.crop_url)"
                class="crop-img"
                alt="Candidate crop"
              />
              <div v-else class="deleted-crop text-medium-emphasis">
                Crop deleted (rejected candidate). Audit metadata retained.
              </div>
            </div>

            <!-- Full frame with bbox -->
            <div v-if="detailCandidate.frame_url" class="mb-3">
              <div class="text-overline">Source frame</div>
              <IdentityBboxOverlay
                :image-url="detailCandidate.frame_url"
                :bboxes="frameBboxes"
                :selectable="false"
              />
            </div>

            <!-- Provenance -->
            <div class="text-overline">Provenance</div>
            <v-table density="compact" class="mb-3 prov-table">
              <tbody>
                <tr>
                  <td>Proposed identity</td>
                  <td>{{ detailCandidate.proposed_identity_id || "-" }}</td>
                </tr>
                <tr>
                  <td>Effective identity</td>
                  <td>{{ detailCandidate.effective_identity_id || "Unknown" }}</td>
                </tr>
                <tr>
                  <td>Label source</td>
                  <td>{{ detailCandidate.label_source || "-" }}</td>
                </tr>
                <tr>
                  <td>Candidate reason</td>
                  <td>{{ detailCandidate.candidate_reason || "-" }}</td>
                </tr>
                <tr>
                  <td>Crop quality</td>
                  <td>{{ pct(detailCandidate.quality) }}</td>
                </tr>
                <tr>
                  <td>Dimensions</td>
                  <td>
                    {{ detailCandidate.crop_width || "?" }} x
                    {{ detailCandidate.crop_height || "?" }}
                  </td>
                </tr>
                <tr>
                  <td>Truncation / occlusion</td>
                  <td>
                    {{ detailCandidate.is_truncated ? "truncated" : "ok" }} /
                    {{ detailCandidate.is_occluded ? "occluded" : "ok" }}
                  </td>
                </tr>
                <tr>
                  <td>Orientation</td>
                  <td>{{ orientationLabel(detailCandidate.orientation) }}</td>
                </tr>
                <tr>
                  <td>Model / preprocessing</td>
                  <td>
                    {{ detailCandidate.model_version || "-" }} /
                    {{ detailCandidate.preprocessing_version || "-" }}
                  </td>
                </tr>
                <tr>
                  <td>Camera</td>
                  <td>{{ detailCandidate.camera_id || "-" }}</td>
                </tr>
                <tr>
                  <td>Captured</td>
                  <td>{{ fmt(detailCandidate.capture_time) }}</td>
                </tr>
                <tr>
                  <td>Source PH</td>
                  <td class="mono">{{ detailCandidate.ph_id || "-" }}</td>
                </tr>
                <tr>
                  <td>Observation</td>
                  <td class="mono">{{ detailCandidate.observation_id || "-" }}</td>
                </tr>
                <tr>
                  <td>Keyframe</td>
                  <td class="mono">{{ detailCandidate.keyframe_id || "-" }}</td>
                </tr>
              </tbody>
            </v-table>

            <!-- Nearby observations from the same PH segment -->
            <div v-if="neighbors.length" class="mb-3">
              <div class="text-overline">Nearby observations (same PH)</div>
              <v-chip
                v-for="o in neighbors"
                :key="o.observation_id"
                size="x-small"
                variant="outlined"
                class="ma-1"
                :title="fmt(o.captured_at)"
              >
                {{ o.camera_id }} {{ fmtShort(o.captured_at) }}
              </v-chip>
            </div>

            <!-- Review history -->
            <div class="text-overline">Review history</div>
            <v-timeline v-if="detailEvents.length" density="compact" side="end" class="mb-3">
              <v-timeline-item
                v-for="ev in detailEvents"
                :key="ev.event_id"
                size="x-small"
                :dot-color="
                  ev.new_state === 'rejected'
                    ? 'error'
                    : ev.new_state === 'operator_verified'
                      ? 'success'
                      : ev.new_state === 'auto_verified'
                        ? 'info'
                        : 'grey'
                "
              >
                <div class="text-body-2">{{ ev.previous_state }} &rarr; {{ ev.new_state }}</div>
                <div class="text-caption text-medium-emphasis">
                  {{ ev.actor }} - {{ fmt(ev.event_time) }}
                  <template v-if="ev.reason"> - {{ ev.reason }}</template>
                </div>
              </v-timeline-item>
            </v-timeline>
            <div v-else class="text-caption text-medium-emphasis mb-3">No review actions yet.</div>

            <!-- Actions -->
            <div v-if="isReviewable">
              <v-divider class="mb-3" />
              <div class="text-overline">Whose body is this?</div>
              <ReviewVerdictBar
                surface="reid_review"
                :members="state.targets.value"
                :proposed-id="proposedId"
                :disabled="state.acting.value"
                :members-disabled="!eligibility.eligible"
                :members-disabled-reason="
                  eligibility.eligible
                    ? ''
                    : `Not eligible for approval: ${eligibility.reasons.join(', ')}.`
                "
                :navigable="false"
                @member="confirmMember"
                @verdict="onVerdict"
              >
                <v-btn
                  v-if="detailCandidate.state === 'auto_verified'"
                  size="small"
                  variant="text"
                  prepend-icon="mdi-undo"
                  :disabled="state.acting.value"
                  :loading="state.acting.value"
                  title="Un-trust this auto-verified candidate back to pending review"
                  data-test="demote"
                  @click="confirmDemote"
                >
                  Demote
                </v-btn>
              </ReviewVerdictBar>
              <div
                v-if="eligibility.eligible && state.targets.value.length > MAX_KEYED_MEMBERS"
                class="pa-2"
              >
                <IdentityTargetPicker
                  v-model="relabelTarget"
                  label="Someone else in the household"
                  density="compact"
                  hide-details
                  class="mb-2"
                />
                <v-btn
                  size="small"
                  :disabled="!relabelTarget"
                  @click="confirmMember(relabelTarget)"
                >
                  Verify as this member
                </v-btn>
              </div>
              <v-expand-transition>
                <div v-if="showReject" class="pa-2" data-test="reject-panel">
                  <v-select
                    v-model="rejectReason"
                    label="Why is it not usable?"
                    :items="UNUSABLE_REASONS"
                    density="compact"
                    hide-details
                    class="mb-2"
                  />
                  <v-textarea
                    v-model="rejectNote"
                    label="Note (optional)"
                    density="compact"
                    hide-details
                    rows="2"
                    class="mb-2"
                  />
                  <v-btn
                    size="small"
                    color="error"
                    :disabled="!rejectReason"
                    data-test="confirm-unusable"
                    @click="confirmUnusable"
                  >
                    Reject as not usable
                  </v-btn>
                </div>
              </v-expand-transition>
            </div>
            <!-- Compensating action for a verified candidate -->
            <div v-else-if="detailCandidate.state === 'operator_verified'">
              <v-divider class="mb-3" />
              <v-btn
                size="small"
                variant="outlined"
                prepend-icon="mdi-undo"
                :loading="state.acting.value"
                @click="confirmCompensate"
              >
                Undo verification
              </v-btn>
            </div>
          </div>
        </div>
      </div>
    </v-navigation-drawer>

    <!-- Batch reject dialog -->
    <AppDialog
      v-model="batchDialog"
      size="sm"
      persistent
      icon="mdi-close-circle-outline"
      label="Not usable"
      :title="`Reject ${state.selectedIds.value.length} samples as not usable`"
      confirm-label="Reject"
      confirm-color="error"
      :confirm-disabled="!batchReason"
      :confirm-loading="state.acting.value"
      @confirm="doBatchReject"
    >
      <div class="px-6 py-5">
        <p class="text-body-2 text-medium-emphasis mb-3" data-test="batch-effect">
          {{ review.effect("reid_review", "not_usable") }}
        </p>
        <v-select
          v-model="batchReason"
          label="Why are they not usable?"
          :items="UNUSABLE_REASONS"
          class="mb-3"
        />
        <v-textarea v-model="batchNote" label="Note (optional)" rows="2" />
      </div>
    </AppDialog>

    <!-- Confirmation dialog for approve / relabel -->
    <v-dialog v-model="confirmDialog" max-width="400" persistent>
      <v-card rounded="xl">
        <v-card-title v-if="confirmTitle">{{ confirmTitle }}</v-card-title>
        <v-card-text>{{ confirmText }}</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="onCancel">{{ cancelLabel }}</v-btn>
          <v-btn :color="confirmColor" @click="onConfirm">{{ confirmLabel }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useReIDReview } from "@/composables/useReIDReview";
import { useIdentityReadiness } from "@/composables/useIdentityReadiness";
import { useNotify } from "@/composables/useNotify";
import { useConfirm } from "@/composables/useConfirm";
import { useBlurMode, useDisplaySrc } from "@/composables/useBlurMode";
import { CorrectionError } from "@/services/cts_identity";
import { ctsPh } from "@/services/cts_ph";
import { formatDateTime, formatDateTimeShort } from "@/services/timezone";
import AppDialog from "@/components/common/AppDialog.vue";
import CcSegmentedToggle from "@/components/common/CcSegmentedToggle.vue";
import BlurToggle from "@/components/cts/BlurToggle.vue";
import IdentityBboxOverlay from "@/components/cts/identity/IdentityBboxOverlay.vue";
import IdentityTargetPicker from "@/components/identity/IdentityTargetPicker.vue";
import ReviewSelectionToolbar from "@/components/identity/ReviewSelectionToolbar.vue";
import ReviewVerdictBar from "@/components/identity/ReviewVerdictBar.vue";
import { MAX_KEYED_MEMBERS, VERDICT_LABELS } from "@/constants/identityReview";
import { useReviewKeys } from "@/composables/useReviewKeys";
import { useIdentityReviewStore } from "@/stores/identityReview";

// "Not in the household" is CTS's wrong_person; "Not usable" asks which kind of unusable,
// because CTS records a reason code on every rejection.
const NOT_ENROLLED_REASON = "wrong_person";
const UNUSABLE_REASONS = [
  { title: "Low quality", value: "low_quality" },
  { title: "Bad box", value: "bad_bbox" },
  { title: "Identity uncertain", value: "identity_uncertain" },
  { title: "Duplicate sample", value: "duplicate_candidate" },
  { title: "Other", value: "other" },
];
const DEFAULT_UNUSABLE_REASON = "low_quality";
const ORIENTATIONS = ["back", "left", "front", "right", "unknown"];

const { notify } = useNotify();
const { state, actions } = useReIDReview(notify);
const {
  confirmDialog,
  confirmTitle,
  confirmText,
  confirmLabel,
  cancelLabel,
  confirmColor,
  showConfirm,
  onConfirm,
  onCancel,
} = useConfirm();
const { blurMode } = useBlurMode();
const { displaySrc } = useDisplaySrc(blurMode);

const forbidden = ref(false);
const neighbors = ref([]);
const showReject = ref(false);
const relabelTarget = ref("");
const rejectReason = ref("");
const rejectNote = ref("");
const batchDialog = ref(false);
const batchReason = ref("");
const batchNote = ref("");

const STATE_LABELS = {
  pending_review: "Pending",
  auto_verified: "Auto-verified",
  operator_verified: "Verified",
  rejected: "Rejected",
};
const STATE_COLORS = {
  pending_review: "warning",
  auto_verified: "info",
  operator_verified: "success",
  rejected: undefined,
};
const STATE_ORDER = ["pending_review", "auto_verified", "operator_verified", "rejected"];

const countsKnown = computed(() => state.countsLoaded.value && !state.countsError.value);

// Counts appear only once known: a placeholder zero must never pass for a real one.
const stateOptions = computed(() =>
  STATE_ORDER.map((value) => ({
    value,
    label: countsKnown.value
      ? `${STATE_LABELS[value]} · ${state.counts.value[value] ?? 0}`
      : STATE_LABELS[value],
  })),
);

// Readiness only explains an empty queue; if it fails to load, the queue works without it.
const readiness = useIdentityReadiness();
const calibratedFacesNotLive = computed(() => {
  const steps = readiness.stepByKey.value;
  if (!steps.artifact || !steps.face_policy) return false;
  return steps.artifact.state !== "ready" || steps.face_policy.state !== "ready";
});

// Counts span every state, so all-zero means nothing has ever been proposed (not a filter miss).
const queueEmpty = computed(
  () => countsKnown.value && STATE_ORDER.every((value) => (state.counts.value[value] ?? 0) === 0),
);

const detailCandidate = computed(() => state.detail.value?.candidate || {});
const detailEvents = computed(() => state.detail.value?.events || []);
const eligibility = computed(
  () => state.detail.value?.eligibility || { eligible: false, model_compatible: true, reasons: [] },
);
// Mirrors the server's REVIEWABLE_STATES: pending_review and auto_verified
// both accept approve/relabel/reject; only the terminal states do not.
const isReviewable = computed(() =>
  ["pending_review", "auto_verified"].includes(detailCandidate.value.state),
);
const frameBboxes = computed(() => {
  const c = detailCandidate.value;
  if (!c.bbox) return [];
  return [{ ...c.bbox, effective_identity_id: c.effective_identity_id }];
});

function fmt(iso) {
  return iso ? formatDateTime(iso) : "-";
}
function fmtShort(iso) {
  return iso ? formatDateTimeShort(iso) : "";
}
function pct(q) {
  return q == null ? "-" : `${Math.round(q * 100)}%`;
}
function orientationLabel(o) {
  return ORIENTATIONS[o] ?? "unknown";
}
function stateLabel(s) {
  return STATE_LABELS[s] ?? s;
}
function stateColor(s) {
  return STATE_COLORS[s];
}
function modelOk(c) {
  // The server is authoritative; this only mirrors the detail eligibility flag
  // for the currently opened candidate as a list-level hint.
  if (detailCandidate.value.candidate_id === c.candidate_id) {
    return eligibility.value.model_compatible;
  }
  return true;
}
function relativeAge(iso) {
  if (!iso) return "-";
  const ms = Date.now() - new Date(iso).getTime();
  if (Number.isNaN(ms)) return "-";
  const h = Math.floor(ms / 3.6e6);
  if (h < 1) return `${Math.max(0, Math.floor(ms / 6e4))}m`;
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

async function refreshAll() {
  forbidden.value = false;
  try {
    await actions.invalidate();
    actions.loadTargets();
  } catch (err) {
    if (err instanceof CorrectionError && err.status === 403) forbidden.value = true;
  }
}

// Load neighbors when the detail opens.
watch(
  () => detailCandidate.value.candidate_id,
  async (id) => {
    neighbors.value = [];
    showReject.value = false;
    relabelTarget.value = "";
    rejectReason.value = "";
    rejectNote.value = "";
    const phId = detailCandidate.value.ph_id;
    if (!id || !phId) return;
    try {
      const data = await ctsPh.observations(phId, 12);
      neighbors.value = (data?.observations || data || []).slice(0, 12);
    } catch {
      neighbors.value = [];
    }
  },
);

function targetName(id) {
  const t = state.targets.value.find((x) => x.identity_id === id);
  return t?.display_name || id;
}

const review = useIdentityReviewStore();
const selectMode = ref(false);
const columnCount = computed(() => (selectMode.value ? 10 : 9));
// The member the system proposes; choosing them approves, choosing anyone else relabels.
const proposedId = computed(
  () => detailCandidate.value.proposed_identity_id || detailCandidate.value.identity_id || null,
);
const selectableIds = computed(() =>
  state.candidates.value.filter((c) => c.state === "pending_review").map((c) => c.candidate_id),
);

function toggleSelectMode(active) {
  selectMode.value = active;
  actions.clearSelection();
}

function selectAllPending() {
  for (const id of selectableIds.value) {
    if (!state.selected.value.has(id)) actions.toggleSelected(id);
  }
}

/** Every member decision goes through a confirm that states the server's effect. */
async function confirmMember(identityId) {
  if (!identityId || !eligibility.value.eligible) return;
  const name = targetName(identityId);
  const isProposal = identityId === proposedId.value;
  const ok = await showConfirm(
    isProposal ? `Verify as ${name}` : `Relabel to ${name} and verify`,
    review.effect("reid_review", "is_member", name),
  );
  if (!ok) return;
  const id = detailCandidate.value.candidate_id;
  const done = isProposal
    ? actions.approve(id)
    : actions.relabel(id, { target_identity_id: identityId });
  await done.catch(() => {});
}

async function onVerdict(verdict) {
  if (verdict === "not_enrolled") {
    const ok = await showConfirm(
      VERDICT_LABELS.not_enrolled,
      review.effect("reid_review", "not_enrolled"),
    );
    if (!ok) return;
    await actions
      .reject(detailCandidate.value.candidate_id, { reason: NOT_ENROLLED_REASON })
      .catch(() => {});
  } else if (verdict === "not_usable") {
    rejectReason.value = rejectReason.value || DEFAULT_UNUSABLE_REASON;
    showReject.value = true;
  }
}

async function confirmUnusable() {
  const ok = await showConfirm(
    VERDICT_LABELS.not_usable,
    review.effect("reid_review", "not_usable"),
  );
  if (!ok) return;
  await actions
    .reject(detailCandidate.value.candidate_id, {
      reason: rejectReason.value,
      note: rejectNote.value || null,
    })
    .catch(() => {});
}

async function confirmDemote() {
  const ok = await showConfirm(
    "Demote candidate",
    "Un-trust this auto-verified candidate back to pending review? It stops voting until re-approved.",
  );
  if (!ok) return;
  await actions.demote(detailCandidate.value.candidate_id).catch(() => {});
}
async function confirmCompensate() {
  await actions.compensate(detailCandidate.value.candidate_id).catch(() => {});
}

async function confirmBatchNotEnrolled() {
  const n = state.selectedIds.value.length;
  const ok = await showConfirm(
    `${VERDICT_LABELS.not_enrolled}: ${n} sample${n === 1 ? "" : "s"}`,
    review.effect("reid_review", "not_enrolled"),
  );
  if (!ok) return;
  await actions.rejectSelected({ reason: NOT_ENROLLED_REASON }).catch(() => {});
}

function openBatchReject() {
  batchReason.value = DEFAULT_UNUSABLE_REASON;
  batchNote.value = "";
  batchDialog.value = true;
}
async function doBatchReject() {
  await actions
    .rejectSelected({ reason: batchReason.value, note: batchNote.value || null })
    .catch(() => {});
  batchDialog.value = false;
}

// Keys act only in the open drawer, and a member key still goes through the confirm.
useReviewKeys({
  enabled: () =>
    isReviewable.value &&
    !state.acting.value &&
    !confirmDialog.value &&
    !batchDialog.value &&
    !showReject.value,
  verdicts: () => review.surface("reid_review")?.verdicts.map((v) => v.verdict) ?? [],
  onMember: (position) => {
    const member = state.targets.value[position];
    if (member) void confirmMember(member.identity_id);
  },
  onVerdict: (verdict) => void onVerdict(verdict),
});

onMounted(() => {
  void refreshAll();
  void readiness.actions.load();
  void review.load();
});
</script>

<style scoped>
.row-clickable {
  cursor: pointer;
}
.row-clickable:hover {
  background: var(--cc-brand-softer);
}
.filter-control {
  max-width: 200px;
}
.empty-explainer {
  max-width: 520px;
}
.crop-img {
  max-width: 200px;
  max-height: 320px;
  border-radius: var(--cc-radius-xs);
  border: 1px solid var(--cc-divider);
}
.deleted-crop {
  width: 200px;
  height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 12px;
  border-radius: var(--cc-radius-xs);
  border: 1px dashed var(--cc-divider-strong);
  font-size: 0.8rem;
}
.prov-table td:first-child {
  color: var(--cc-text-2);
  width: 45%;
}
.mono {
  font-family: var(--cc-font-mono);
  font-size: 0.75rem;
  word-break: break-all;
}
</style>
