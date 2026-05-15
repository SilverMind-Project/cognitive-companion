<template>
  <div>
    <div class="d-flex align-center mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Live Tracking</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Per-camera bbox overlay. Click a tracked identity to issue a manual
          correction. Revisions surface as toasts.
        </div>
      </div>
      <v-spacer />
      <v-chip
        :color="wsStatusColor"
        prepend-icon="mdi-circle"
        size="small"
        variant="tonal"
      >
        {{ wsStatus }}
      </v-chip>
    </div>

    <v-alert
      v-if="error"
      type="error"
      class="mb-4"
      closable
      @click:close="error = ''"
    >
      {{ error }}
    </v-alert>

    <v-card class="glass-card">
      <v-card-text class="d-flex ga-4 align-center pa-4">
        <v-select
          v-model="layout"
          :items="layoutOptions"
          item-title="label"
          item-value="value"
          label="Layout"
          variant="outlined"
          density="compact"
          hide-details
          style="max-width: 200px"
        />
        <v-switch
          v-model="showBboxes"
          color="primary"
          label="Show bboxes"
          density="compact"
          hide-details
        />
        <v-switch
          v-model="showIdLabels"
          color="primary"
          label="Show identity labels"
          density="compact"
          hide-details
        />
        <v-spacer />
        <v-btn
          variant="tonal"
          prepend-icon="mdi-account-edit"
          :to="{ name: 'cts-identity-corrections' }"
        >
          Manage corrections
        </v-btn>
      </v-card-text>

      <v-divider />

      <div :class="gridClass" class="pa-4 ga-4 live-grid">
        <v-card
          v-for="slot in slots"
          :key="slot"
          class="live-tile"
          variant="outlined"
        >
          <v-card-text class="d-flex align-center justify-space-between pa-2">
            <v-chip size="small" variant="tonal">{{
              cameraIdForSlot(slot) || "—"
            }}</v-chip>
            <span class="text-caption text-medium-emphasis">
              {{ cameraForSlot(slot)?.detections?.length || 0 }} detections
            </span>
          </v-card-text>
          <div
            class="live-tile-frame"
            :class="{ 'live-tile-stale': isCameraStale(cameraForSlot(slot)) }"
            :aria-label="`Live camera ${cameraIdForSlot(slot) || slot}`"
          >
            <img
              v-if="cameraForSlot(slot)?.frame_url"
              :src="cameraForSlot(slot).frame_url"
              class="live-tile-img"
              alt=""
              @error="onFrameError($event, cameraForSlot(slot))"
            />
            <img
              v-else-if="snapshotUrls[cameraIdForSlot(slot)]"
              :src="snapshotUrls[cameraIdForSlot(slot)]"
              class="live-tile-img"
              alt=""
            />
            <div
              v-else
              class="live-tile-no-frame"
            >
              <v-icon size="24" color="medium-emphasis">mdi-video-off-outline</v-icon>
            </div>
            <svg
              v-if="cameraForSlot(slot) && showBboxes"
              :viewBox="`0 0 ${cameraForSlot(slot).frame_width || 1920} ${cameraForSlot(slot).frame_height || 1080}`"
              class="live-tile-overlay"
              preserveAspectRatio="xMidYMid meet"
            >
              <g
                v-for="(det, idx) in cameraForSlot(slot).detections"
                :key="idx"
              >
                <rect
                  :x="det.bbox.x_min || 0"
                  :y="det.bbox.y_min || 0"
                  :width="(det.bbox.x_max || 0) - (det.bbox.x_min || 0)"
                  :height="(det.bbox.y_max || 0) - (det.bbox.y_min || 0)"
                  fill="none"
                  :stroke="det.identity_id ? 'var(--cc-success)' : 'var(--cc-warning)'"
                  stroke-width="3"
                  @click="openCorrection(det, cameraForSlot(slot))"
                  style="cursor: pointer"
                />
                <text
                  v-if="showIdLabels"
                  :x="(det.bbox.x_min || 0) + 8"
                  :y="(det.bbox.y_min || 0) + 20"
                  fill="var(--cc-text-1)"
                  font-size="36"
                  font-weight="bold"
                  style="paint-order: stroke; stroke: rgba(0, 0, 0, 0.6); stroke-width: 3"
                >
                  {{ det.identity_id || "unknown" }}
                </text>
              </g>
            </svg>
            <div
              v-if="isCameraStale(cameraForSlot(slot))"
              class="live-tile-stale-badge"
            >
              <v-icon size="12" class="mr-1">mdi-clock-alert-outline</v-icon>
              Last seen {{ staleLabel(cameraForSlot(slot)) }}
            </div>
          </div>
        </v-card>
      </div>
    </v-card>

    <v-snackbar v-model="revisionToast" :timeout="3500" color="info">
      {{ revisionToastText }}
    </v-snackbar>

    <v-dialog v-model="correctionOpen" max-width="520" persistent>
      <v-card>
        <DialogHeader
          icon="mdi-account-convert"
          label="Correct"
          title="Identity"
          @close="correctionOpen = false"
        />
        <v-card-text>
          <div class="text-body-2 mb-2">
            GlobalTrack: <strong>{{ correction.global_track_id }}</strong>
          </div>
          <div class="text-body-2 mb-2">
            Camera: {{ correction.camera_id }}
          </div>
          <div class="text-body-2 mb-4">
            Current identity: {{ correction.previous_identity_id || "unknown" }}
          </div>
          <v-text-field
            v-model="correction.new_identity_id"
            label="New identity id"
            variant="outlined"
            placeholder="Leave blank to mark as UNKNOWN"
          />
          <v-text-field
            v-model="correction.reason"
            label="Reason"
            variant="outlined"
          />
        </v-card-text>
        <DialogFooter
          hint="Correct misidentified persons to improve tracking accuracy."
          confirm-label="Apply override"
          :confirm-loading="saving"
          @cancel="correctionOpen = false"
          @confirm="submitCorrection"
        />
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, computed, reactive, onMounted, onUnmounted } from "vue";
import { cts } from "@/services/cts";
import { useCtsWebSocket } from "@/composables/useCtsWebSocket.js";
import DialogHeader from "@/components/common/DialogHeader.vue";
import DialogFooter from "@/components/common/DialogFooter.vue";

const STALE_THRESHOLD_S = 15;
const SNAPSHOT_POLL_MS = 5_000;

const error = ref("");
const layout = ref(4);
const layoutOptions = [
  { label: "1 camera", value: 1 },
  { label: "4 cameras (2x2)", value: 4 },
  { label: "9 cameras (3x3)", value: 9 },
  { label: "16 cameras (4x4)", value: 16 },
];
const showBboxes = ref(true);
const showIdLabels = ref(true);

const cameras = ref({});
// camera_id → blob URL for go2rtc snapshot (fallback when WS is idle)
const snapshotUrls = ref({});
// Camera IDs loaded from the API on mount (ensures slots populate before first WS event)
const knownCameraIds = ref([]);
const now = ref(Date.now());
let _freshnessTimer = null;
let _snapshotTimer = null;

async function loadKnownCameras() {
  try {
    const data = await cts.getCameras();
    knownCameraIds.value = (data.cameras || []).map((c) => c.camera_id);
    console.debug("[cts_live] cameras loaded", {
      count: knownCameraIds.value.length,
      ids: knownCameraIds.value,
    });
  } catch (err) {
    console.warn("[cts_live] camera list fetch failed", err);
  }
}

async function pollSnapshots() {
  const ids = [
    ...new Set([...knownCameraIds.value, ...Object.keys(cameras.value)]),
  ];
  console.debug("[cts_live] polling snapshots", { camera_count: ids.length, ids });
  await Promise.allSettled(
    ids.map(async (id) => {
      try {
        const url = await cts.getSnapshot(id);
        if (snapshotUrls.value[id]) URL.revokeObjectURL(snapshotUrls.value[id]);
        snapshotUrls.value = { ...snapshotUrls.value, [id]: url };
        console.debug("[cts_live] snapshot fetched", { camera_id: id });
      } catch (err) {
        console.warn("[cts_live] snapshot fetch failed", { camera_id: id, error: String(err) });
      }
    })
  );
}

onMounted(async () => {
  _freshnessTimer = setInterval(() => { now.value = Date.now(); }, 5000);
  await loadKnownCameras();
  pollSnapshots();
  _snapshotTimer = setInterval(pollSnapshots, SNAPSHOT_POLL_MS);
});
onUnmounted(() => {
  clearInterval(_freshnessTimer);
  clearInterval(_snapshotTimer);
  for (const url of Object.values(snapshotUrls.value)) URL.revokeObjectURL(url);
});

const revisionToast = ref(false);
const revisionToastText = ref("");
const correctionOpen = ref(false);
const saving = ref(false);
const correction = reactive({
  global_track_id: "",
  previous_identity_id: "",
  new_identity_id: "",
  camera_id: "",
  reason: "manual",
});

const slots = computed(() => Array.from({ length: layout.value }, (_, i) => i));

// Merged, sorted list of camera IDs (WS + static camera list from API)
const allCameraIds = computed(() => {
  const merged = new Set([...knownCameraIds.value, ...Object.keys(cameras.value)]);
  return [...merged].sort();
});

const gridClass = computed(() => {
  if (layout.value === 1) return "d-grid grid-1";
  if (layout.value === 4) return "d-grid grid-2";
  if (layout.value === 9) return "d-grid grid-3";
  return "d-grid grid-4";
});

const wsStatusColor = computed(() => {
  if (wsStatus.value === "open") return "success";
  if (wsStatus.value === "connecting") return "warning";
  return "error";
});

function onMessage(msg) {
  if (msg.type === "cts_live_frame") {
    if (!msg.camera_id) {
      console.warn("[cts_live] WS frame missing camera_id", msg);
      return;
    }
    console.debug("[cts_live] WS frame received", {
      camera_id: msg.camera_id,
      has_frame_url: !!msg.frame_url,
      has_minio_key: !!msg.minio_key,
      detection_count: msg.detections?.length ?? 0,
    });
    cameras.value = {
      ...cameras.value,
      [msg.camera_id]: {
        camera_id: msg.camera_id,
        detections: msg.detections || [],
        event_time: msg.event_time,
        room_name: msg.room_name,
        minio_key: msg.minio_key || null,
        frame_url: msg.frame_url || null,
        frame_width: msg.frame_width || 1920,
        frame_height: msg.frame_height || 1080,
        lastSeenMs: Date.now(),
      },
    };
  } else if (msg.type === "cts_identity_revision") {
    const prev = msg.previous_identity_id || "unknown";
    const next = msg.new_identity_id || "unknown";
    revisionToastText.value = `Identity corrected: ${prev} → ${next}`;
    revisionToast.value = true;
  } else {
    console.debug("[cts_live] WS unknown message type", msg.type, Object.keys(msg));
  }
}

const { status: wsStatus } = useCtsWebSocket(onMessage);

function cameraIdForSlot(slot) {
  return allCameraIds.value[slot] ?? null;
}

function cameraForSlot(slot) {
  const id = cameraIdForSlot(slot);
  return id ? cameras.value[id] ?? null : null;
}

function onFrameError(_event, cam) {
  const cameraId = cam?.camera_id;
  if (!cameraId || !cameras.value[cameraId]) return;
  console.warn("[cts_live] frame_url load failed", {
    camera_id: cameraId,
    prev_frame_url: cameras.value[cameraId].frame_url?.substring(0, 80),
  });
  cameras.value = {
    ...cameras.value,
    [cameraId]: { ...cameras.value[cameraId], frame_url: null },
  };
}

function cameraAgeS(cam) {
  if (!cam?.lastSeenMs) return null;
  return (now.value - cam.lastSeenMs) / 1000;
}

function isCameraStale(cam) {
  const age = cameraAgeS(cam);
  return age !== null && age > STALE_THRESHOLD_S;
}

function staleLabel(cam) {
  const age = cameraAgeS(cam);
  if (age === null) return "";
  if (age < 60) return `${Math.round(age)}s ago`;
  return `${Math.round(age / 60)}m ago`;
}

function openCorrection(det, cam) {
  correction.global_track_id = det.global_track_id;
  correction.previous_identity_id = det.identity_id || "";
  correction.new_identity_id = "";
  correction.camera_id = cam?.camera_id || "";
  correction.reason = "manual";
  correctionOpen.value = true;
}

async function submitCorrection() {
  if (!correction.global_track_id) {
    error.value = "No global_track_id on the selected detection.";
    return;
  }
  saving.value = true;
  try {
    await cts.applyCorrection({
      global_track_id: correction.global_track_id,
      new_identity_id: correction.new_identity_id || null,
      reason: correction.reason || "manual",
    });
    correctionOpen.value = false;
  } catch (err) {
    error.value = String(err.message || err);
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped>
.live-grid {
  display: grid;
  gap: 16px;
}
.grid-1 {
  grid-template-columns: 1fr;
}
.grid-2 {
  grid-template-columns: repeat(2, 1fr);
}
.grid-3 {
  grid-template-columns: repeat(3, 1fr);
}
.grid-4 {
  grid-template-columns: repeat(4, 1fr);
}
.live-tile {
  background: var(--cc-surface-2);
}
.live-tile-frame {
  position: relative;
  background: var(--cc-bg);
  aspect-ratio: 16 / 9;
  overflow: hidden;
}
.live-tile-img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.live-tile-overlay {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
.live-tile-no-frame {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(var(--v-theme-on-surface), 0.03);
}
.live-tile-stale .live-tile-img {
  opacity: 0.4;
  filter: grayscale(60%);
}
.live-tile-stale-badge {
  position: absolute;
  bottom: 6px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(0, 0, 0, 0.65);
  color: var(--cc-warning, #fb8c00);
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
  white-space: nowrap;
  display: flex;
  align-items: center;
  pointer-events: none;
}
</style>
