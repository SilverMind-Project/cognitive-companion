<template>
  <div>
    <!-- Header -->
    <div class="d-flex align-center mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Camera Media</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Recently aggregated images per camera. Shows flushed images still within
          their retention window and the count of images pending flush.
        </div>
      </div>
      <v-spacer />
      <v-btn
        variant="tonal"
        prepend-icon="mdi-refresh"
        :loading="loading"
        @click="loadData"
      >
        Refresh
      </v-btn>
    </div>

    <!-- Filters toolbar -->
    <v-card class="mb-4" variant="outlined">
      <v-card-text class="py-3">
        <v-row align="center" dense>
          <v-col cols="12" sm="4" md="3">
            <v-select
              v-model="filterSensorId"
              :items="sensorOptions"
              item-title="label"
              item-value="value"
              label="Camera"
              variant="outlined"
              density="compact"
              clearable
              hide-details
              @update:model-value="loadData"
            />
          </v-col>
          <v-col cols="12" sm="4" md="3">
            <v-select
              v-model="sortOrder"
              :items="sortOptions"
              label="Sort images by"
              variant="outlined"
              density="compact"
              hide-details
            />
          </v-col>
          <v-col cols="12" sm="4" md="3">
            <v-select
              v-model="limitPerSensor"
              :items="[5, 10, 20, 50]"
              label="Images per camera"
              variant="outlined"
              density="compact"
              hide-details
              @update:model-value="loadData"
            />
          </v-col>
          <v-col cols="12" sm="12" md="3" class="d-flex align-center gap-2">
            <v-switch
              v-model="autoRefresh"
              label="Auto-refresh"
              color="primary"
              density="compact"
              hide-details
              class="mr-4"
            />
            <v-chip
              v-if="autoRefresh"
              size="small"
              color="primary"
              variant="tonal"
              prepend-icon="mdi-timer-outline"
            >
              {{ AUTO_REFRESH_SECONDS }}s
            </v-chip>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <!-- No cameras -->
    <v-alert v-if="!loading && cameras.length === 0" type="info" variant="tonal">
      No enabled camera sensors found.
    </v-alert>

    <!-- Per-camera panels -->
    <div v-for="cam in cameras" :key="cam.sensor_id" class="mb-6">
      <div class="d-flex align-center mb-3">
        <v-icon size="20" class="mr-2 text-medium-emphasis">mdi-camera</v-icon>
        <span class="text-subtitle-1 font-weight-bold">{{ cam.sensor_name }}</span>
        <v-chip
          v-if="cam.room_name"
          size="x-small"
          variant="tonal"
          color="secondary"
          class="ml-2"
        >
          {{ cam.room_name }}
        </v-chip>
        <v-chip
          v-if="cam.buffer_pending > 0"
          size="x-small"
          color="warning"
          variant="tonal"
          prepend-icon="mdi-clock-outline"
          class="ml-2"
        >
          {{ cam.buffer_pending }} pending flush
        </v-chip>
        <v-chip
          v-if="cam.cooldown_remaining_seconds !== null"
          size="x-small"
          color="info"
          variant="tonal"
          prepend-icon="mdi-timer-sand"
          class="ml-2"
        >
          cooldown {{ cam.cooldown_remaining_seconds }}s
        </v-chip>
        <v-spacer />
        <span class="text-caption text-medium-emphasis">
          {{ cam.images.length }} image{{ cam.images.length !== 1 ? 's' : '' }}
        </span>
      </div>

      <!-- Image grid -->
      <div v-if="cam.images.length > 0" class="image-grid">
        <v-card
          v-for="img in sortedImages(cam.images)"
          :key="img.id"
          class="image-card"
          variant="outlined"
          @click="openLightbox(img, cam)"
        >
          <v-img
            :src="img.url"
            aspect-ratio="16/9"
            cover
            class="image-thumb"
          >
            <template #placeholder>
              <div class="d-flex align-center justify-center fill-height">
                <v-progress-circular indeterminate color="primary" size="24" />
              </div>
            </template>
            <template #error>
              <div class="d-flex flex-column align-center justify-center fill-height broken-placeholder">
                <v-icon size="32" color="grey-lighten-1">mdi-image-broken-variant</v-icon>
                <span class="text-caption text-disabled mt-1">Expired</span>
              </div>
            </template>
          </v-img>
          <v-card-text class="pa-2">
            <div class="text-caption font-weight-medium">{{ formatTimestamp(img.captured_at) }}</div>
            <div class="text-caption text-medium-emphasis">
              expires {{ formatRelative(img.expires_at) }}
            </div>
          </v-card-text>
        </v-card>
      </div>

      <v-alert
        v-else
        type="info"
        variant="tonal"
        density="compact"
        class="mt-1"
      >
        No flushed images in retention window
        <span v-if="cam.buffer_pending > 0">
          &mdash; {{ cam.buffer_pending }} image{{ cam.buffer_pending !== 1 ? 's' : '' }} pending flush.
        </span>
      </v-alert>
    </div>

    <!-- Lightbox dialog -->
    <v-dialog v-model="lightbox.open" max-width="900" scrollable>
      <v-card v-if="lightbox.image">
        <v-card-title class="d-flex align-center pa-4 pb-2">
          <v-icon size="18" class="mr-2">mdi-camera</v-icon>
          {{ lightbox.sensorName }}
          <v-chip v-if="lightbox.roomName" size="x-small" variant="tonal" class="ml-2">
            {{ lightbox.roomName }}
          </v-chip>
          <v-spacer />
          <v-btn icon="mdi-close" size="small" variant="text" @click="lightbox.open = false" />
        </v-card-title>

        <v-img
          :src="lightbox.image.url"
          max-height="600"
          contain
          class="mx-4"
        >
          <template #placeholder>
            <div class="d-flex align-center justify-center" style="height: 400px">
              <v-progress-circular indeterminate color="primary" />
            </div>
          </template>
        </v-img>

        <v-card-text class="pt-3">
          <v-row dense>
            <v-col cols="6">
              <div class="text-caption text-medium-emphasis">Captured</div>
              <div class="text-body-2">{{ formatTimestampFull(lightbox.image.captured_at) }}</div>
            </v-col>
            <v-col cols="6">
              <div class="text-caption text-medium-emphasis">Expires</div>
              <div class="text-body-2">{{ formatTimestampFull(lightbox.image.expires_at) }}</div>
            </v-col>
            <v-col cols="12" class="mt-1">
              <div class="text-caption text-medium-emphasis">Object</div>
              <div class="text-caption font-weight-medium" style="word-break: break-all">
                {{ lightbox.image.object_name }}
              </div>
            </v-col>
          </v-row>
        </v-card-text>

        <v-card-actions class="px-4 pb-4">
          <v-btn
            variant="tonal"
            prepend-icon="mdi-chevron-left"
            :disabled="lightbox.index <= 0"
            @click="moveLightbox(-1)"
          >
            Prev
          </v-btn>
          <v-spacer />
          <span class="text-caption text-medium-emphasis">
            {{ lightbox.index + 1 }} / {{ lightbox.images.length }}
          </span>
          <v-spacer />
          <v-btn
            variant="tonal"
            append-icon="mdi-chevron-right"
            :disabled="lightbox.index >= lightbox.images.length - 1"
            @click="moveLightbox(1)"
          >
            Next
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snack" color="error" timeout="4000">{{ snackText }}</v-snackbar>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from "vue";
import { api } from "../../services/api.js";
import { formatDateTimeShort, formatDateTimeFull } from "../../services/timezone.js";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const AUTO_REFRESH_SECONDS = 15;

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const cameras = ref([]);
const loading = ref(false);
const snack = ref(false);
const snackText = ref("");

const filterSensorId = ref(null);
const sortOrder = ref("desc");
const limitPerSensor = ref(20);
const autoRefresh = ref(false);

let autoRefreshTimer = null;

// Lightbox
const lightbox = ref({
  open: false,
  image: null,
  sensorName: "",
  roomName: null,
  images: [],
  index: 0,
});

// ---------------------------------------------------------------------------
// Derived
// ---------------------------------------------------------------------------
const sortOptions = [
  { title: "Newest first", value: "desc" },
  { title: "Oldest first", value: "asc" },
];

const sensorOptions = computed(() => {
  // Populated from the last successful load; we collect all sensors regardless
  // of the current filter so the dropdown always shows all cameras.
  return [
    { label: "All cameras", value: null },
    ...cameras.value.map((c) => ({
      label: c.room_name ? `${c.sensor_name} (${c.room_name})` : c.sensor_name,
      value: c.sensor_id,
    })),
  ];
});

function sortedImages(images) {
  const copy = [...images];
  copy.sort((a, b) => {
    const ta = new Date(a.captured_at).getTime();
    const tb = new Date(b.captured_at).getTime();
    return sortOrder.value === "asc" ? ta - tb : tb - ta;
  });
  return copy;
}

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------
async function loadData() {
  loading.value = true;
  const params = { limit: limitPerSensor.value };
  if (filterSensorId.value) params.sensor_id = filterSensorId.value;
  try {
    cameras.value = await api.getMediaBuffer(params);
  } catch (e) {
    snackText.value = e.message || "Failed to load camera media";
    snack.value = true;
    cameras.value = [];
  } finally {
    loading.value = false;
  }
}

// ---------------------------------------------------------------------------
// Auto-refresh
// ---------------------------------------------------------------------------
function startAutoRefresh() {
  stopAutoRefresh();
  autoRefreshTimer = setInterval(loadData, AUTO_REFRESH_SECONDS * 1000);
}

function stopAutoRefresh() {
  if (autoRefreshTimer !== null) {
    clearInterval(autoRefreshTimer);
    autoRefreshTimer = null;
  }
}

watch(autoRefresh, (enabled) => {
  if (enabled) startAutoRefresh();
  else stopAutoRefresh();
});

// ---------------------------------------------------------------------------
// Lightbox
// ---------------------------------------------------------------------------
function openLightbox(img, cam) {
  const sorted = sortedImages(cam.images);
  lightbox.value = {
    open: true,
    image: img,
    sensorName: cam.sensor_name,
    roomName: cam.room_name,
    images: sorted,
    index: sorted.findIndex((i) => i.id === img.id),
  };
}

function moveLightbox(delta) {
  const next = lightbox.value.index + delta;
  if (next < 0 || next >= lightbox.value.images.length) return;
  lightbox.value.index = next;
  lightbox.value.image = lightbox.value.images[next];
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------
const formatTimestamp = formatDateTimeShort;
const formatTimestampFull = formatDateTimeFull;

function formatRelative(iso) {
  if (!iso) return "";
  const diff = new Date(iso).getTime() - Date.now();
  if (diff <= 0) return "now";
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "< 1 min";
  if (mins < 60) return `${mins} min`;
  return `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------
onMounted(loadData);
onUnmounted(stopAutoRefresh);
</script>

<style scoped>
.tracking-tight {
  letter-spacing: -0.018em;
}

.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}

.image-card {
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.image-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px -8px rgba(0, 0, 0, 0.35);
}

.image-thumb {
  border-radius: 4px 4px 0 0;
}

.broken-placeholder {
  background: rgba(0, 0, 0, 0.04);
  height: 100%;
}
</style>
