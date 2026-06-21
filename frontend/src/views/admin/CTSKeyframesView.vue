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
        :items="personOptions"
        item-title="title"
        item-value="value"
        label="Person"
        variant="outlined"
        density="compact"
        clearable
        hide-details
        style="width: 200px"
        :loading="personsLoading"
        @update:modelValue="loadKeyframes"
      />
      <v-select
        v-model="filters.tag_reason"
        :items="triggerReasons"
        label="Trigger Reason"
        variant="outlined"
        density="compact"
        clearable
        hide-details
        style="width: 200px"
        @update:modelValue="loadKeyframes"
      />
      <v-btn
        :variant="filters.conflict_only ? 'flat' : 'tonal'"
        :color="filters.conflict_only ? 'error' : undefined"
        prepend-icon="mdi-alert"
        @click="toggleConflictOnly"
      >Conflicts</v-btn>
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
      <BlurToggle />
      <v-btn
        :variant="selectMode ? 'flat' : 'tonal'"
        :color="selectMode ? 'primary' : undefined"
        prepend-icon="mdi-checkbox-multiple-marked-outline"
        @click="toggleSelectMode"
      >{{ selectMode ? "Cancel" : "Select" }}</v-btn>
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
                    {{ item.effective_identity_id || "Unknown" }}
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

    <!-- Keyframe Annotation Dialog -->
    <KeyframeAnnotationDialog
      v-model="keyframeDialog"
      :image-url="selectedKeyframe ? keyframeImage(selectedKeyframe) : ''"
      :keyframe-id="selectedKeyframe?.keyframe_id || selectedKeyframe?.sample_id || ''"
      :identities="availableIdentities"
      @saved="onAnnotationSaved"
      @error="notify.error($event)"
    />

  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { cts } from "../../services/cts.js";
import { formatDateTime } from "../../services/timezone.js";
import { useBlurMode, useDisplaySrc } from "../../composables/useBlurMode.js";
import { useNotify } from "../../composables/useNotify.js";
import BlurToggle from "../../components/cts/BlurToggle.vue";
import KeyframeAnnotationDialog from "../../components/cts/keyframes/KeyframeAnnotationDialog.vue";

const { blurMode } = useBlurMode();
const { displaySrc } = useDisplaySrc(blurMode);
const { notify } = useNotify();

const keyframes = ref([]);
const selectedKeyframe = ref(null);
const loading = ref(false);
const keyframeDialog = ref(false);
const availableIdentities = ref([]);

const filters = ref({
  person_id: null,
  tag_reason: null,
  conflict_only: false,
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
  // Augment the static list with any trigger reasons present in the
  // current card set so caregivers can filter by any value seen.
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
const personOptions = ref([{ title: "Unknown", value: UNKNOWN_OPTION }]);

async function loadPersonOptions() {
  personsLoading.value = true;
  try {
    const data = await cts.getCorrectionTargets();
    const targets = (data?.targets || []).map((t) => ({
      title: t.display_name || t.identity_id,
      value: t.identity_id,
    }));
    personOptions.value = [{ title: "Unknown", value: UNKNOWN_OPTION }, ...targets];
  } catch (e) {
    console.error("Failed to load correction targets:", e);
  } finally {
    personsLoading.value = false;
  }
}

function toggleConflictOnly() {
  filters.value.conflict_only = !filters.value.conflict_only;
  loadKeyframes();
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
      conflict_only: filters.value.conflict_only,
      limit: filters.value.limit,
    });
    keyframes.value = data.keyframes || [];
    refreshTriggerReasons();
  } catch (e) {
    console.error("Failed to load keyframes:", e);
  } finally {
    loading.value = false;
  }
}

function keyframeImage(kf) {
  return kf.image_url || "";
}

async function viewKeyframe(kf) {
  selectedKeyframe.value = kf;
  try {
    const identities = await cts.getIdentities().catch(() => ({ identities: [] }));
    availableIdentities.value = identities?.identities || [];
  } catch {
    availableIdentities.value = [];
  }
  keyframeDialog.value = true;
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

async function onAnnotationSaved() {
  notify.success("Annotations saved");
  await loadKeyframes();
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
