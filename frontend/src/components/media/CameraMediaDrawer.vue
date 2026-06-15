<template>
  <div class="h-100 d-flex flex-column">
    <div class="d-flex align-center px-4 py-3">
      <div>
        <div class="text-subtitle-1 font-weight-semibold">{{ cameraName }}</div>
        <div class="text-caption text-medium-emphasis">{{ camera.camera_id }}</div>
      </div>
      <v-spacer />
      <v-btn icon="mdi-close" variant="text" size="small" @click="emit('close')" />
    </div>
    <v-divider />

    <div class="flex-grow-1 overflow-y-auto" style="min-height: 0">
      <div class="pa-4">
        <div class="d-flex flex-wrap ga-2 mb-4">
          <v-chip size="small" variant="tonal" :color="originColor">
            {{ originLabel }}
          </v-chip>
          <v-chip v-if="camera.room_name" size="small" variant="tonal">
            {{ camera.room_name }}
          </v-chip>
          <v-chip size="small" variant="tonal">{{ camera.buffer_depth }} buffered</v-chip>
        </div>

        <div class="text-subtitle-2 font-weight-bold mb-2">Depth trend</div>
        <div class="drawer-chart mb-5">
          <CcTimeSeriesChart :series="historySeries" unit="frames" />
        </div>

        <v-row dense class="mb-4">
          <v-col cols="6">
            <div class="text-caption text-medium-emphasis">Rate ceiling</div>
            <div class="text-body-2">{{ formatRate(camera.rate_per_second) }}</div>
          </v-col>
          <v-col cols="6">
            <div class="text-caption text-medium-emphasis">Tokens available</div>
            <div class="text-body-2">{{ formatTokens(camera.tokens_available) }}</div>
          </v-col>
          <v-col cols="6">
            <div class="text-caption text-medium-emphasis">Image-eligible</div>
            <div class="text-body-2">{{ camera.images_eligible_total }}</div>
          </v-col>
          <v-col cols="6">
            <div class="text-caption text-medium-emphasis">Dropped</div>
            <div class="text-body-2">{{ camera.images_dropped_total }}</div>
          </v-col>
          <v-col cols="12">
            <div class="text-caption text-medium-emphasis">Last event</div>
            <div class="text-body-2">
              {{ camera.last_event_at
                ? formatDateTimeFull(camera.last_event_at)
                : "No events recorded" }}
            </div>
          </v-col>
        </v-row>

        <template v-if="camera.origin === 'recamera'">
          <div class="d-flex align-center mb-2">
            <div class="text-subtitle-2 font-weight-bold">Recent retained images</div>
            <v-spacer />
            <v-progress-circular
              v-if="mediaLoading"
              indeterminate
              color="primary"
              size="20"
              width="2"
            />
          </div>
          <v-alert
            v-if="mediaError"
            type="error"
            variant="tonal"
            density="compact"
            class="mb-3"
          >
            {{ mediaError }}
          </v-alert>
          <div v-if="media?.images?.length" class="image-grid">
            <v-card
              v-for="image in media.images"
              :key="image.id"
              class="image-card"
              variant="outlined"
              @click="openLightbox(image)"
            >
              <v-img :src="image.url" aspect-ratio="16/9" cover class="image-thumb">
                <template #placeholder>
                  <div class="d-flex align-center justify-center fill-height">
                    <v-progress-circular indeterminate color="primary" size="24" />
                  </div>
                </template>
                <template #error>
                  <div class="broken-placeholder d-flex flex-column align-center justify-center fill-height">
                    <v-icon size="32" color="medium-emphasis">mdi-image-broken-variant</v-icon>
                    <span class="text-caption text-disabled mt-1">Expired</span>
                  </div>
                </template>
              </v-img>
              <v-card-text class="pa-2">
                <div class="text-caption font-weight-medium">
                  {{ formatDateTimeShort(image.captured_at) }}
                </div>
                <div class="text-caption text-medium-emphasis">
                  Expires {{ formatDateTimeShort(image.expires_at) }}
                </div>
              </v-card-text>
            </v-card>
          </div>
          <v-alert
            v-else-if="!mediaLoading && !mediaError"
            type="info"
            variant="tonal"
            density="compact"
          >
            No retained images are available for this camera.
          </v-alert>
        </template>

        <v-alert v-else type="info" variant="tonal" density="compact">
          CTS image references remain in the live media window and are not exposed by the
          retained reCamera media endpoint. Buffer history and rate-limit telemetry remain
          available here.
        </v-alert>
      </div>
    </div>

    <v-dialog v-model="lightbox.open" max-width="900" scrollable>
      <v-card v-if="lightbox.image">
        <v-card-title class="d-flex align-center pa-4 pb-2">
          <v-icon size="18" class="mr-2">mdi-camera</v-icon>
          {{ cameraName }}
          <v-spacer />
          <v-btn icon="mdi-close" size="small" variant="text" @click="lightbox.open = false" />
        </v-card-title>
        <v-img :src="lightbox.image.url" max-height="600" contain class="mx-4">
          <template #placeholder>
            <div class="d-flex align-center justify-center lightbox-placeholder">
              <v-progress-circular indeterminate color="primary" />
            </div>
          </template>
        </v-img>
        <v-card-text class="pt-3">
          <v-row dense>
            <v-col cols="6">
              <div class="text-caption text-medium-emphasis">Captured</div>
              <div class="text-body-2">{{ formatDateTimeFull(lightbox.image.captured_at) }}</div>
            </v-col>
            <v-col cols="6">
              <div class="text-caption text-medium-emphasis">Expires</div>
              <div class="text-body-2">{{ formatDateTimeFull(lightbox.image.expires_at) }}</div>
            </v-col>
            <v-col cols="12">
              <div class="text-caption text-medium-emphasis">Object</div>
              <div class="text-caption font-weight-medium object-name">
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
  </div>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import CcTimeSeriesChart from "@/components/charts/CcTimeSeriesChart.vue";
import { useNotify } from "@/composables/useNotify.js";
import { api } from "@/services/api.js";
import { formatDateTimeFull, formatDateTimeShort } from "@/services/timezone.js";

const props = defineProps({
  camera: { type: Object, required: true },
  history: { type: Array, default: () => [] },
});

const emit = defineEmits(["close"]);
const { notify } = useNotify();
const media = ref(null);
const mediaLoading = ref(false);
const mediaError = ref(null);
const lightbox = ref({ open: false, image: null, images: [], index: 0 });

const cameraName = computed(() => props.camera.display_name || props.camera.camera_id);
const originLabel = computed(() => props.camera.origin === "recamera" ? "reCamera" : "CTS");
const originColor = computed(() => props.camera.origin === "recamera" ? "primary" : "info");
const historySeries = computed(() => [{
  name: "Buffer depth",
  points: props.history.map((point) => ({ t: point.t, v: point.depth })),
}]);

function formatRate(value) {
  return value == null ? "n/a" : `${Number(value).toFixed(2)}/s`;
}

function formatTokens(value) {
  return value == null ? "n/a" : Number(value).toFixed(1);
}

async function loadMedia() {
  media.value = null;
  mediaError.value = null;
  if (props.camera.origin !== "recamera") return;

  mediaLoading.value = true;
  try {
    const response = await api.getMediaBuffer({ sensor_id: props.camera.camera_id, limit: 20 });
    media.value = response.items[0] ?? null;
  } catch (error) {
    mediaError.value = error?.message || "Failed to load retained images";
    notify.error(mediaError.value);
  } finally {
    mediaLoading.value = false;
  }
}

function openLightbox(image) {
  const images = media.value?.images ?? [];
  lightbox.value = {
    open: true,
    image,
    images,
    index: images.findIndex((candidate) => candidate.id === image.id),
  };
}

function moveLightbox(delta) {
  const next = lightbox.value.index + delta;
  if (next < 0 || next >= lightbox.value.images.length) return;
  lightbox.value.index = next;
  lightbox.value.image = lightbox.value.images[next];
}

watch(() => props.camera.camera_id, loadMedia, { immediate: true });
</script>

<style scoped>
.drawer-chart {
  height: 220px;
}

.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
}

.image-card {
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.image-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--cc-shadow-md);
}

.image-thumb {
  border-radius: var(--cc-radius-xs) var(--cc-radius-xs) 0 0;
}

.broken-placeholder {
  background: var(--cc-surface-3);
  height: 100%;
}

.lightbox-placeholder {
  height: 400px;
}

.object-name {
  word-break: break-all;
}
</style>
