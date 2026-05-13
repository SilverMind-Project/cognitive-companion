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
          <v-card class="keyframe-card" elevation="1">
            <v-img
              :src="keyframeImage(kf)"
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
                <div class="pa-2">
                  <v-chip v-if="kf.signal_type" size="x-small" color="primary">
                    {{ kf.signal_type.replace(/_/g, " ") }}
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
        <v-img :src="keyframeImage(selectedKeyframe)" height="400" cover />
        <v-card-title>Keyframe Details</v-card-title>
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
              <v-chip size="small" color="primary">
                {{ selectedKeyframe.signal_type?.replace(/_/g, " ") || "—" }}
              </v-chip>
            </v-col>
            <v-col cols="6">
              <div class="text-caption text-medium-emphasis">Quality</div>
              <v-progress-linear :model-value="selectedKeyframe.quality * 100" height="8" rounded />
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
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="detailDialog = false">Close</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { cts } from "../../services/cts.js";
import { severityColor } from "../../composables/useCtsSeverity";

const keyframes = ref([]);
const selectedKeyframe = ref(null);
const loading = ref(false);
const detailDialog = ref(false);

const filters = ref({
  person_id: null,
  signal_type: null,
  limit: 50,
});

const signalTypes = [
  "pacing",
  "room_revisit_rate",
  "bathroom_dwell_anomaly",
  "sundowning_index",
  "nighttime_movement",
  "stillness_anomaly",
  "absence",
];

const persons = computed(() => {
  const ids = new Set(keyframes.value.map((k) => k.person_id).filter(Boolean));
  return Array.from(ids).sort();
});

onMounted(() => {
  loadKeyframes();
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
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
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
</style>
