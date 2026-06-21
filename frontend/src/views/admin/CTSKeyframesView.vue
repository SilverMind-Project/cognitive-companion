<template>
  <div>
    <div class="d-flex align-center flex-wrap ga-3 mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Keyframes</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          One card per physical frame. Every identity, source, and conflict is server-computed.
        </div>
      </div>
      <v-spacer />
      <v-select
        v-model="filters.person_id"
        :items="personOptions"
        item-title="title"
        item-value="value"
        label="Person"
        variant="outlined"
        density="compact"
        clearable
        hide-details
        style="width: 180px"
        :loading="personsLoading"
        @update:modelValue="onFilterChange"
      />
      <v-select
        v-model="filters.tag_reason"
        :items="triggerReasons"
        label="Trigger Reason"
        variant="outlined"
        density="compact"
        clearable
        hide-details
        style="width: 170px"
        @update:modelValue="onFilterChange"
      />
      <v-select
        v-model="filters.decision_source"
        :items="SOURCE_OPTIONS"
        label="Source"
        variant="outlined"
        density="compact"
        clearable
        hide-details
        style="width: 150px"
        @update:modelValue="onFilterChange"
      />
      <v-btn
        :variant="filters.conflict_only ? 'flat' : 'tonal'"
        :color="filters.conflict_only ? 'error' : undefined"
        prepend-icon="mdi-alert"
        @click="toggleFilter('conflict_only')"
      >Conflicts</v-btn>
      <v-btn
        :variant="filters.pending_review_only ? 'flat' : 'tonal'"
        :color="filters.pending_review_only ? 'info' : undefined"
        prepend-icon="mdi-clock-outline"
        @click="toggleFilter('pending_review_only')"
      >Pending</v-btn>
      <v-select
        v-model="filters.limit"
        :items="[20, 50, 100]"
        label="Limit"
        variant="outlined"
        density="compact"
        hide-details
        style="width: 100px"
        @update:modelValue="onFilterChange"
      />
      <BlurToggle />
      <v-btn variant="tonal" prepend-icon="mdi-refresh" @click="loadKeyframes" :loading="loading">Refresh</v-btn>
    </div>

    <v-card class="glass-card">
      <!-- Empty state -->
      <div v-if="keyframes.length === 0 && !loading" class="text-center text-medium-emphasis py-12">
        <v-icon size="64">mdi-image-off</v-icon>
        <div class="mt-2">No keyframes found. Try adjusting filters.</div>
      </div>

      <!-- Keyframes Grid -->
      <v-row v-else class="pa-4" dense>
        <v-col
          v-for="kf in keyframes"
          :key="kf.physical_frame_id || kf.keyframe_id"
          cols="12"
          sm="6"
          md="4"
          lg="3"
        >
          <v-card class="keyframe-card" elevation="1">
            <v-img
              :src="displaySrc(keyframeImage(kf))"
              height="180"
              cover
              class="keyframe-image"
            >
              <template v-slot:placeholder>
                <v-row class="fill-height ma-0" align="center" justify="center">
                  <v-progress-circular indeterminate color="primary" />
                </v-row>
              </template>
              <v-overlay opacity="0.6" class="align-end" contained>
                <div class="pa-2 d-flex flex-wrap ga-1">
                  <v-chip
                    v-for="reason in kf.trigger_reasons || []"
                    :key="reason"
                    size="x-small"
                    color="secondary"
                  >
                    {{ reason.replace(/_/g, " ") }}
                  </v-chip>
                  <v-chip
                    v-if="kf.conflict_count"
                    size="x-small"
                    color="error"
                    prepend-icon="mdi-alert"
                  >{{ kf.conflict_count }} conflict</v-chip>
                  <v-chip
                    v-if="kf.unknown_count"
                    size="x-small"
                    color="warning"
                  >{{ kf.unknown_count }} unknown</v-chip>
                  <v-chip
                    v-if="kf.pending_review_count"
                    size="x-small"
                    color="info"
                    prepend-icon="mdi-clock-outline"
                  >{{ kf.pending_review_count }} pending</v-chip>
                </div>
              </v-overlay>
            </v-img>

            <v-card-actions class="pa-2">
              <div class="d-flex flex-column ga-1 flex-grow-1">
                <!-- Server-computed card summary: every effective identity with count -->
                <div class="d-flex flex-wrap ga-1">
                  <v-chip
                    v-for="item in kf.identity_summary || []"
                    :key="item.effective_identity_id || 'unknown'"
                    size="x-small"
                    :color="item.effective_identity_id ? 'primary' : 'warning'"
                    variant="tonal"
                  >
                    {{ identityName(item.effective_identity_id) }}
                    <span v-if="item.count > 1" class="ml-1">×{{ item.count }}</span>
                    <v-tooltip activator="parent" location="top">
                      {{ (item.source_badges || []).join(", ") || "no source" }}
                    </v-tooltip>
                  </v-chip>
                  <span
                    v-if="!(kf.identity_summary || []).length"
                    class="text-caption text-medium-emphasis"
                  >No identities</span>
                </div>
                <span class="text-caption text-medium-emphasis">{{ formatTime(kf.captured_at) }}</span>
                <div class="d-flex ga-1">
                  <v-btn size="x-small" variant="text" color="primary" @click="openDetail(kf)">
                    <v-icon start size="small">mdi-eye</v-icon>Inspect
                  </v-btn>
                </div>
              </div>
            </v-card-actions>
          </v-card>
        </v-col>
      </v-row>

      <!-- Pagination -->
      <div v-if="pageCount > 1" class="d-flex align-center justify-center pa-3">
        <v-pagination
          v-model="page"
          :length="pageCount"
          :total-visible="7"
          density="comfortable"
          @update:modelValue="loadKeyframes"
        />
      </div>
      <div v-if="truncated" class="text-caption text-medium-emphasis text-center pb-3">
        Showing the most recent window of matches.
      </div>
    </v-card>

    <!-- Detail dialog: labeled overlay + click-to-correct -->
    <v-dialog v-model="detailOpen" max-width="1080" scrollable>
      <v-card v-if="detailCard">
        <DialogHeader
          icon="mdi-image-search"
          label="Keyframe"
          :title="`${detailCard.camera_id} · ${formatTime(detailCard.captured_at)}`"
          @close="closeDetail"
        />
        <v-divider />
        <v-card-text>
          <v-row dense>
            <!-- Overlay -->
            <v-col cols="12" md="7">
              <IdentityBboxOverlay
                :image-url="keyframeImage(detailCard)"
                :bboxes="detailCard.bboxes || []"
                :targets="targets"
                :frame-width="detailCard.frame_width"
                :frame-height="detailCard.frame_height"
                @select="onBboxSelect"
              />
              <div class="text-caption text-medium-emphasis mt-2">
                Click a box to correct its identity.
              </div>
              <v-btn
                class="mt-2"
                size="small"
                variant="tonal"
                prepend-icon="mdi-vector-square"
                @click="openGeometry"
              >
                Edit boxes (geometry)
              </v-btn>
            </v-col>

            <!-- Evidence + correction workflow -->
            <v-col cols="12" md="5">
              <template v-if="selectedBbox">
                <div class="text-subtitle-2 mb-2">Selected box</div>
                <IdentityEvidenceBadges :bbox="selectedBbox" :targets="targets" detailed class="mb-3" />
                <v-divider class="mb-3" />
                <IdentityCorrectionWorkflow
                  :key="selectedBbox.bbox_id || selectedBbox.ph_id"
                  :ph-id="selectedBbox.ph_id"
                  :frame-captured-at="detailCard.captured_at"
                  :reviewed-frame-id="firstTriggerKeyframeId"
                  :reviewed-bbox="reviewedBbox"
                  :bbox="selectedBbox"
                  source-view="keyframe"
                  default-scope="frame_only"
                  @applied="onCorrectionApplied"
                  @close="selectedBbox = null"
                />
              </template>
              <div v-else class="text-body-2 text-medium-emphasis pa-4 text-center">
                Select a bounding box to view evidence and correct identity.
              </div>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- Geometry editing (separate revision type) -->
    <KeyframeAnnotationDialog
      v-model="geometryOpen"
      :image-url="detailCard ? keyframeImage(detailCard) : ''"
      :keyframe-id="firstTriggerKeyframeId"
      :identities="targets"
      @saved="onGeometrySaved"
      @error="notify.error($event)"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { cts } from "../../services/cts.js";
import { formatDateTime } from "../../services/timezone.js";
import { useBlurMode, useDisplaySrc } from "../../composables/useBlurMode.js";
import { useNotify } from "../../composables/useNotify.js";
import BlurToggle from "../../components/cts/BlurToggle.vue";
import DialogHeader from "../../components/common/DialogHeader.vue";
import KeyframeAnnotationDialog from "../../components/cts/keyframes/KeyframeAnnotationDialog.vue";
import IdentityBboxOverlay from "../../components/cts/identity/IdentityBboxOverlay.vue";
import IdentityEvidenceBadges from "../../components/cts/identity/IdentityEvidenceBadges.vue";
import IdentityCorrectionWorkflow from "../../components/cts/identity/IdentityCorrectionWorkflow.vue";

const { blurMode } = useBlurMode();
const { displaySrc } = useDisplaySrc(blurMode);
const { notify } = useNotify();

const keyframes = ref([]);
const loading = ref(false);
const total = ref(0);
const truncated = ref(false);
const page = ref(1);

// Detail dialog
const detailOpen = ref(false);
const detailCard = ref(null);
const selectedBbox = ref(null);
const geometryOpen = ref(false);

const SOURCE_OPTIONS = [
  { title: "ArcFace", value: "face" },
  { title: "ReID", value: "reid" },
  { title: "Prior", value: "temporal_prior" },
];

const filters = ref({
  person_id: null,
  tag_reason: null,
  decision_source: null,
  conflict_only: false,
  pending_review_only: false,
  limit: 50,
});

const triggerReasons = ref([
  "periodic",
  "identity_changed",
  "hazard",
  "dwell_start",
  "fall",
  "dementia_signal",
]);

function refreshTriggerReasons() {
  const seen = new Set(triggerReasons.value);
  for (const kf of keyframes.value) {
    for (const reason of kf.trigger_reasons || []) {
      if (reason && !seen.has(reason)) {
        seen.add(reason);
        triggerReasons.value.push(reason);
      }
    }
  }
}

// Filter options come from the authoritative correction-target endpoint
// (active household members), not the current result page. An explicit Unknown
// option maps to the server-side explicit_unknown filter.
const UNKNOWN_OPTION = "__unknown__";
const personsLoading = ref(false);
const targets = ref([]);
const personOptions = ref([{ title: "Unknown", value: UNKNOWN_OPTION }]);

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / filters.value.limit)));

const firstTriggerKeyframeId = computed(
  () => detailCard.value?.triggers?.[0]?.keyframe_id || ""
);

// reviewed_bbox in normalized ratio coordinates for the audit record.
const reviewedBbox = computed(() => {
  const b = selectedBbox.value;
  if (!b || !b.frame_width || !b.frame_height) return null;
  return {
    x1: b.x1 / b.frame_width,
    y1: b.y1 / b.frame_height,
    x2: b.x2 / b.frame_width,
    y2: b.y2 / b.frame_height,
  };
});

function identityName(id) {
  if (!id) return "Unknown";
  return targets.value.find((t) => t.identity_id === id)?.display_name || id;
}

async function loadPersonOptions() {
  personsLoading.value = true;
  try {
    const data = await cts.getCorrectionTargets();
    targets.value = data?.targets || [];
    const opts = targets.value.map((t) => ({
      title: t.display_name || t.identity_id,
      value: t.identity_id,
    }));
    personOptions.value = [{ title: "Unknown", value: UNKNOWN_OPTION }, ...opts];
  } catch (e) {
    console.error("Failed to load correction targets:", e);
  } finally {
    personsLoading.value = false;
  }
}

function toggleFilter(key) {
  filters.value[key] = !filters.value[key];
  onFilterChange();
}

function onFilterChange() {
  page.value = 1;
  loadKeyframes();
}

onMounted(() => {
  loadPersonOptions();
  loadKeyframes();
});

async function loadKeyframes() {
  loading.value = true;
  try {
    const selected = filters.value.person_id;
    const isUnknown = selected === UNKNOWN_OPTION;
    const data = await cts.getKeyframes({
      person_id: isUnknown ? null : selected,
      explicit_unknown: isUnknown,
      tag_reason: filters.value.tag_reason,
      decision_source: filters.value.decision_source,
      conflict_only: filters.value.conflict_only,
      pending_review_only: filters.value.pending_review_only,
      limit: filters.value.limit,
      offset: (page.value - 1) * filters.value.limit,
    });
    keyframes.value = data.keyframes || [];
    total.value = data.total ?? keyframes.value.length;
    truncated.value = !!data.truncated;
    refreshTriggerReasons();
  } catch (e) {
    notify.error("Failed to load keyframes: " + (e.message || e));
  } finally {
    loading.value = false;
  }
}

function keyframeImage(kf) {
  return kf.image_url || "";
}

function openDetail(kf) {
  detailCard.value = kf;
  selectedBbox.value = null;
  detailOpen.value = true;
}

function closeDetail() {
  detailOpen.value = false;
  selectedBbox.value = null;
}

function onBboxSelect(bbox) {
  selectedBbox.value = bbox;
}

function openGeometry() {
  geometryOpen.value = true;
}

async function onGeometrySaved() {
  notify.success("Boxes updated");
  geometryOpen.value = false;
  await loadKeyframes();
}

async function onCorrectionApplied() {
  notify.success("Identity corrected");
  closeDetail();
  await loadKeyframes();
}

function formatTime(iso) {
  return formatDateTime(iso) || "";
}
</script>

<style scoped>
.keyframe-card {
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.keyframe-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--cc-shadow-md);
}
.keyframe-image {
  border-radius: 4px 4px 0 0;
}
</style>
