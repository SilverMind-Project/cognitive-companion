<template>
  <v-card>
    <v-card-title class="d-flex align-center">
      <span>Camera Frame</span>
      <v-spacer />
      <BlurToggle class="mr-2" />
      <v-btn size="small" variant="tonal" prepend-icon="mdi-camera" @click="$emit('refresh')">
        Refresh
      </v-btn>
    </v-card-title>
    <v-card-text class="pa-0 position-relative">
      <div
        class="snapshot-container"
        :class="{ 'cursor-crosshair': !!snapshotUrl }"
        @click="onCameraClick"
      >
        <img
          v-if="snapshotUrl"
          ref="imgEl"
          :src="displaySrc(snapshotUrl)"
          class="snapshot-img"
          draggable="false"
          @load="onImageLoad"
        />
        <div v-else class="d-flex align-center justify-center" style="height: 300px">
          <v-progress-circular v-if="snapshotLoading" indeterminate />
          <span v-else class="text-medium-emphasis text-body-2">
            Click "Refresh" to load a camera frame.
          </span>
        </div>

        <!-- Point overlay SVG (viewBox = natural camera resolution, positioned over content area) -->
        <svg
          v-if="snapshotUrl && imgContentRect"
          class="point-overlay"
          :viewBox="`0 0 ${imgContentRect.naturalWidth} ${imgContentRect.naturalHeight}`"
          :style="`width:${imgContentRect.width}px;height:${imgContentRect.height}px;top:${imgContentRect.offsetY}px;left:${imgContentRect.offsetX}px`"
        >
          <!-- Distribution guide: faint quadrant zones, shown until 4 points are placed -->
          <g v-if="points.length < 4">
            <rect
              x="0"
              y="0"
              :width="imgContentRect.naturalWidth / 2"
              :height="imgContentRect.naturalHeight / 2"
              fill="none"
              stroke="rgba(255,255,255,0.18)"
              stroke-width="2"
              stroke-dasharray="12 6"
            />
            <rect
              :x="imgContentRect.naturalWidth / 2"
              y="0"
              :width="imgContentRect.naturalWidth / 2"
              :height="imgContentRect.naturalHeight / 2"
              fill="none"
              stroke="rgba(255,255,255,0.18)"
              stroke-width="2"
              stroke-dasharray="12 6"
            />
            <rect
              x="0"
              :y="imgContentRect.naturalHeight / 2"
              :width="imgContentRect.naturalWidth / 2"
              :height="imgContentRect.naturalHeight / 2"
              fill="none"
              stroke="rgba(255,255,255,0.18)"
              stroke-width="2"
              stroke-dasharray="12 6"
            />
            <rect
              :x="imgContentRect.naturalWidth / 2"
              :y="imgContentRect.naturalHeight / 2"
              :width="imgContentRect.naturalWidth / 2"
              :height="imgContentRect.naturalHeight / 2"
              fill="none"
              stroke="rgba(255,255,255,0.18)"
              stroke-width="2"
              stroke-dasharray="12 6"
            />
            <text
              :x="imgContentRect.naturalWidth * 0.25"
              :y="imgContentRect.naturalHeight * 0.25"
              text-anchor="middle"
              dominant-baseline="middle"
              fill="rgba(255,255,255,0.35)"
              font-size="36"
              :opacity="pointInQuadrant(0) ? 0 : 1"
            >
              Place point here
            </text>
            <text
              :x="imgContentRect.naturalWidth * 0.75"
              :y="imgContentRect.naturalHeight * 0.25"
              text-anchor="middle"
              dominant-baseline="middle"
              fill="rgba(255,255,255,0.35)"
              font-size="36"
              :opacity="pointInQuadrant(1) ? 0 : 1"
            >
              Place point here
            </text>
            <text
              :x="imgContentRect.naturalWidth * 0.25"
              :y="imgContentRect.naturalHeight * 0.75"
              text-anchor="middle"
              dominant-baseline="middle"
              fill="rgba(255,255,255,0.35)"
              font-size="36"
              :opacity="pointInQuadrant(2) ? 0 : 1"
            >
              Place point here
            </text>
            <text
              :x="imgContentRect.naturalWidth * 0.75"
              :y="imgContentRect.naturalHeight * 0.75"
              text-anchor="middle"
              dominant-baseline="middle"
              fill="rgba(255,255,255,0.35)"
              font-size="36"
              :opacity="pointInQuadrant(3) ? 0 : 1"
            >
              Place point here
            </text>
          </g>
          <!-- Completed points — draggable with residual coloring -->
          <g
            v-for="(pt, i) in points"
            :key="i"
            style="cursor: grab"
            @mousedown.stop="startCameraDrag(i, $event)"
            @click.stop
          >
            <circle :cx="pt.pixel[0]" :cy="pt.pixel[1]" r="40" fill="transparent" />
            <circle
              :cx="pt.pixel[0]"
              :cy="pt.pixel[1]"
              r="30"
              fill="none"
              :stroke="pointColor(i)"
              stroke-width="3"
            />
            <circle :cx="pt.pixel[0]" :cy="pt.pixel[1]" r="12" :fill="pointColor(i)" />
            <text
              v-bind="haloLg"
              :x="pt.pixel[0] + 18"
              :y="pt.pixel[1] - 10"
              :fill="pointColor(i)"
              font-size="48"
              font-weight="500"
              style="pointer-events: none"
            >
              {{ i + 1 }}
            </text>
          </g>
          <!-- Auto-calibration suggestions: camera pixels only, not floor-plan coordinates -->
          <g
            v-for="(pt, i) in autoSuggestedPoints"
            :key="`auto-${i}`"
            class="auto-suggestion-marker"
          >
            <circle
              :cx="pt.pixel[0]"
              :cy="pt.pixel[1]"
              r="24"
              fill="none"
              stroke="#38bdf8"
              stroke-width="3"
              stroke-dasharray="8 6"
            />
            <circle :cx="pt.pixel[0]" :cy="pt.pixel[1]" r="7" fill="#38bdf8" opacity="0.85" />
          </g>
          <!-- Floor-region polygon overlay (draggable vertices) -->
          <g v-if="floorRegionDraft && floorRegionSvgPoints">
            <polygon
              :points="floorRegionSvgPoints"
              fill="rgba(16,185,129,0.12)"
              stroke="#10b981"
              stroke-width="3"
              stroke-dasharray="10 5"
            />
            <g
              v-for="(pt, vi) in floorRegionDraft"
              :key="`fr-${vi}`"
              :transform="`translate(${frPtToSvg(pt)?.[0] ?? 0},${frPtToSvg(pt)?.[1] ?? 0})`"
              style="cursor: grab"
              @mousedown.stop="startFloorRegionDrag(vi, $event)"
              @click.stop
            >
              <circle r="32" fill="transparent" />
              <circle r="14" fill="#10b981" opacity="0.85" />
              <circle r="14" fill="none" stroke="white" stroke-width="2" />
            </g>
          </g>
          <!-- Pending camera point -->
          <g v-if="pendingPixel">
            <circle
              :cx="pendingPixel[0]"
              :cy="pendingPixel[1]"
              r="50"
              fill="none"
              stroke="#f59e0b"
              stroke-width="2.5"
              stroke-dasharray="4 3"
            />
            <circle :cx="pendingPixel[0]" :cy="pendingPixel[1]" r="15" fill="#f59e0b" />
            <text
              v-bind="haloLg"
              :x="pendingPixel[0] + 18"
              :y="pendingPixel[1] - 10"
              fill="#f59e0b"
              font-size="48"
              font-weight="500"
            >
              {{ points.length + 1 }}?
            </text>
          </g>
        </svg>
      </div>

      <!-- Camera status bar -->
      <div class="d-flex align-center px-3 py-2 text-caption text-medium-emphasis">
        <template v-if="!snapshotUrl" />
        <template v-else-if="pendingPixel && inputMode === 'pick'">
          <v-icon size="14" color="warning" class="mr-1">mdi-arrow-right-circle</v-icon>
          Point {{ points.length + 1 }} placed — now click the same spot on the floor plan →
        </template>
        <template v-else>
          <v-icon size="14" class="mr-1">mdi-cursor-default-click</v-icon>
          Click a floor-level spot to place point {{ points.length + 1 }}
          <template v-if="points.length < 4"> ({{ 4 - points.length }} more needed) </template>
        </template>
      </div>
    </v-card-text>
  </v-card>
</template>

<script setup>
import { ref, computed } from "vue";
import BlurToggle from "@/components/cts/BlurToggle.vue";
import { HALO } from "@/composables/useAnnotationStyle.js";

// haloLg: camera natural-resolution SVG (viewBox ~1920×1080, font-size 48)
//   stroke-width 8 ≈ 17% of 48 — thin enough to not distort letterforms
const haloLg = HALO.attrs(8);

const props = defineProps({
  snapshotUrl: { type: String, default: null },
  snapshotLoading: { type: Boolean, default: false },
  autoSuggestedPoints: { type: Array, required: true },
  inputMode: { type: String, required: true },
  floorPlanReady: { type: Boolean, required: true },
  scaleReady: { type: Boolean, required: true },
  pointColor: { type: Function, required: true },
  pointInQuadrant: { type: Function, required: true },
  displaySrc: { type: Function, required: true },
  nearestAutoSuggestion: { type: Function, required: true },
  consumeAutoSuggestion: { type: Function, required: true },
});
defineEmits(["refresh"]);

const points = defineModel("points", { type: Array, required: true });
const pendingPixel = defineModel("pendingPixel", { type: Array, default: null });
const floorRegionDraft = defineModel("floorRegionDraft", { type: Array, default: null });
const floorRegionDragIdx = defineModel("floorRegionDragIdx", { type: Number, default: null });
const imgContentRect = defineModel("imgContentRect", { type: Object, default: null });

const imgEl = ref(null);

// ── Image load / resize ───────────────────────────────────────────────────
function onImageLoad() {
  if (!imgEl.value) return;
  const r = imgEl.value.getBoundingClientRect();
  const nw = imgEl.value.naturalWidth;
  const nh = imgEl.value.naturalHeight;
  if (!nw || !nh) return;
  const naturalRatio = nw / nh;
  const elRatio = r.width / r.height;
  let contentW, contentH, offX, offY;
  if (naturalRatio > elRatio) {
    // Letterboxed (bars top/bottom).
    contentW = r.width;
    contentH = r.width / naturalRatio;
    offX = 0;
    offY = (r.height - contentH) / 2;
  } else {
    // Pillarboxed (bars left/right).
    contentH = r.height;
    contentW = r.height * naturalRatio;
    offX = (r.width - contentW) / 2;
    offY = 0;
  }
  imgContentRect.value = {
    width: contentW,
    height: contentH,
    offsetX: offX,
    offsetY: offY,
    naturalWidth: nw,
    naturalHeight: nh,
  };
}

// ── Camera click ──────────────────────────────────────────────────────────
function onCameraClick(e) {
  if (!props.snapshotUrl || !imgEl.value || !imgContentRect.value) return;
  const r = imgEl.value.getBoundingClientRect();
  const {
    offsetX,
    offsetY,
    width: cw,
    height: ch,
    naturalWidth: nw,
    naturalHeight: nh,
  } = imgContentRect.value;
  // Click position relative to the image content area (excluding pillar/letterbox bars).
  const relX = e.clientX - r.left - offsetX;
  const relY = e.clientY - r.top - offsetY;
  if (relX < 0 || relX > cw || relY < 0 || relY > ch) return;
  // Convert to raw pixel coords in the camera's natural resolution.
  let px = Math.round((relX / cw) * nw);
  let py = Math.round((relY / ch) * nh);
  const suggestion = props.nearestAutoSuggestion(px, py);
  if (suggestion) {
    px = suggestion.pixel[0];
    py = suggestion.pixel[1];
  }

  if (props.inputMode === "pick" && props.floorPlanReady && props.scaleReady) {
    pendingPixel.value = [px, py];
  } else {
    points.value.push({ pixel: [px, py], floor_m: [0, 0] });
  }
}

// ── Drag: camera pane ──────────────────────────────────────────────────────
const cameraDragIdx = ref(null);

function startCameraDrag(i, e) {
  e.preventDefault();
  e.stopPropagation();
  cameraDragIdx.value = i;
  window.addEventListener("mousemove", onCameraDragMove);
  window.addEventListener("mouseup", stopCameraDrag);
}

function onCameraDragMove(e) {
  if (cameraDragIdx.value === null) return;
  if (!imgEl.value || !imgContentRect.value) return;

  const r = imgEl.value.getBoundingClientRect();
  const {
    offsetX,
    offsetY,
    width: cw,
    height: ch,
    naturalWidth: nw,
    naturalHeight: nh,
  } = imgContentRect.value;

  const relX = Math.max(0, Math.min(cw, e.clientX - r.left - offsetX));
  const relY = Math.max(0, Math.min(ch, e.clientY - r.top - offsetY));

  const px = Math.round((relX / cw) * nw);
  const py = Math.round((relY / ch) * nh);

  const updated = points.value.map((pt, idx) =>
    idx === cameraDragIdx.value ? { ...pt, pixel: [px, py] } : pt,
  );
  points.value = updated;
}

function stopCameraDrag() {
  cameraDragIdx.value = null;
  window.removeEventListener("mousemove", onCameraDragMove);
  window.removeEventListener("mouseup", stopCameraDrag);
}

// ── Floor-region overlay ───────────────────────────────────────────────────

// Convert normalised [x_norm, y_norm] to SVG coords in the camera natural-resolution viewBox.
function frPtToSvg(pt) {
  if (!imgContentRect.value) return null;
  const { naturalWidth: nw, naturalHeight: nh } = imgContentRect.value;
  return [pt[0] * nw, pt[1] * nh];
}

// SVG polygon points string from the draft polygon.
const floorRegionSvgPoints = computed(() => {
  if (!floorRegionDraft.value || !imgContentRect.value) return null;
  return floorRegionDraft.value
    .map((pt) => {
      const sv = frPtToSvg(pt);
      return sv ? `${sv[0].toFixed(1)},${sv[1].toFixed(1)}` : null;
    })
    .filter(Boolean)
    .join(" ");
});

function startFloorRegionDrag(idx, e) {
  if (!floorRegionDraft.value) return;
  e.preventDefault();
  e.stopPropagation();
  floorRegionDragIdx.value = idx;
  window.addEventListener("mousemove", onFloorRegionDragMove);
  window.addEventListener("mouseup", stopFloorRegionDrag);
}

function onFloorRegionDragMove(e) {
  if (floorRegionDragIdx.value === null || !imgEl.value || !imgContentRect.value) return;
  const r = imgEl.value.getBoundingClientRect();
  const { offsetX, offsetY, width: cw, height: ch } = imgContentRect.value;
  const relX = Math.max(0, Math.min(cw, e.clientX - r.left - offsetX));
  const relY = Math.max(0, Math.min(ch, e.clientY - r.top - offsetY));
  const xn = parseFloat((relX / cw).toFixed(4));
  const yn = parseFloat((relY / ch).toFixed(4));
  const updated = floorRegionDraft.value.map((pt, i) =>
    i === floorRegionDragIdx.value ? [xn, yn] : pt,
  );
  floorRegionDraft.value = updated;
}

function stopFloorRegionDrag() {
  floorRegionDragIdx.value = null;
  window.removeEventListener("mousemove", onFloorRegionDragMove);
  window.removeEventListener("mouseup", stopFloorRegionDrag);
}

defineExpose({ stopCameraDrag, stopFloorRegionDrag });
</script>

<style scoped>
.snapshot-container {
  position: relative;
  display: inline-block;
  width: 100%;
  user-select: none;
}

.cursor-crosshair {
  cursor: crosshair;
}

.snapshot-img {
  display: block;
  width: 100%;
  max-height: 380px;
  object-fit: contain;
}

.point-overlay {
  position: absolute;
  pointer-events: none;
}
</style>
