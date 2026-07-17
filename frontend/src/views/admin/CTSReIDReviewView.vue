<template>
  <div class="reid-review">
    <div class="d-flex align-center mb-4 flex-wrap ga-3">
      <h1 class="text-h5 mb-0">ReID review queue</h1>
      <v-chip size="small" color="warning" variant="tonal" title="Pending review">
        {{ state.counts.value.pending_review }} pending
      </v-chip>
      <v-chip size="small" color="success" variant="tonal" title="Operator verified">
        {{ state.counts.value.operator_verified }} verified
      </v-chip>
      <v-chip size="small" variant="tonal" title="Rejected">
        {{ state.counts.value.rejected }} rejected
      </v-chip>
      <v-spacer />
      <BlurToggle />
      <v-btn
        size="small"
        variant="text"
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
      <!-- Filters -->
      <v-card variant="outlined" class="mb-4 pa-3">
        <div class="d-flex flex-wrap ga-3 align-end">
          <v-select
            :model-value="state.filters.value.state"
            label="State"
            :items="STATE_OPTIONS"
            density="compact"
            hide-details
            style="max-width: 180px"
            @update:model-value="(v) => actions.setFilter('state', v)"
          />
          <v-text-field
            :model-value="state.filters.value.identity_id"
            label="Identity"
            density="compact"
            hide-details
            clearable
            style="max-width: 200px"
            @update:model-value="(v) => actions.setFilter('identity_id', v || null)"
          />
          <v-text-field
            :model-value="state.filters.value.camera_id"
            label="Camera"
            density="compact"
            hide-details
            clearable
            style="max-width: 180px"
            @update:model-value="(v) => actions.setFilter('camera_id', v || null)"
          />
          <v-text-field
            :model-value="state.filters.value.model_version"
            label="Model version"
            density="compact"
            hide-details
            clearable
            style="max-width: 180px"
            @update:model-value="(v) => actions.setFilter('model_version', v || null)"
          />
        </div>
      </v-card>

      <!-- Batch action bar (reject only; bulk approval is disabled by design) -->
      <v-slide-y-transition>
        <v-card
          v-if="state.selectedIds.value.length"
          variant="tonal"
          color="error"
          class="mb-3 pa-2"
        >
          <div class="d-flex align-center ga-3">
            <span class="text-body-2">{{ state.selectedIds.value.length }} selected</span>
            <v-spacer />
            <v-btn size="small" variant="text" @click="actions.clearSelection()">Clear</v-btn>
            <v-btn
              size="small"
              color="error"
              prepend-icon="mdi-close-circle-outline"
              :loading="state.acting.value"
              @click="openBatchReject"
            >
              Reject selected
            </v-btn>
          </div>
        </v-card>
      </v-slide-y-transition>

      <v-alert v-if="state.listError.value" type="error" variant="tonal" class="mb-3">
        {{ state.listError.value }}
        <template #append>
          <v-btn size="small" variant="text" @click="refreshAll">Retry</v-btn>
        </template>
      </v-alert>

      <v-card variant="outlined">
        <v-table density="comfortable">
          <thead>
            <tr>
              <th style="width: 44px"></th>
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
              <td colspan="9" class="text-center py-8">
                <v-progress-circular indeterminate size="28" />
              </td>
            </tr>
            <tr v-else-if="!state.candidates.value.length">
              <td colspan="9" class="text-center py-8 text-medium-emphasis">
                No candidates match the current filters.
              </td>
            </tr>
            <tr
              v-for="c in state.candidates.value"
              :key="c.candidate_id"
              class="row-clickable"
              @click="actions.openDetail(c.candidate_id)"
            >
              <td @click.stop>
                <v-checkbox
                  :model-value="state.selected.value.has(c.candidate_id)"
                  density="compact"
                  hide-details
                  :disabled="c.state !== 'pending_review'"
                  @update:model-value="actions.toggleSelected(c.candidate_id)"
                />
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
      width="560"
      @update:model-value="(v) => !v && actions.closeDetail()"
    >
      <div v-if="state.detailLoading.value" class="pa-8 text-center">
        <v-progress-circular indeterminate />
      </div>
      <div v-else-if="state.detailError.value" class="pa-4">
        <v-alert type="error" variant="tonal">{{ state.detailError.value }}</v-alert>
      </div>
      <div v-else-if="state.detail.value" class="pa-4">
        <div class="d-flex align-center mb-3">
          <h2 class="text-h6 mb-0">Candidate</h2>
          <v-spacer />
          <v-btn icon="mdi-close" size="small" variant="text" @click="actions.closeDetail()" />
        </div>

        <!-- Eligibility -->
        <v-alert
          :type="
            detailCandidate.state !== 'pending_review'
              ? 'info'
              : eligibility.eligible
                ? 'success'
                : 'warning'
          "
          variant="tonal"
          density="compact"
          class="mb-3"
        >
          <template v-if="detailCandidate.state !== 'pending_review'">
            Already reviewed: {{ detailCandidate.state }}.
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
                {{ detailCandidate.crop_width || "?" }} x {{ detailCandidate.crop_height || "?" }}
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
        <div v-if="detailCandidate.state === 'pending_review'">
          <v-divider class="mb-3" />
          <div class="d-flex ga-2 mb-2">
            <v-btn
              color="success"
              size="small"
              prepend-icon="mdi-check"
              :disabled="!eligibility.eligible || state.acting.value"
              :title="
                eligibility.eligible ? 'Verify this candidate' : 'Server eligibility is false'
              "
              @click="confirmApprove"
            >
              Approve
            </v-btn>
            <v-btn
              color="warning"
              size="small"
              prepend-icon="mdi-account-switch-outline"
              :disabled="!eligibility.eligible || state.acting.value"
              @click="showRelabel = !showRelabel"
            >
              Relabel
            </v-btn>
            <v-btn
              color="error"
              size="small"
              prepend-icon="mdi-close"
              :disabled="state.acting.value"
              @click="showReject = !showReject"
            >
              Reject
            </v-btn>
          </div>

          <v-expand-transition>
            <div v-if="showRelabel" class="pa-2">
              <v-autocomplete
                v-model="relabelTarget"
                label="Household target"
                :items="state.targets.value"
                item-title="display_name"
                item-value="identity_id"
                :loading="state.targetsLoading.value"
                density="compact"
                hide-details
                class="mb-2"
              />
              <v-btn
                size="small"
                color="warning"
                :disabled="!relabelTarget"
                @click="confirmRelabel"
              >
                Relabel and verify
              </v-btn>
            </div>
          </v-expand-transition>

          <v-expand-transition>
            <div v-if="showReject" class="pa-2">
              <v-select
                v-model="rejectReason"
                label="Reason"
                :items="REJECT_REASONS"
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
              <v-btn size="small" color="error" :disabled="!rejectReason" @click="confirmReject">
                Confirm rejection
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
    </v-navigation-drawer>

    <!-- Batch reject dialog -->
    <v-dialog v-model="batchDialog" max-width="420">
      <v-card>
        <v-card-title>Reject {{ state.selectedIds.value.length }} candidates</v-card-title>
        <v-card-text>
          <v-select
            v-model="batchReason"
            label="Reason"
            :items="REJECT_REASONS"
            density="compact"
          />
          <v-textarea v-model="batchNote" label="Note (optional)" rows="2" density="compact" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="batchDialog = false">Cancel</v-btn>
          <v-btn
            color="error"
            :disabled="!batchReason"
            :loading="state.acting.value"
            @click="doBatchReject"
          >
            Reject
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Confirmation dialog for approve / relabel -->
    <v-dialog v-model="confirmDialog" max-width="420">
      <v-card>
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
import { useNotify } from "@/composables/useNotify";
import { useConfirm } from "@/composables/useConfirm";
import { useBlurMode, useDisplaySrc } from "@/composables/useBlurMode";
import { CorrectionError } from "@/services/cts_identity";
import { ctsPh } from "@/services/cts_ph";
import { formatDateTime, formatDateTimeShort } from "@/services/timezone";
import BlurToggle from "@/components/cts/BlurToggle.vue";
import IdentityBboxOverlay from "@/components/cts/identity/IdentityBboxOverlay.vue";

const STATE_OPTIONS = [
  { title: "Pending review", value: "pending_review" },
  { title: "Operator verified", value: "operator_verified" },
  { title: "Rejected", value: "rejected" },
];
const REJECT_REASONS = [
  { title: "Wrong person", value: "wrong_person" },
  { title: "Identity uncertain", value: "identity_uncertain" },
  { title: "Low quality", value: "low_quality" },
  { title: "Duplicate candidate", value: "duplicate_candidate" },
  { title: "Bad bbox", value: "bad_bbox" },
  { title: "Other", value: "other" },
];
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
const showRelabel = ref(false);
const showReject = ref(false);
const relabelTarget = ref("");
const rejectReason = ref("");
const rejectNote = ref("");
const batchDialog = ref(false);
const batchReason = ref("");
const batchNote = ref("");

const detailCandidate = computed(() => state.detail.value?.candidate || {});
const detailEvents = computed(() => state.detail.value?.events || []);
const eligibility = computed(
  () => state.detail.value?.eligibility || { eligible: false, model_compatible: true, reasons: [] },
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
    showRelabel.value = false;
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

async function confirmApprove() {
  const ok = await showConfirm(
    "Approve candidate",
    `Verify this candidate as ${detailCandidate.value.proposed_identity_id || detailCandidate.value.identity_id || "the proposed identity"}? It will start influencing identity resolution.`,
  );
  if (!ok) return;
  await actions.approve(detailCandidate.value.candidate_id).catch(() => {});
}
async function confirmRelabel() {
  if (!relabelTarget.value) return;
  const ok = await showConfirm(
    "Relabel and verify",
    `Relabel this candidate to ${targetName(relabelTarget.value)} and verify it?`,
  );
  if (!ok) return;
  await actions
    .relabel(detailCandidate.value.candidate_id, { target_identity_id: relabelTarget.value })
    .catch(() => {});
}
async function confirmReject() {
  await actions
    .reject(detailCandidate.value.candidate_id, {
      reason: rejectReason.value,
      note: rejectNote.value || null,
    })
    .catch(() => {});
}
async function confirmCompensate() {
  await actions.compensate(detailCandidate.value.candidate_id).catch(() => {});
}

function openBatchReject() {
  batchReason.value = "";
  batchNote.value = "";
  batchDialog.value = true;
}
async function doBatchReject() {
  await actions
    .rejectSelected({ reason: batchReason.value, note: batchNote.value || null })
    .catch(() => {});
  batchDialog.value = false;
}

onMounted(refreshAll);
</script>

<style scoped>
.row-clickable {
  cursor: pointer;
}
.row-clickable:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}
.crop-img {
  max-width: 200px;
  max-height: 320px;
  border-radius: 6px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
}
.deleted-crop {
  width: 200px;
  height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 12px;
  border-radius: 6px;
  border: 1px dashed rgba(var(--v-theme-on-surface), 0.24);
  font-size: 0.8rem;
}
.prov-table td:first-child {
  color: rgba(var(--v-theme-on-surface), 0.6);
  width: 45%;
}
.mono {
  font-family: monospace;
  font-size: 0.75rem;
  word-break: break-all;
}
</style>
