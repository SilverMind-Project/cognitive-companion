<template>
  <div>
    <div class="d-flex align-center mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Homography Calibration</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Map pixel coordinates to floor-plan metres by clicking 4+ matching points.
        </div>
      </div>
      <v-spacer />
      <v-select
        v-model="selectedCameraId"
        :items="cameras"
        item-title="name"
        item-value="id"
        label="Camera"
        variant="outlined"
        density="compact"
        hide-details
        style="max-width: 260px"
        @update:model-value="onCameraChange"
      />
    </div>

    <v-row v-if="selectedCameraId">
      <!-- Left: camera snapshot with point picker -->
      <v-col cols="12" md="7">
        <v-card>
          <v-card-title class="d-flex align-center">
            <span>Camera Frame</span>
            <v-spacer />
            <v-btn size="small" variant="tonal" prepend-icon="mdi-camera" @click="loadSnapshot">
              Refresh Snapshot
            </v-btn>
          </v-card-title>
          <v-card-text class="pa-0 position-relative">
            <div class="snapshot-container" @click="onCanvasClick">
              <img
                v-if="snapshotUrl"
                ref="imgEl"
                :src="snapshotUrl"
                class="snapshot-img"
                draggable="false"
                @load="onImageLoad"
              />
              <div v-else class="d-flex align-center justify-center" style="height: 320px">
                <v-progress-circular v-if="snapshotLoading" indeterminate />
                <span v-else class="text-medium-emphasis">Click "Refresh Snapshot" to load a frame.</span>
              </div>
              <!-- Overlay dots for placed pixel points -->
              <svg
                v-if="snapshotUrl && imgRect"
                class="point-overlay"
                :viewBox="`0 0 ${imgRect.width} ${imgRect.height}`"
                :style="`width:${imgRect.width}px;height:${imgRect.height}px;`"
              >
                <circle
                  v-for="(pt, i) in points"
                  :key="i"
                  :cx="pt.pixel[0] * imgRect.width"
                  :cy="pt.pixel[1] * imgRect.height"
                  r="7"
                  fill="none"
                  style="stroke: var(--cc-brand); stroke-width: 2.5"
                />
                <text
                  v-for="(pt, i) in points"
                  :key="`t${i}`"
                  :x="pt.pixel[0] * imgRect.width + 10"
                  :y="pt.pixel[1] * imgRect.height - 6"
                  style="fill: var(--cc-brand)"
                  font-size="12"
                  font-weight="bold"
                >{{ i + 1 }}</text>
              </svg>
            </div>
            <div class="text-caption text-medium-emphasis pa-2">
              {{ points.length < 4
                ? `Click to place point ${points.length + 1} (need ${4 - points.length} more)`
                : `${points.length} points placed: enter floor coords on the right, then calibrate.`
              }}
            </div>
          </v-card-text>
        </v-card>
      </v-col>

      <!-- Right: floor coordinate inputs + result -->
      <v-col cols="12" md="5">
        <v-card class="mb-4">
          <v-card-title>Point Correspondences</v-card-title>
          <v-card-text>
            <div v-if="points.length === 0" class="text-medium-emphasis text-body-2">
              No points placed yet. Click on the camera frame to add points.
            </div>
            <div v-for="(pt, i) in points" :key="i" class="mb-3">
              <div class="d-flex align-center mb-1">
                <v-chip size="x-small" color="primary" class="mr-2">{{ i + 1 }}</v-chip>
                <span class="text-body-2">
                  Pixel: ({{ (pt.pixel[0] * 100).toFixed(1) }}%, {{ (pt.pixel[1] * 100).toFixed(1) }}%)
                </span>
                <v-spacer />
                <v-btn icon="mdi-close" size="x-small" variant="text" @click="removePoint(i)" />
              </div>
              <v-row dense>
                <v-col cols="6">
                  <v-text-field
                    v-model.number="pt.floor_m[0]"
                    label="Floor X (m)"
                    variant="outlined"
                    density="compact"
                    type="number"
                    step="0.1"
                    hide-details
                  />
                </v-col>
                <v-col cols="6">
                  <v-text-field
                    v-model.number="pt.floor_m[1]"
                    label="Floor Y (m)"
                    variant="outlined"
                    density="compact"
                    type="number"
                    step="0.1"
                    hide-details
                  />
                </v-col>
              </v-row>
            </div>
          </v-card-text>
          <v-card-actions class="px-4 pb-4">
            <v-btn variant="text" :disabled="points.length === 0" @click="clearPoints">
              Clear All
            </v-btn>
            <v-spacer />
            <v-btn
              color="primary"
              variant="flat"
              :loading="calibrating"
              :disabled="points.length < 4"
              @click="runCalibration"
            >
              Calibrate
            </v-btn>
          </v-card-actions>
        </v-card>

        <!-- Result card -->
        <v-card v-if="result">
          <v-card-title class="d-flex align-center">
            <span>Result</span>
            <v-spacer />
            <v-chip
              :color="result.status === 'ok' ? 'success' : result.status === 'warning' ? 'warning' : 'error'"
              size="small"
            >
              {{ result.status.toUpperCase() }}
            </v-chip>
          </v-card-title>
          <v-card-text>
            <div class="text-body-2 mb-2">
              Max reprojection error: <strong>{{ result.max_residual_m.toFixed(3) }} m</strong>
            </div>
            <v-table density="compact">
              <thead>
                <tr><th>Pt</th><th>Residual (m)</th></tr>
              </thead>
              <tbody>
                <tr v-for="(r, i) in result.residuals_m" :key="i">
                  <td>{{ i + 1 }}</td>
                  <td>{{ r.toFixed(4) }}</td>
                </tr>
              </tbody>
            </v-table>
          </v-card-text>
        </v-card>

        <!-- Existing calibration indicator -->
        <v-card v-else-if="existingCalibration" class="mt-0">
          <v-card-text>
            <v-icon color="success" class="mr-1">mdi-check-circle</v-icon>
            <span class="text-body-2">This camera is already calibrated.</span>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <v-alert v-else type="info" variant="tonal" class="mt-4">
      Select a camera from the dropdown to begin calibration.
    </v-alert>

    <v-snackbar v-model="snack" :color="snackColor" timeout="4000">{{ snackText }}</v-snackbar>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from "vue";
import { cts } from "../../services/cts.js";
import { useNotify } from "../../composables/useNotify.js";

const { snack, snackText, snackColor, notify } = useNotify();

const cameras = ref([]);
const selectedCameraId = ref(null);
const snapshotUrl = ref(null);
const snapshotLoading = ref(false);
const imgEl = ref(null);
const imgRect = ref(null);
const points = ref([]);
const calibrating = ref(false);
const result = ref(null);
const existingCalibration = ref(false);

async function loadCameras() {
  try {
    cameras.value = await cts.getCameras();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function onCameraChange() {
  points.value = [];
  result.value = null;
  snapshotUrl.value = null;
  imgRect.value = null;
  existingCalibration.value = false;
  await Promise.all([loadSnapshot(), loadExistingCalibration()]);
}

async function loadSnapshot() {
  if (!selectedCameraId.value) return;
  snapshotLoading.value = true;
  if (snapshotUrl.value) {
    URL.revokeObjectURL(snapshotUrl.value);
    snapshotUrl.value = null;
  }
  try {
    snapshotUrl.value = await cts.getSnapshot(selectedCameraId.value);
  } catch (e) {
    notify(`Snapshot failed: ${e.message}`, "warning");
  } finally {
    snapshotLoading.value = false;
  }
}

async function loadExistingCalibration() {
  if (!selectedCameraId.value) return;
  try {
    await cts.getHomography(selectedCameraId.value);
    existingCalibration.value = true;
  } catch {
    existingCalibration.value = false;
  }
}

function onImageLoad() {
  if (!imgEl.value) return;
  const r = imgEl.value.getBoundingClientRect();
  imgRect.value = { width: r.width, height: r.height };
}

function onCanvasClick(e) {
  if (!snapshotUrl.value || !imgEl.value) return;
  const r = imgEl.value.getBoundingClientRect();
  const x = (e.clientX - r.left) / r.width;
  const y = (e.clientY - r.top) / r.height;
  if (x < 0 || x > 1 || y < 0 || y > 1) return;
  points.value.push({
    pixel: [parseFloat(x.toFixed(4)), parseFloat(y.toFixed(4))],
    floor_m: [0, 0],
  });
}

function removePoint(i) {
  points.value.splice(i, 1);
}

function clearPoints() {
  points.value = [];
  result.value = null;
}

async function runCalibration() {
  if (points.value.length < 4) return;
  calibrating.value = true;
  result.value = null;
  try {
    result.value = await cts.postHomography(selectedCameraId.value, points.value);
    notify("Calibration saved: status: " + result.value.status);
    existingCalibration.value = true;
  } catch (e) {
    notify(e.message, "error");
  } finally {
    calibrating.value = false;
  }
}

onMounted(loadCameras);
onBeforeUnmount(() => {
  if (snapshotUrl.value) URL.revokeObjectURL(snapshotUrl.value);
});
</script>

<style scoped>
.snapshot-container {
  position: relative;
  display: inline-block;
  width: 100%;
  cursor: crosshair;
  user-select: none;
}

.snapshot-img {
  display: block;
  width: 100%;
  max-height: 420px;
  object-fit: contain;
}

.point-overlay {
  position: absolute;
  top: 0;
  left: 0;
  pointer-events: none;
}
</style>
