<template>
  <v-card class="live-tile" variant="outlined" :style="tileStyle">
    <v-card-text class="d-flex align-center ga-2 pa-2">
      <v-select
        :model-value="cameraId"
        :items="availableCameras"
        item-title="name"
        item-value="id"
        density="compact"
        variant="outlined"
        hide-details
        clearable
        class="camera-picker"
        @update:model-value="(val) => $emit('camera-change', val)"
      />
      <span class="text-caption text-medium-emphasis text-no-wrap">
        {{ camera?.detections?.length || 0 }} detections
      </span>
    </v-card-text>
    <div
      class="live-tile-frame"
      :class="[`tile-density-${layout}`, { 'live-tile-stale': isStale }]"
      :aria-label="`Live camera ${cameraId || slotIndex}`"
    >
      <img
        v-if="camera?.frame_url"
        :src="displaySrc(camera.frame_url)"
        class="live-tile-img"
        alt=""
        @error="$emit('frame-error', $event, camera)"
      />
      <img v-else-if="snapshotUrl" :src="displaySrc(snapshotUrl)" class="live-tile-img" alt="" />
      <div v-else class="live-tile-no-frame">
        <v-icon size="24" color="medium-emphasis">mdi-video-off-outline</v-icon>
      </div>
      <svg
        v-if="camera"
        :viewBox="`0 0 ${camera.frame_width || 1920} ${camera.frame_height || 1080}`"
        class="live-tile-overlay"
        preserveAspectRatio="xMidYMid slice"
      >
        <g v-for="(det, idx) in camera.detections" :key="idx">
          <!-- Trail polyline -->
          <polyline
            v-if="showTrail && det.trail && det.trail.length > 1"
            :points="trailPoints(det, camera)"
            fill="none"
            :stroke="det.identity_id ? 'var(--cc-success)' : 'var(--cc-warning)'"
            :stroke-width="overlayStroke(camera, 1)"
            opacity="0.5"
            stroke-linecap="round"
            stroke-linejoin="round"
          />

          <!-- Bounding box -->
          <MaraudersInkBox
            v-if="showBboxes && maraudersEnabled"
            :x="det.bbox.x_min || 0"
            :y="det.bbox.y_min || 0"
            :w="(det.bbox.x_max || 0) - (det.bbox.x_min || 0)"
            :h="(det.bbox.y_max || 0) - (det.bbox.y_min || 0)"
            :seed-key="String(det.track_id || det.detection_id || det.bbox.x_min)"
            :color="bboxColor(det)"
            style="cursor: pointer"
            @click="$emit('open-correction', det, camera)"
          />
          <rect
            v-else-if="showBboxes"
            :x="det.bbox.x_min || 0"
            :y="det.bbox.y_min || 0"
            :width="(det.bbox.x_max || 0) - (det.bbox.x_min || 0)"
            :height="(det.bbox.y_max || 0) - (det.bbox.y_min || 0)"
            fill="none"
            :stroke="bboxColor(det)"
            :stroke-width="overlayStroke(camera, isMultiCamera(det) ? 1.25 : 1)"
            :opacity="isMultiCamera(det) ? undefined : 1"
            style="cursor: pointer"
            @click="$emit('open-correction', det, camera)"
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
              :cx="(det.bbox.x_max || 0) - badgeRadius(camera) * 1"
              :cy="(det.bbox.y_min || 0) + badgeRadius(camera) * 1"
              :r="badgeRadius(camera)"
              :fill="bboxColor(det)"
              opacity="0.9"
            />
            <text
              :x="(det.bbox.x_max || 0) - badgeRadius(camera) * 1"
              :y="(det.bbox.y_min || 0) + badgeRadius(camera) * 1"
              text-anchor="middle"
              :font-size="smallFontSize(camera)"
              fill="white"
              font-weight="bold"
              dominant-baseline="central"
            >
              {{ multiCameraCount(det) }}
            </text>
          </g>

          <!-- Identity label: white text + dark halo (camera-feed standard) -->
          <text
            v-if="showIdLabels"
            :x="(det.bbox.x_min || 0) + labelOffsetX(camera)"
            :y="(det.bbox.y_min || 0) + labelOffsetY(camera)"
            fill="white"
            :font-size="labelFontSize(camera)"
            font-weight="500"
            :style="{
              paintOrder: 'stroke',
              stroke: HALO.color,
              strokeWidth: labelHaloStroke(camera),
              strokeLinejoin: 'round',
            }"
          >
            {{ det.identity_id || "unknown" }}
          </text>
          <!-- Posture label: semantic color + dark halo -->
          <text
            v-if="showPosture && det.posture && det.posture !== 'unknown'"
            :x="(det.bbox.x_min || 0) + labelOffsetX(camera)"
            :y="postureLabelY(det, camera)"
            :fill="postureColor(det.posture)"
            :font-size="smallFontSize(camera)"
            font-weight="500"
            :style="{
              paintOrder: 'stroke',
              stroke: HALO.color,
              strokeWidth: labelHaloStroke(camera),
              strokeLinejoin: 'round',
            }"
          >
            {{ det.posture }}
          </text>

          <!-- Pose stick figure -->
          <g v-if="showPose && det.pose_keypoints && det.pose_keypoints.length === 17">
            <template v-for="([a, b], li) in LIMB_PAIRS" :key="li">
              <line
                v-if="det.pose_keypoints[a]?.score > 0.2 && det.pose_keypoints[b]?.score > 0.2"
                :x1="poseX(det, a)"
                :y1="poseY(det, a)"
                :x2="poseX(det, b)"
                :y2="poseY(det, b)"
                stroke="rgba(255,200,50,0.85)"
                :stroke-width="overlayStroke(camera, 0.5)"
                stroke-linecap="round"
              />
            </template>
            <circle
              v-for="(kp, ki) in det.pose_keypoints"
              :key="`kp${ki}`"
              :cx="poseX(det, ki)"
              :cy="poseY(det, ki)"
              :r="overlayStroke(camera, 1.5)"
              :fill="kp.score > 0.4 ? 'rgba(255,200,50,1)' : 'transparent'"
            />
          </g>

          <!-- Evidence chip (top-right of bbox) -->
          <g v-if="showEvidence && det.evidence">
            <title>{{ evidenceTooltip(det) }}</title>
            <!-- Background pill -->
            <rect
              :x="evidencePillX(det, camera)"
              :y="evidencePillY(det, camera)"
              :width="evidencePillWidth(camera)"
              :height="evidencePillHeight(camera)"
              :rx="Math.round(evidencePillHeight(camera) * 0.18)"
              fill="rgba(0,0,0,0.72)"
            />
            <text
              :x="evidencePillX(det, camera) + evidencePad(camera)"
              :y="evidencePillY(det, camera) + evidenceTextY(camera)"
              fill="white"
              :font-size="evidenceFontSize(camera)"
              font-weight="600"
              dominant-baseline="central"
              style="pointer-events: none"
            >
              {{ evidenceLabel(det) }}
            </text>
            <!-- Top-1 bar -->
            <rect
              :x="evidencePillX(det, camera) + evidencePad(camera)"
              :y="evidencePillY(det, camera) + evidenceBarY(camera, 0)"
              :width="evidenceBarWidth(det, camera, 'top_prob')"
              :height="evidenceBarHeight(camera)"
              :rx="Math.round(evidenceBarHeight(camera) * 0.5)"
              :fill="det.evidence.face_anchor_used ? '#a78bfa' : '#34d399'"
            />
            <!-- Top-2 bar -->
            <rect
              :x="evidencePillX(det, camera) + evidencePad(camera)"
              :y="evidencePillY(det, camera) + evidenceBarY(camera, 1)"
              :width="evidenceBarWidth(det, camera, 'top2_prob')"
              :height="Math.max(1, Math.round(evidenceBarHeight(camera) * 0.72))"
              :rx="Math.round(evidenceBarHeight(camera) * 0.36)"
              fill="#94a3b8"
            />
          </g>

          <!-- Face badge (crown) when face anchor was used -->
          <text
            v-if="showEvidence && det.evidence?.face_anchor_used"
            :x="(det.bbox.x_min || 0) + labelOffsetX(camera)"
            :y="(det.bbox.y_min || 0) + crownOffsetY(camera)"
            :font-size="labelFontSize(camera)"
            style="user-select: none"
          >
            👑
          </text>
        </g>
      </svg>
      <div v-if="isStale" class="live-tile-stale-badge">
        <v-icon size="12" class="mr-1">mdi-clock-alert-outline</v-icon>
        Last seen {{ staleLabelText }}
      </div>
      <!-- Cross-camera link badges: one per linked identity on this tile -->
      <div v-if="linkEntries.length" class="live-tile-link-stack">
        <div
          v-for="entry in linkEntries"
          :key="entry.identity_id"
          class="live-tile-link-badge"
          :style="{ borderColor: entry.color, color: entry.color }"
          :title="`GT linked: ${entry.display_name} also on ${entry.otherCameras.join(', ')}`"
        >
          <v-icon size="11" :color="entry.color">mdi-link-variant</v-icon>
          <span class="live-tile-link-name">{{ entry.display_name }}</span>
          <span class="live-tile-link-cams" :style="{ background: entry.color }"
            >+{{ entry.otherCameras.length }}</span
          >
        </div>
      </div>
    </div>
  </v-card>
</template>

<script setup>
import { toRef } from "vue";
import MaraudersInkBox from "@/components/marauders/MaraudersInkBox.vue";
import { HALO, postureColor } from "@/composables/useAnnotationStyle.js";
import { useLiveOverlayGeometry } from "@/composables/useLiveOverlayGeometry.js";

// COCO 17-keypoint limb pairs (0-indexed).
const LIMB_PAIRS = [
  [5, 6],
  [5, 7],
  [7, 9],
  [6, 8],
  [8, 10],
  [5, 11],
  [6, 12],
  [11, 12],
  [11, 13],
  [13, 15],
  [12, 14],
  [14, 16],
  [0, 5],
  [0, 6],
];

const props = defineProps({
  slotIndex: { type: Number, required: true },
  cameraId: { type: String, default: null },
  camera: { type: Object, default: null },
  availableCameras: { type: Array, required: true },
  layout: { type: Number, required: true },
  showBboxes: { type: Boolean, required: true },
  showIdLabels: { type: Boolean, required: true },
  showTrail: { type: Boolean, required: true },
  showPose: { type: Boolean, required: true },
  showEvidence: { type: Boolean, required: true },
  showPosture: { type: Boolean, required: true },
  maraudersEnabled: { type: Boolean, required: true },
  tileStyle: { type: Object, required: true },
  linkEntries: { type: Array, required: true },
  snapshotUrl: { type: String, default: null },
  displaySrc: { type: Function, required: true },
  isStale: { type: Boolean, required: true },
  staleLabelText: { type: String, required: true },
  isMultiCamera: { type: Function, required: true },
  multiCameraCount: { type: Function, required: true },
  multiCameraTooltip: { type: Function, required: true },
  bboxColor: { type: Function, required: true },
});

defineEmits(["camera-change", "frame-error", "open-correction"]);

const layout = toRef(props, "layout");
const {
  labelFontSize,
  smallFontSize,
  labelHaloStroke,
  overlayStroke,
  badgeRadius,
  evidenceBarY,
  evidenceBarHeight,
  evidencePillWidth,
  evidencePillHeight,
  evidencePad,
  evidenceFontSize,
  evidenceTextY,
  evidencePillX,
  evidencePillY,
  evidenceBarWidth,
  evidenceLabel,
  evidenceTooltip,
  labelOffsetX,
  labelOffsetY,
  crownOffsetY,
  postureLabelY,
  poseX,
  poseY,
  trailPoints,
} = useLiveOverlayGeometry(layout);
</script>

<style scoped>
.camera-picker {
  flex: 1 1 auto;
  min-width: 0;
}
.live-tile {
  background: var(--cc-surface-2);
  min-width: 0;
}
.live-tile :deep(.v-card-text:first-child) {
  flex-wrap: wrap;
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
