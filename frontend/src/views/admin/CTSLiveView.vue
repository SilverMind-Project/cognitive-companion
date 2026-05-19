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
          label="Bboxes"
          density="compact"
          hide-details
        />
        <v-switch
          v-model="showIdLabels"
          color="primary"
          label="Labels"
          density="compact"
          hide-details
        />
        <v-switch
          v-model="showTrail"
          color="primary"
          label="Trail"
          density="compact"
          hide-details
        />
        <v-switch
          v-model="showPose"
          color="primary"
          label="Pose"
          density="compact"
          hide-details
        />
        <v-switch
          v-model="showEvidence"
          color="primary"
          label="Evidence"
          density="compact"
          hide-details
        />
        <v-switch
          v-model="showPosture"
          color="primary"
          label="Posture"
          density="compact"
          hide-details
        />
        <BlurToggle />
        <v-spacer />
        <v-btn
          variant="tonal"
          prepend-icon="mdi-account-edit"
          :to="{ name: 'cts-identity-corrections' }"
        >
          Manage corrections
        </v-btn>
      </v-card-text>

      <!-- Cross-camera presence panel: only shown when same identity seen on 2+ cameras -->
      <div v-if="multiCameraIdentities.length > 0" class="px-4 pb-3 pt-1">
        <v-divider class="mb-2" />
        <div class="d-flex align-center ga-2 mb-2">
          <v-icon size="18" color="primary">mdi-camera-flip-outline</v-icon>
          <span class="text-body-2 font-weight-medium">Cross-camera activity</span>
          <v-chip size="x-small" color="primary" variant="flat" density="compact">
            {{ multiCameraIdentities.length }} {{ multiCameraIdentities.length > 1 ? 'identities' : 'identity' }}
          </v-chip>
        </div>
        <div class="d-flex flex-wrap ga-2">
          <v-chip
            v-for="entry in multiCameraIdentities"
            :key="entry.identity_id"
            size="small"
            :color="entry.color"
            variant="outlined"
          >
            <template #prepend>
              <v-icon size="14" :color="entry.color">mdi-camera</v-icon>
            </template>
            <span class="font-weight-medium">{{ entry.identity_id }}</span>
            <v-chip
              size="x-small"
              variant="flat"
              :color="entry.color"
              class="ml-1"
              density="compact"
            >
              {{ entry.cameraCount }} cam{{ entry.cameraCount > 1 ? 's' : '' }}
            </v-chip>
          </v-chip>
        </div>
      </div>

      <v-divider />

      <div :class="gridClass" class="pa-4 ga-4 live-grid">
        <v-card
          v-for="slot in slots"
          :key="slot"
          class="live-tile"
          variant="outlined"
          :style="tileLinkStyle(cameraIdForSlot(slot))"
        >
          <v-card-text class="d-flex align-center ga-2 pa-2">
            <v-select
              :model-value="cameraIdForSlot(slot)"
              :items="availableCameras"
              item-title="name"
              item-value="id"
              density="compact"
              variant="outlined"
              hide-details
              clearable
              class="camera-picker"
              @update:model-value="(val) => onSlotCameraChange(slot, val)"
            />
            <span class="text-caption text-medium-emphasis text-no-wrap">
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
              :src="displaySrc(cameraForSlot(slot).frame_url)"
              class="live-tile-img"
              alt=""
              @error="onFrameError($event, cameraForSlot(slot))"
            />
            <img
              v-else-if="snapshotUrls[cameraIdForSlot(slot)]"
              :src="displaySrc(snapshotUrls[cameraIdForSlot(slot)])"
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
              v-if="cameraForSlot(slot)"
              :viewBox="`0 0 ${cameraForSlot(slot).frame_width || 1920} ${cameraForSlot(slot).frame_height || 1080}`"
              class="live-tile-overlay"
              preserveAspectRatio="xMidYMid slice"
            >
              <g
                v-for="(det, idx) in cameraForSlot(slot).detections"
                :key="idx"
              >
                <!-- Trail polyline -->
                <polyline
                  v-if="showTrail && det.trail && det.trail.length > 1"
                  :points="trailPoints(det, cameraForSlot(slot))"
                  fill="none"
                  :stroke="det.identity_id ? 'var(--cc-success)' : 'var(--cc-warning)'"
                  :stroke-width="overlayStroke(cameraForSlot(slot), 1)"
                  opacity="0.5"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />

                <!-- Bounding box -->
                <rect
                  v-if="showBboxes"
                  :x="det.bbox.x_min || 0"
                  :y="det.bbox.y_min || 0"
                  :width="(det.bbox.x_max || 0) - (det.bbox.x_min || 0)"
                  :height="(det.bbox.y_max || 0) - (det.bbox.y_min || 0)"
                  fill="none"
                  :stroke="bboxColor(det)"
                  :stroke-width="overlayStroke(cameraForSlot(slot), isMultiCamera(det) ? 2 : 1)"
                  :opacity="isMultiCamera(det) ? undefined : 1"
                  style="cursor: pointer"
                  @click="openCorrection(det, cameraForSlot(slot))"
                >
                  <animate
                    v-if="isMultiCamera(det)"
                    attributeName="opacity"
                    values="0.75;1;0.75"
                    dur="2s"
                    repeatCount="indefinite"
                  />
                </rect>
                <!-- Cross-camera badge: shown when same identity appears on multiple cameras -->
                <g v-if="showBboxes && isMultiCamera(det)">
                  <title>{{ multiCameraTooltip(det) }}</title>
                  <circle
                    :cx="(det.bbox.x_max || 0) - badgeRadius(cameraForSlot(slot)) * 1"
                    :cy="(det.bbox.y_min || 0) + badgeRadius(cameraForSlot(slot)) * 1"
                    :r="badgeRadius(cameraForSlot(slot))"
                    :fill="bboxColor(det)"
                    opacity="0.9"
                  />
                  <text
                    :x="(det.bbox.x_max || 0) - badgeRadius(cameraForSlot(slot)) * 1"
                    :y="(det.bbox.y_min || 0) + badgeRadius(cameraForSlot(slot)) * 1"
                    text-anchor="middle"
                    :font-size="smallFontSize(cameraForSlot(slot))"
                    fill="white"
                    font-weight="bold"
                    dominant-baseline="central"
                  >{{ multiCameraCount(det) }}</text>
                </g>

                <!-- Identity label -->
                <text
                  v-if="showIdLabels"
                  :x="(det.bbox.x_min || 0) + labelOffsetX(cameraForSlot(slot))"
                  :y="(det.bbox.y_min || 0) + labelOffsetY(cameraForSlot(slot))"
                  fill="var(--cc-text-1)"
                  :font-size="labelFontSize(cameraForSlot(slot))"
                  font-weight="bold"
                  :style="{ paintOrder: 'stroke', stroke: 'rgba(0,0,0,0.6)', strokeWidth: overlayStroke(cameraForSlot(slot), 0.5) }"
                >
                  {{ det.identity_id || "unknown" }}
                </text>
                <!-- "Also on" camera label for multi-camera detections -->
                <text
                  v-if="showIdLabels && isMultiCamera(det)"
                  :x="(det.bbox.x_min || 0) + labelOffsetX(cameraForSlot(slot))"
                  :y="(det.bbox.y_min || 0) + labelOffsetY(cameraForSlot(slot)) + labelFontSize(cameraForSlot(slot)) + 4"
                  fill="var(--cc-text-2)"
                  :font-size="smallFontSize(cameraForSlot(slot))"
                  font-weight="500"
                  :style="{ paintOrder: 'stroke', stroke: 'rgba(0,0,0,0.6)', strokeWidth: overlayStroke(cameraForSlot(slot), 0.5) }"
                >
                  {{ otherCameraNames(det, cameraForSlot(slot)) }}
                </text>

                <!-- Posture label -->
                <text
                  v-if="showPosture && det.posture && det.posture !== 'unknown'"
                  :x="(det.bbox.x_min || 0) + labelOffsetX(cameraForSlot(slot))"
                  :y="postureLabelY(det, cameraForSlot(slot))"
                  :fill="postureColor(det.posture)"
                  :font-size="smallFontSize(cameraForSlot(slot))"
                  font-weight="600"
                  :style="{
                    paintOrder: 'stroke',
                    stroke: 'rgba(0,0,0,0.7)',
                    strokeWidth: overlayStroke(cameraForSlot(slot), 0.5),
                  }"
                >{{ det.posture }}</text>

                <!-- Pose stick figure -->
                <g v-if="showPose && det.pose_keypoints && det.pose_keypoints.length === 17">
                  <template
                    v-for="([a, b], li) in LIMB_PAIRS"
                    :key="li"
                  >
                    <line
                      v-if="det.pose_keypoints[a]?.score > 0.2 && det.pose_keypoints[b]?.score > 0.2"
                      :x1="poseX(det, a)"
                      :y1="poseY(det, a)"
                      :x2="poseX(det, b)"
                      :y2="poseY(det, b)"
                      stroke="rgba(255,200,50,0.85)"
                      :stroke-width="overlayStroke(cameraForSlot(slot), .5)"
                      stroke-linecap="round"
                    />
                  </template>
                  <circle
                    v-for="(kp, ki) in det.pose_keypoints"
                    :key="`kp${ki}`"
                    :cx="poseX(det, ki)"
                    :cy="poseY(det, ki)"
                    :r="overlayStroke(cameraForSlot(slot), 1.5)"
                    :fill="kp.score > 0.4 ? 'rgba(255,200,50,1)' : 'transparent'"
                  />
                </g>

                <!-- Evidence chip (top-right of bbox) -->
                <g v-if="showEvidence && det.evidence">
                  <!-- Background pill -->
                  <rect
                    :x="(det.bbox.x_max || 0) - evidencePillWidth(cameraForSlot(slot)) - 4"
                    :y="(det.bbox.y_min || 0) + 2"
                    :width="evidencePillWidth(cameraForSlot(slot)) + 4"
                    :height="evidencePillHeight(cameraForSlot(slot))"
                    :rx="Math.round(evidencePillHeight(cameraForSlot(slot)) * 0.27)"
                    fill="rgba(0,0,0,0.65)"
                  />
                  <!-- Top-1 bar -->
                  <rect
                    :x="(det.bbox.x_max || 0) - evidencePillWidth(cameraForSlot(slot)) - 2"
                    :y="(det.bbox.y_min || 0) + evidenceBarY(cameraForSlot(slot), 0)"
                    :width="Math.round((evidencePillWidth(cameraForSlot(slot)) - 4) * (det.evidence.top_prob || 0))"
                    :height="evidenceBarHeight(cameraForSlot(slot))"
                    :rx="Math.round(evidenceBarHeight(cameraForSlot(slot)) * 0.5)"
                    :fill="det.evidence.face_anchor_used ? '#a78bfa' : '#34d399'"
                  />
                  <!-- Top-2 bar -->
                  <rect
                    :x="(det.bbox.x_max || 0) - evidencePillWidth(cameraForSlot(slot)) - 2"
                    :y="(det.bbox.y_min || 0) + evidenceBarY(cameraForSlot(slot), 1)"
                    :width="Math.round((evidencePillWidth(cameraForSlot(slot)) - 4) * (det.evidence.top2_prob || 0))"
                    :height="Math.round(evidenceBarHeight(cameraForSlot(slot)) * 0.7)"
                    :rx="Math.round(evidenceBarHeight(cameraForSlot(slot)) * 0.35)"
                    fill="#94a3b8"
                  />
                </g>

                <!-- Face badge (crown) when face anchor was used -->
                <text
                  v-if="showEvidence && det.evidence?.face_anchor_used"
                  :x="(det.bbox.x_min || 0) + labelOffsetX(cameraForSlot(slot))"
                  :y="(det.bbox.y_min || 0) + crownOffsetY(cameraForSlot(slot))"
                  :font-size="labelFontSize(cameraForSlot(slot))"
                  style="user-select: none"
                >👑</text>
              </g>
            </svg>
            <div
              v-if="isCameraStale(cameraForSlot(slot))"
              class="live-tile-stale-badge"
            >
              <v-icon size="12" class="mr-1">mdi-clock-alert-outline</v-icon>
              Last seen {{ staleLabel(cameraForSlot(slot)) }}
            </div>
            <!-- Cross-camera link badges: one per linked identity on this tile -->
            <div
              v-if="tileLinkEntries(cameraIdForSlot(slot)).length"
              class="live-tile-link-stack"
            >
              <div
                v-for="entry in tileLinkEntries(cameraIdForSlot(slot))"
                :key="entry.identity_id"
                class="live-tile-link-badge"
                :style="{ borderColor: entry.color, color: entry.color }"
                :title="`GT linked: ${entry.display_name} also on ${entry.otherCameras.join(', ')}`"
              >
                <v-icon size="11" :color="entry.color">mdi-link-variant</v-icon>
                <span class="live-tile-link-name">{{ entry.display_name }}</span>
                <span class="live-tile-link-cams" :style="{ background: entry.color }">+{{ entry.otherCameras.length }}</span>
              </div>
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
import { ref, computed, reactive, onMounted, onUnmounted, watch } from "vue";
import { cts } from "@/services/cts";
import { useCtsWebSocket } from "@/composables/useCtsWebSocket.js";
import { useBlurMode, useDisplaySrc } from "@/composables/useBlurMode.js";
import { identityColor } from "@/composables/useIdentityColor.js";
import DialogHeader from "@/components/common/DialogHeader.vue";
import DialogFooter from "@/components/common/DialogFooter.vue";
import BlurToggle from "@/components/cts/BlurToggle.vue";

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
const showTrail = ref(false);
const showPose = ref(false);
const showEvidence = ref(false);
const showPosture = ref(true);

const { blurMode } = useBlurMode();
const { displaySrc } = useDisplaySrc(blurMode);

// COCO 17-keypoint limb pairs (0-indexed).
const LIMB_PAIRS = [
  [5, 6], [5, 7], [7, 9], [6, 8], [8, 10],
  [5, 11], [6, 12], [11, 12],
  [11, 13], [13, 15], [12, 14], [14, 16],
  [0, 5], [0, 6],
];

const cameras = ref({});
// camera_id → blob URL for go2rtc snapshot (fallback when WS is idle)
const snapshotUrls = ref({});
// Full camera objects loaded from the API on mount
const cameraList = ref([]);
// Camera IDs loaded from the API (ensures slots populate before first WS event)
const knownCameraIds = ref([]);
const now = ref(Date.now());
let _freshnessTimer = null;
let _snapshotTimer = null;

const SELECTED_STORAGE_KEY = "cts_live_selected_cameras";

function loadSelectedFromStorage() {
  try {
    return JSON.parse(localStorage.getItem(SELECTED_STORAGE_KEY) || "{}");
  } catch {
    return {};
  }
}

const selectedCameras = ref(loadSelectedFromStorage());

function persistSelected() {
  localStorage.setItem(SELECTED_STORAGE_KEY, JSON.stringify(selectedCameras.value));
}

watch(selectedCameras, persistSelected, { deep: true });

async function loadKnownCameras() {
  try {
    const data = await cts.getCameras();
    const list = Array.isArray(data) ? data : (data.cameras || []);
    cameraList.value = list;
    knownCameraIds.value = list.map((c) => c.id);
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

// Cross-camera person detection: identity_id → Set of camera_ids where seen.
const identityCameraMap = computed(() => {
  const map = new Map(); // identity_id → Set<camera_id>
  for (const [cameraId, cam] of Object.entries(cameras.value)) {
    for (const det of cam.detections || []) {
      const id = det.identity_id;
      if (!id) continue;
      if (!map.has(id)) map.set(id, new Set());
      map.get(id).add(cameraId);
    }
  }
  return map;
});

// List of identities seen on 2+ cameras, sorted by camera count desc.
const multiCameraIdentities = computed(() => {
  const result = [];
  for (const [id, cams] of identityCameraMap.value.entries()) {
    if (cams.size >= 2) {
      result.push({ identity_id: id, cameraCount: cams.size, color: identityColor(id) });
    }
  }
  return result.sort((a, b) => b.cameraCount - a.cameraCount);
});

function isMultiCamera(det) {
  if (!det.identity_id) return false;
  const cams = identityCameraMap.value.get(det.identity_id);
  return cams ? cams.size >= 2 : false;
}

function multiCameraCount(det) {
  if (!det.identity_id) return 0;
  return identityCameraMap.value.get(det.identity_id)?.size ?? 0;
}

function otherCameraNames(det, currentCam) {
  if (!det.identity_id) return "";
  const cams = identityCameraMap.value.get(det.identity_id);
  if (!cams || cams.size < 2) return "";
  const others = [...cams].filter((c) => c !== currentCam?.camera_id);
  if (others.length === 0) return "";
  return others.length > 2
    ? `+${others.length} other cameras`
    : `also on ${others.join(", ")}`;
}

function multiCameraTooltip(det) {
  if (!det.identity_id) return "";
  const cams = identityCameraMap.value.get(det.identity_id);
  if (!cams) return "";
  return `Seen on: ${[...cams].join(", ")}`;
}

function bboxColor(det) {
  if (!det.identity_id) return "var(--cc-warning)";
  return isMultiCamera(det) ? identityColor(det.identity_id) : "var(--cc-success)";
}

// Returns the dominant multi-camera identity color for a camera tile, or null.
// "Dominant" = most cameras, tie-broken by identity_confidence.
function tileDominantLinkColor(cameraId) {
  if (!cameraId) return null;
  const cam = cameras.value[cameraId];
  if (!cam?.detections?.length) return null;
  let best = null;
  let bestScore = -1;
  for (const det of cam.detections) {
    if (!det.identity_id) continue;
    const cams = identityCameraMap.value.get(det.identity_id);
    if (!cams || cams.size < 2) continue;
    const score = cams.size + (det.identity_confidence || 0);
    if (score > bestScore) {
      bestScore = score;
      best = det.identity_id;
    }
  }
  return best ? identityColor(best) : null;
}

// Box-shadow glow style applied to the tile card when it has a linked GT.
function tileLinkStyle(cameraId) {
  const color = tileDominantLinkColor(cameraId);
  if (!color) return {};
  return {
    boxShadow: `0 0 0 2px ${color}cc, 0 0 14px ${color}55`,
    transition: "box-shadow 0.4s ease",
  };
}

// Returns one entry per multi-camera identity visible on this camera tile,
// used to render the per-tile link badges.
function tileLinkEntries(cameraId) {
  if (!cameraId) return [];
  const cam = cameras.value[cameraId];
  if (!cam?.detections?.length) return [];
  const seen = new Set();
  const result = [];
  for (const det of cam.detections) {
    if (!det.identity_id || seen.has(det.identity_id)) continue;
    const cams = identityCameraMap.value.get(det.identity_id);
    if (!cams || cams.size < 2) continue;
    seen.add(det.identity_id);
    const others = [...cams].filter((c) => c !== cameraId);
    result.push({
      identity_id: det.identity_id,
      display_name: det.display_name || det.identity_id,
      color: identityColor(det.identity_id),
      otherCameras: others,
    });
  }
  return result;
}

// ---------------------------------------------------------------------------
// Identity caches — three layers, consulted in order:
//
//  1. global_track_id cache  (5 min TTL) — most stable; one GT per person per session.
//  2. tracklet_id cache      (30 s TTL)  — covers same-tracklet identity drops.
//  3. position cache         (5 s TTL)   — last resort when both IDs are empty
//     (the ~2-frame window while BoT-SORT confirms a new local track before
//     it gets a tracklet_id or is merged back into the GT).  Picks the cached
//     entry whose bbox overlaps the current detection most.
// ---------------------------------------------------------------------------

const GLOBAL_TRACK_IDENTITY_TTL_MS = 300_000;
const TRACKLET_IDENTITY_TTL_MS     =  30_000;
const POSITION_IDENTITY_TTL_MS     =   5_000;
const POSITION_IOU_MIN             =    0.25;  // require ≥25% bbox overlap

const globalTrackIdentityCache = {};  // global_track_id → {identity_id, display_name, identity_confidence, lastSeenMs}
const trackletIdentityCache    = {};  // tracklet_id      → {identity_id, display_name, identity_confidence, lastSeenMs}
const positionIdentityCache    = {};  // camera_id        → [{bbox, identity_id, display_name, identity_confidence, lastSeenMs}]

function _cacheEntry(d, nowMs) {
  return { identity_id: d.identity_id, display_name: d.display_name, identity_confidence: d.identity_confidence, lastSeenMs: nowMs };
}

function _bboxIoU(a, b) {
  const ix1 = Math.max(a.x_min, b.x_min), iy1 = Math.max(a.y_min, b.y_min);
  const ix2 = Math.min(a.x_max, b.x_max), iy2 = Math.min(a.y_max, b.y_max);
  if (ix2 <= ix1 || iy2 <= iy1) return 0;
  const inter = (ix2 - ix1) * (iy2 - iy1);
  const aA = (a.x_max - a.x_min) * (a.y_max - a.y_min);
  const bA = (b.x_max - b.x_min) * (b.y_max - b.y_min);
  return inter / (aA + bA - inter);
}

function _applyIdentity(d, entry, action, cameraId) {
  console.debug("[cts_live] identity_cache", { action, camera_id: cameraId, global_track_id: d.global_track_id || "", tracklet_id: d.tracklet_id || "", identity_id: entry.identity_id });
  return { ...d, identity_id: entry.identity_id, display_name: entry.display_name, identity_confidence: entry.identity_confidence };
}

function mergeIdentityCache(detections, cameraId = "unknown") {
  if (!detections) return detections;
  const nowMs = Date.now();

  // --- Pass 1: populate caches from detections that already have an identity ---
  const freshPositions = [];
  for (const d of detections) {
    if (!d.identity_id) continue;
    const entry = _cacheEntry(d, nowMs);
    if (d.global_track_id) globalTrackIdentityCache[d.global_track_id] = entry;
    if (d.tracklet_id)     trackletIdentityCache[d.tracklet_id]         = entry;
    if (d.bbox)            freshPositions.push({ bbox: d.bbox, ...entry });
  }
  if (freshPositions.length) positionIdentityCache[cameraId] = freshPositions;

  // --- Pass 2: fill identity for detections that lack one ---
  return detections.map((d) => {
    if (d.identity_id) return d;

    // 1. Global-track cache (most stable — session-lifetime key).
    if (d.global_track_id) {
      const c = globalTrackIdentityCache[d.global_track_id];
      if (c && nowMs - c.lastSeenMs <= GLOBAL_TRACK_IDENTITY_TTL_MS)
        return _applyIdentity(d, c, "gt_cache_hit", cameraId);
    }

    // 2. Tracklet cache (covers same-tracklet brief identity drops).
    if (d.tracklet_id) {
      const c = trackletIdentityCache[d.tracklet_id];
      if (c && nowMs - c.lastSeenMs <= TRACKLET_IDENTITY_TTL_MS)
        return _applyIdentity(d, c, "tracklet_cache_hit", cameraId);
    }

    // 3. Position cache — fires when both IDs are empty (new unconfirmed track).
    //    Pick the cached bbox with the highest IoU to this detection's bbox.
    if (d.bbox) {
      const recent = (positionIdentityCache[cameraId] || [])
        .filter(e => nowMs - e.lastSeenMs <= POSITION_IDENTITY_TTL_MS);
      let bestIoU = POSITION_IOU_MIN, bestEntry = null;
      for (const e of recent) {
        const iou = _bboxIoU(d.bbox, e.bbox);
        if (iou > bestIoU) { bestIoU = iou; bestEntry = e; }
      }
      if (bestEntry)
        return _applyIdentity(d, bestEntry, "position_cache_hit", cameraId);
    }

    console.debug("[cts_live] identity_cache", { action: "cache_miss", camera_id: cameraId, global_track_id: d.global_track_id || "", tracklet_id: d.tracklet_id || "" });
    return d;
  });
}

setInterval(() => {
  const gtCutoff = Date.now() - GLOBAL_TRACK_IDENTITY_TTL_MS;
  const tCutoff  = Date.now() - TRACKLET_IDENTITY_TTL_MS;
  for (const [k, v] of Object.entries(globalTrackIdentityCache)) { if (v.lastSeenMs < gtCutoff) delete globalTrackIdentityCache[k]; }
  for (const [k, v] of Object.entries(trackletIdentityCache))    { if (v.lastSeenMs < tCutoff)  delete trackletIdentityCache[k]; }
  // Position cache entries are rebuilt fresh each frame — just clear stale cameras.
  for (const [k, v] of Object.entries(positionIdentityCache)) {
    if (!v.length || Date.now() - Math.max(...v.map(e => e.lastSeenMs)) > POSITION_IDENTITY_TTL_MS * 2)
      delete positionIdentityCache[k];
  }
}, TRACKLET_IDENTITY_TTL_MS);

// Per-tracklet keypoint EMA smoothing to reduce frame-to-frame jitter.
// Each tracklet's 17 keypoints (x, y only) are blended with the previous
// frame's values at alpha=0.35 so the skeleton overlay moves smoothly.
const KEYPOINT_SMOOTH_ALPHA = 0.65;
const keypointSmoothState = {};  // { tracklet_id: [{x, y} x 17] }

function smoothKeypoints(detections) {
  if (!detections) return detections;
  const now = Date.now();
  for (const d of detections) {
    const tid = d.tracklet_id;
    if (!tid || !d.pose_keypoints || d.pose_keypoints.length !== 17) continue;
    const prev = keypointSmoothState[tid];
    if (!prev || (now - prev._ts) > 2000) {
      // First sighting or >2s gap: initialise with current values.
      keypointSmoothState[tid] = {
        _ts: now,
        kps: d.pose_keypoints.map((kp) => ({ x: kp.x, y: kp.y })),
      };
      continue;
    }
    for (let i = 0; i < 17; i++) {
      const pk = prev.kps[i];
      const ck = d.pose_keypoints[i];
      if (!ck || !pk) continue;
      pk.x = pk.x + KEYPOINT_SMOOTH_ALPHA * (ck.x - pk.x);
      pk.y = pk.y + KEYPOINT_SMOOTH_ALPHA * (ck.y - pk.y);
      // Write smoothed values back to the detection for rendering.
      ck.x = pk.x;
      ck.y = pk.y;
    }
    prev._ts = now;
  }
  return detections;
}

// Clean up stale keypoint state every 30 s.
setInterval(() => {
  const cutoff = Date.now() - 30_000;
  for (const [tid, state] of Object.entries(keypointSmoothState)) {
    if (state._ts < cutoff) delete keypointSmoothState[tid];
  }
}, 30_000);

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
    // Apply temporal smoothing to pose keypoints before rendering.
    msg.detections = smoothKeypoints(msg.detections);
    // Fill in last-known identity for detections that lack one this frame.
    msg.detections = mergeIdentityCache(msg.detections, msg.camera_id);
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

const availableCameras = computed(() =>
  cameraList.value.map((c) => ({ id: c.id, name: c.name || c.id }))
);

function cameraIdForSlot(slot) {
  const forLayout = selectedCameras.value[layout.value] || {};
  const selectedId = forLayout[slot];
  if (selectedId && availableCameras.value.some((c) => c.id === selectedId)) {
    return selectedId;
  }
  return allCameraIds.value[slot] ?? null;
}

function onSlotCameraChange(slot, cameraId) {
  const current = { ...(selectedCameras.value[layout.value] || {}) };
  if (cameraId) {
    current[slot] = cameraId;
  } else {
    delete current[slot];
  }
  selectedCameras.value = {
    ...selectedCameras.value,
    [layout.value]: current,
  };
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

function poseX(det, keypointIdx) {
  const kp = det.pose_keypoints[keypointIdx];
  if (!kp) return 0;
  const bw = (det.bbox.x_max || 0) - (det.bbox.x_min || 0);
  return (det.bbox.x_min || 0) + kp.x * bw;
}

function poseY(det, keypointIdx) {
  const kp = det.pose_keypoints[keypointIdx];
  if (!kp) return 0;
  const bh = (det.bbox.y_max || 0) - (det.bbox.y_min || 0);
  return (det.bbox.y_min || 0) + kp.y * bh;
}

function trailPoints(det, cam) {
  if (!det.trail || !cam) return "";
  const fw = cam.frame_width || 1920;
  const fh = cam.frame_height || 1080;
  return det.trail.map((t) => `${t.x * fw},${t.y * fh}`).join(" ");
}

// Scale visual SVG elements relative to the camera's native resolution so
// fonts, strokes, and badges remain readable regardless of tile display size.
// For a 1920 px viewBox shown on a ~400 px tile (scale ≈ 0.21):
//   labelFont  = 1920 × 0.04  = 77 SVG units → 77 × 0.21 ≈ 16 CSS px
//   smallFont  = 1920 × 0.025 = 48 SVG units → 48 × 0.21 ≈ 10 CSS px
//   baseStroke = 1920 × 0.004 =  8 SVG units →  8 × 0.21 ≈  2 CSS px
function labelFontSize(cam) {
  return Math.round((cam?.frame_width || 1920) * 0.015);
}
function smallFontSize(cam) {
  return Math.round((cam?.frame_width || 1920) * 0.01);
}
function overlayStroke(cam, multiplier = 1) {
  return Math.max(1, Math.round((cam?.frame_width || 1920) * 0.005 * multiplier));
}
function badgeRadius(cam) {
  return Math.round((cam?.frame_width || 1920) * 0.01);
}
function evidenceBarY(cam, row) {
  // row 0 = top bar, row 1 = bottom bar; returns y offset from bbox top
  const fs = smallFontSize(cam);
  const gap = Math.round(fs * 0.5);
  const barH = Math.round(fs * 0.8);
  return 2 + row * (barH + gap);
}
function evidenceBarHeight(cam) {
  return Math.round(smallFontSize(cam) * 0.8);
}
function evidencePillWidth(cam) {
  return Math.round((cam?.frame_width || 1920) * 0.06);
}
function evidencePillHeight(cam) {
  const fs = smallFontSize(cam);
  return Math.round(fs * 1.8);
}
function labelOffsetY(cam) {
  return Math.round(labelFontSize(cam) * 0.8);
}
function labelOffsetX(cam) {
  return Math.round(labelFontSize(cam) * 0.22);
}
function crownOffsetY(cam) {
  return Math.round(labelFontSize(cam) * 1.0);
}

function postureColor(posture) {
  const colors = {
    standing: "#4ade80",
    sitting: "#fbbf24",
    walking: "#60a5fa",
    lying: "#c084fc",
  };
  return colors[posture] || "var(--cc-text-2)";
}

function postureLabelY(det, cam) {
  const fs = labelFontSize(cam);
  let yOff = labelOffsetY(cam) + fs + 4;
  if (showIdLabels.value && isMultiCamera(det)) {
    yOff += smallFontSize(cam) + 4;
  }
  return (det.bbox.y_min || 0) + yOff;
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
.camera-picker {
  flex: 1 1 auto;
  min-width: 0;
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
  font-size: 12px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
  white-space: nowrap;
  display: flex;
  align-items: center;
  pointer-events: none;
}
.live-tile-link-stack {
  position: absolute;
  top: 6px;
  left: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  pointer-events: none;
}
.live-tile-link-badge {
  background: rgba(0, 0, 0, 0.72);
  border: 1px solid;
  border-radius: 10px;
  padding: 2px 7px 2px 5px;
  font-size: 11px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 3px;
  white-space: nowrap;
}
.live-tile-link-name {
  max-width: 80px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.live-tile-link-cams {
  color: rgba(0, 0, 0, 0.85);
  border-radius: 8px;
  padding: 0 4px;
  font-size: 10px;
  font-weight: 700;
  margin-left: 2px;
}

</style>
