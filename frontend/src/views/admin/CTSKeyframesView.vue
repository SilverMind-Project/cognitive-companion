<template>
  <div>
    <div class="d-flex align-center flex-wrap ga-3 mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Keyframes</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">Captured keyframes from CTS signals, filterable by person and signal type.</div>
      </div>
      <v-spacer />
      <v-select
        v-model="filters.person_id"
        :items="persons"
        label="Person"
        variant="outlined"
        density="compact"
        clearable
        hide-details
        style="width: 200px"
        @update:modelValue="loadKeyframes"
      />
      <v-select
        v-model="filters.signal_type"
        :items="signalTypes"
        label="Signal Type"
        variant="outlined"
        density="compact"
        clearable
        hide-details
        style="width: 220px"
        @update:modelValue="loadKeyframes"
      />
      <v-select
        v-model="filters.limit"
        :items="[20, 50, 100]"
        label="Limit"
        variant="outlined"
        density="compact"
        hide-details
        style="width: 100px"
        @update:modelValue="loadKeyframes"
      />
      <v-chip
        v-if="identityHealth && !identityHealth.issues.length"
        size="small"
        variant="tonal"
        color="success"
        prepend-icon="mdi-shield-check"
      >{{ identityHealth.gallery_size }} in gallery</v-chip>
      <BlurToggle />
      <v-btn
        :variant="selectMode ? 'flat' : 'tonal'"
        :color="selectMode ? 'primary' : undefined"
        prepend-icon="mdi-checkbox-multiple-marked-outline"
        @click="toggleSelectMode"
      >{{ selectMode ? "Cancel" : "Select" }}</v-btn>
      <v-btn
        v-if="selectMode && selectedIds.size > 0"
        variant="flat"
        color="primary"
        prepend-icon="mdi-account-plus"
        @click="openBulkEnroll"
      >Enroll ({{ selectedIds.size }})</v-btn>
      <v-btn variant="tonal" prepend-icon="mdi-refresh" @click="loadKeyframes" :loading="loading">Refresh</v-btn>
    </div>

    <v-alert
      v-if="identityHealth && identityHealth.issues.length"
      type="warning"
      variant="tonal"
      density="compact"
      class="mb-4"
    >
      <div class="font-weight-medium mb-1">Identity gallery needs attention</div>
      <div v-for="issue in identityHealth.issues" :key="issue" class="text-body-2">{{ issue }}</div>
    </v-alert>

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
          :key="kf.keyframe_id || kf.sample_id"
          cols="12"
          sm="6"
          md="4"
          lg="3"
        >
          <v-card
            class="keyframe-card"
            :class="{ 'card-selected': selectMode && selectedIds.has(kf.keyframe_id || kf.sample_id) }"
            elevation="1"
          >
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
              <v-overlay v-if="selectMode" :model-value="true" contained class="align-start justify-start pa-1">
                <v-checkbox-btn
                  :model-value="selectedIds.has(kf.keyframe_id || kf.sample_id)"
                  color="white"
                  @click.stop="toggleSelect(kf)"
                />
              </v-overlay>
              <v-overlay opacity="0.6" class="align-end" contained>
                <div class="pa-2">
                  <v-chip
                    v-if="kf.signal_type || kf.tag_reason"
                    size="x-small"
                    :color="kf.signal_type ? 'primary' : 'secondary'"
                  >
                    {{ (kf.signal_type || kf.tag_reason).replace(/_/g, " ") }}
                  </v-chip>
                  <v-chip v-if="kf.severity" size="x-small" :color="severityColor(kf.severity)" class="ml-1">
                    {{ kf.severity }}
                  </v-chip>
                </div>
              </v-overlay>
            </v-img>

            <v-card-actions class="pa-2">
              <div class="d-flex flex-column ga-1 flex-grow-1">
                <span class="text-caption font-weight-medium">{{ kf.person_id || "Unknown" }}</span>
                <span class="text-caption text-medium-emphasis">{{ formatTime(kf.captured_at) }}</span>
                <div class="d-flex ga-1">
                  <v-btn size="x-small" variant="text" color="primary" @click="viewKeyframe(kf)">
                    <v-icon start size="small">mdi-eye</v-icon>View
                  </v-btn>
                  <v-btn v-if="!kf.retained" size="x-small" variant="text" @click="retain(kf)">
                    <v-icon start size="small">mdi-bookmark</v-icon>Retain
                  </v-btn>
                </div>
              </div>
            </v-card-actions>
          </v-card>
        </v-col>
      </v-row>
    </v-card>

    <!-- Keyframe Detail Dialog -->
    <v-dialog v-model="detailDialog" max-width="800">
      <v-card v-if="selectedKeyframe">
        <DialogHeader
          icon="mdi-image-search"
          label="Keyframe"
          title="Details"
          @close="detailDialog = false"
        />
        <v-img :src="displaySrc(keyframeImage(selectedKeyframe))" height="400" cover />
        <v-card-text>
          <v-row>
            <v-col cols="6">
              <div class="text-caption text-medium-emphasis">Person</div>
              <div class="font-weight-medium">{{ selectedKeyframe.person_id }}</div>
            </v-col>
            <v-col cols="6">
              <div class="text-caption text-medium-emphasis">Captured</div>
              <div class="font-weight-medium">{{ formatTime(selectedKeyframe.captured_at) }}</div>
            </v-col>
            <v-col cols="6">
              <div class="text-caption text-medium-emphasis">Signal Type</div>
              <v-chip
                v-if="selectedKeyframe.signal_type || selectedKeyframe.tag_reason"
                size="small"
                :color="selectedKeyframe.signal_type ? 'primary' : 'secondary'"
              >
                {{ (selectedKeyframe.signal_type || selectedKeyframe.tag_reason).replace(/_/g, " ") }}
              </v-chip>
              <span v-else class="text-body-2 text-medium-emphasis">—</span>
            </v-col>
            <v-col cols="6">
              <div class="text-caption text-medium-emphasis">Quality</div>
              <template v-if="selectedKeyframe.quality != null && selectedKeyframe.quality > 0">
                <v-progress-linear :model-value="selectedKeyframe.quality * 100" height="8" rounded />
                <div class="text-caption text-medium-emphasis mt-1">{{ Math.round(selectedKeyframe.quality * 100) }}%</div>
              </template>
              <span v-else class="text-body-2 text-medium-emphasis">—</span>
            </v-col>
          </v-row>
          <v-divider class="my-3" />
          <div class="text-subtitle-2 mb-2">Annotations</div>
          <v-chip-group orientation="horizontal" wrap>
            <v-chip
              v-for="reason in selectedKeyframe.reasons || []"
              :key="reason"
              size="small"
              variant="tonal"
              color="blue"
            >
              {{ reason }}
            </v-chip>
          </v-chip-group>
        </v-card-text>
        <v-divider />
        <v-card-actions class="px-6 py-3">
          <v-btn
            v-if="selectedKeyframe?.tracklet_id"
            variant="tonal"
            color="primary"
            prepend-icon="mdi-account-plus"
            @click="openEnroll(selectedKeyframe)"
          >
            Enroll in gallery
          </v-btn>
          <v-spacer />
          <v-btn variant="text" @click="detailDialog = false">Close</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Gallery Enrollment Dialog -->
    <v-dialog v-model="enrollDialog" max-width="480" persistent>
      <v-card>
        <DialogHeader
          icon="mdi-account-plus"
          label="Enroll"
          title="Gallery"
          @close="enrollDialog = false"
        />
        <v-card-text>
          <div class="text-body-2 text-medium-emphasis mb-4">
            Assign this tracklet's appearance embeddings to an identity so the
            ReID resolver can recognise them in future frames.
          </div>
          <div class="text-caption text-medium-emphasis mb-1">Tracklet</div>
          <div class="font-weight-medium text-body-2 mb-4">{{ enrollTrackletId }}</div>
          <v-autocomplete
            v-model="enrollIdentityId"
            :items="householdMembers"
            :item-title="(m) => m.name + ' (' + m.id + ')'"
            item-value="id"
            label="Identity"
            variant="outlined"
            :error-messages="enrollError ? [enrollError] : []"
            :menu-props="{ maxHeight: 280 }"
          >
            <template #item="{ props: itemProps, item }">
              <v-list-item v-bind="itemProps" :subtitle="item.raw.is_enrolled ? 'Enrolled · ' + item.raw.embedding_count + ' embedding(s)' : 'Not yet enrolled'">
                <template #append>
                  <div class="ml-2">
                    <v-chip v-if="!item.raw.is_active" size="x-small" color="warning">Inactive</v-chip>
                  </div>
                </template>
              </v-list-item>
            </template>
          </v-autocomplete>
          <v-text-field
            v-model="enrollDisplayName"
            label="Display name (optional)"
            variant="outlined"
            placeholder="e.g. Grandma"
          />
        </v-card-text>
        <DialogFooter
          hint="Creates named gallery entries for the Bayesian identity resolver."
          confirm-label="Enroll"
          :confirm-loading="enrollSaving"
          :confirm-disabled="!enrollIdentityId.trim()"
          @cancel="enrollDialog = false"
          @confirm="submitEnroll"
        />
      </v-card>
    </v-dialog>

    <!-- Bulk Enroll Dialog -->
    <v-dialog v-model="bulkDialog" max-width="480" persistent>
      <v-card>
        <DialogHeader
          icon="mdi-account-plus-outline"
          label="Bulk Enroll"
          :title="`${selectedIds.size} selected`"
          @close="bulkDialog = false"
        />
        <v-card-text>
          <v-alert v-if="enrollableCount < selectedIds.size" type="info" variant="tonal" density="compact" class="mb-3 text-body-2">
            {{ enrollableCount }} of {{ selectedIds.size }} selected frames have a tracklet ID and will be enrolled. The rest will be skipped.
          </v-alert>
          <div class="text-body-2 text-medium-emphasis mb-4">
            Assigns body-appearance embeddings from the selected tracklets to the chosen identity so the ReID resolver can recognise them in future frames.
            This uses SOLIDER-ReID embeddings only — for ArcFace face matching, add a face anchor via the person profile.
          </div>
          <v-autocomplete
            v-model="bulkIdentityId"
            :items="householdMembers"
            :item-title="(m) => m.name + ' (' + m.id + ')'"
            item-value="id"
            label="Identity"
            variant="outlined"
            :error-messages="bulkError ? [bulkError] : []"
            :menu-props="{ maxHeight: 280 }"
          >
            <template #item="{ props: itemProps, item }">
              <v-list-item
                v-bind="itemProps"
                :subtitle="item.raw.is_enrolled ? 'Enrolled · ' + item.raw.embedding_count + ' embedding(s)' : 'Not yet enrolled'"
              >
                <template #append>
                  <div class="ml-2">
                    <v-chip v-if="!item.raw.is_active" size="x-small" color="warning">Inactive</v-chip>
                  </div>
                </template>
              </v-list-item>
            </template>
          </v-autocomplete>
          <v-text-field
            v-model="bulkDisplayName"
            label="Display name (optional)"
            variant="outlined"
            placeholder="e.g. Grandma"
          />
        </v-card-text>
        <DialogFooter
          hint="Enrolls ReID body-appearance embeddings. Add a face anchor separately for ArcFace matching."
          confirm-label="Enroll"
          :confirm-loading="bulkSaving"
          :confirm-disabled="!bulkIdentityId?.trim() || enrollableCount === 0"
          @cancel="bulkDialog = false"
          @confirm="submitBulkEnroll"
        />
      </v-card>
    </v-dialog>

    <v-snackbar v-model="enrollSnackbar" :timeout="3500" color="success">
      {{ enrollSnackbarText }}
    </v-snackbar>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { api } from "../../services/api.js";
import { cts } from "../../services/cts.js";
import { severityColor } from "../../composables/useCtsSeverity";
import { formatDateTime } from "../../services/timezone.js";
import { useBlurMode, useDisplaySrc } from "../../composables/useBlurMode.js";
import DialogHeader from "../../components/common/DialogHeader.vue";
import DialogFooter from "../../components/common/DialogFooter.vue";
import BlurToggle from "../../components/cts/BlurToggle.vue";

const { blurMode } = useBlurMode();
const { displaySrc } = useDisplaySrc(blurMode);

const keyframes = ref([]);
const selectedKeyframe = ref(null);
const loading = ref(false);
const detailDialog = ref(false);

const filters = ref({
  person_id: null,
  signal_type: null,
  limit: 50,
});

const signalTypes = ref([
  "pacing",
  "bathroom_dwell_anomaly",
  "sundowning_index",
  "nighttime_movement",
  "stillness_anomaly",
  "absence",
]);

async function refreshSignalTypes() {
  // Augment the static list with signal types and tag_reasons seen in
  // the current keyframe set so caregivers can filter by any value.
  const seen = new Set(signalTypes.value);
  for (const kf of keyframes.value) {
    const val = kf.signal_type || kf.tag_reason;
    if (val && !seen.has(val)) {
      seen.add(val);
      signalTypes.value.push(val);
    }
  }
}

const persons = computed(() => {
  const ids = new Set(keyframes.value.map((k) => k.person_id).filter(Boolean));
  return Array.from(ids).sort();
});

// ── Identity health ────────────────────────────────────────────────────────
const identityHealth = ref(null);

async function loadIdentityHealth() {
  try {
    identityHealth.value = await cts.getIdentityHealth();
  } catch {
    // non-blocking — banner simply won't show
  }
}

// ── Selection mode ─────────────────────────────────────────────────────────
const selectMode = ref(false);
const selectedIds = ref(new Set());

function toggleSelectMode() {
  selectMode.value = !selectMode.value;
  if (!selectMode.value) selectedIds.value = new Set();
}

function toggleSelect(kf) {
  const id = kf.keyframe_id || kf.sample_id;
  const next = new Set(selectedIds.value);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  selectedIds.value = next;
}

// ── Bulk enroll ────────────────────────────────────────────────────────────
const bulkDialog = ref(false);
const bulkIdentityId = ref("");
const bulkDisplayName = ref("");
const bulkSaving = ref(false);
const bulkError = ref("");

const enrollableCount = computed(() =>
  keyframes.value.filter(
    (kf) => selectedIds.value.has(kf.keyframe_id || kf.sample_id) && kf.tracklet_id
  ).length
);

function openBulkEnroll() {
  bulkIdentityId.value = "";
  bulkDisplayName.value = "";
  bulkError.value = "";
  bulkDialog.value = true;
  if (!householdMembers.value.length) loadHouseholdMembers();
}

async function submitBulkEnroll() {
  bulkError.value = "";
  bulkSaving.value = true;
  const items = keyframes.value
    .filter((kf) => selectedIds.value.has(kf.keyframe_id || kf.sample_id) && kf.tracklet_id)
    .map((kf) => ({
      tracklet_id: kf.tracklet_id,
      identity_id: bulkIdentityId.value.trim(),
      display_name: bulkDisplayName.value.trim() || null,
    }));
  try {
    const resp = await cts.enrollBatch(items);
    const ok = resp.results.filter((r) => r.status === "ok").length;
    const fail = resp.results.length - ok;
    bulkDialog.value = false;
    selectMode.value = false;
    selectedIds.value = new Set();
    enrollSnackbarText.value =
      fail > 0
        ? `Enrolled ${ok} tracklet(s); ${fail} could not be enrolled.`
        : `Enrolled ${ok} tracklet(s) for "${bulkIdentityId.value.trim()}".`;
    enrollSnackbar.value = true;
    await loadIdentityHealth();
  } catch (e) {
    bulkError.value = e.message || String(e);
  } finally {
    bulkSaving.value = false;
  }
}

onMounted(() => {
  loadKeyframes();
  loadIdentityHealth();
});

async function loadKeyframes() {
  loading.value = true;
  try {
    const data = await cts.getKeyframes({
      person_id: filters.value.person_id,
      signal_type: filters.value.signal_type,
      limit: filters.value.limit,
    });
    keyframes.value = data.keyframes || [];
    refreshSignalTypes();
  } catch (e) {
    console.error("Failed to load keyframes:", e);
  } finally {
    loading.value = false;
  }
}

function keyframeImage(kf) {
  return kf.image_url || "";
}

function viewKeyframe(kf) {
  selectedKeyframe.value = kf;
  detailDialog.value = true;
}

async function retain(kf) {
  try {
    await cts.retainKeyframe(kf.keyframe_id || kf.sample_id);
    kf.retained = true;
  } catch (e) {
    console.error("Failed to retain keyframe:", e);
  }
}

function formatTime(iso) {
  return formatDateTime(iso) || "";
}

// ── Gallery enrollment ──────────────────────────────────────────────────────
const householdMembers = ref([]);
const enrollDialog = ref(false);
const enrollSaving = ref(false);
const enrollTrackletId = ref("");
const enrollIdentityId = ref("");
const enrollDisplayName = ref("");
const enrollError = ref("");
const enrollSnackbar = ref(false);
const enrollSnackbarText = ref("");

async function loadHouseholdMembers() {
  try {
    const [persons, enrolled] = await Promise.all([
      api.getPersons(),
      api.getEnrolledPersons().catch(() => []),
    ]);
    const enrolledById = new Map(
      (enrolled || []).map((e) => [e.person_id || e.id, e])
    );
    householdMembers.value = (persons || []).map((p) => {
      const enrollment = enrolledById.get(p.id);
      return {
        ...p,
        is_enrolled: !!enrollment,
        embedding_count: enrollment?.embedding_count || 0,
      };
    });
  } catch {
    householdMembers.value = [];
  }
}

function openEnroll(kf) {
  enrollTrackletId.value = kf.tracklet_id || "";
  enrollIdentityId.value = kf.person_id || "";
  enrollDisplayName.value = "";
  enrollError.value = "";
  enrollDialog.value = true;
  if (!householdMembers.value.length) loadHouseholdMembers();
}

async function submitEnroll() {
  enrollError.value = "";
  enrollSaving.value = true;
  try {
    const resp = await cts.enrollFromTracklet({
      identity_id: enrollIdentityId.value.trim(),
      tracklet_id: enrollTrackletId.value,
      display_name: enrollDisplayName.value.trim() || null,
    });
    enrollDialog.value = false;
    enrollSnackbarText.value = `Enrolled ${resp.enrolled_count} embedding(s) for "${resp.identity_id}".`;
    enrollSnackbar.value = true;
  } catch (e) {
    enrollError.value = e.message || String(e);
  } finally {
    enrollSaving.value = false;
  }
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
.card-selected {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}
</style>
