<template>
  <v-card class="mb-4">
    <v-card-title class="d-flex align-center">
      <span>Floor Plan</span>
      <v-spacer />
      <v-chip v-if="pendingPixel" color="warning" size="small" variant="tonal">
        Click to match point {{ points.length + 1 }}
      </v-chip>
    </v-card-title>
    <v-card-text class="pa-0 position-relative">
      <div
        class="snapshot-container"
        :class="pendingPixel ? 'cursor-crosshair fp-awaiting' : 'fp-idle'"
        @click="onFloorPlanClick"
      >
        <img
          ref="fpImgEl"
          :src="floorPlanUrl"
          class="snapshot-img marauders-no-paint"
          draggable="false"
          alt="Floor plan"
          @load="onFpImageLoad"
        />
        <svg
          v-if="fpImgRect"
          class="point-overlay"
          :viewBox="`0 0 ${fpImgRect.width} ${fpImgRect.height}`"
          :style="`width:${fpImgRect.width}px;height:${fpImgRect.height}px`"
        >
          <!-- Live coverage preview polygon -->
          <polygon
            v-if="previewCoveragePolygon"
            :points="previewCoveragePolygon"
            fill="rgba(99,102,241,0.12)"
            :stroke="
              qualityColor(previewStatus === 'ok' ? 0 : previewStatus === 'warning' ? 0.1 : 0.3)
            "
            stroke-width="2"
            stroke-dasharray="8 4"
          />
          <text
            v-if="previewCoveragePolygon && previewStatus"
            x="8"
            y="20"
            :fill="
              qualityColor(previewStatus === 'ok' ? 0 : previewStatus === 'warning' ? 0.1 : 0.3)
            "
            font-size="13"
            font-weight="700"
          >
            preview · {{ previewStatus }}
          </text>
          <!-- Draggable floor plan points with residual coloring -->
          <g
            v-for="(pt, i) in points"
            :key="i"
            style="cursor: grab"
            @mousedown.stop="startFloorDrag(i, $event)"
            @click.stop
          >
            <circle
              :cx="(pt.floor_m[0] / (fpWidth * fpMpp)) * fpImgRect.width"
              :cy="(pt.floor_m[1] / (fpHeight * fpMpp)) * fpImgRect.height"
              r="16"
              fill="transparent"
            />
            <circle
              :cx="(pt.floor_m[0] / (fpWidth * fpMpp)) * fpImgRect.width"
              :cy="(pt.floor_m[1] / (fpHeight * fpMpp)) * fpImgRect.height"
              r="8"
              fill="none"
              :stroke="pointColor(i)"
              stroke-width="2.5"
            />
            <circle
              :cx="(pt.floor_m[0] / (fpWidth * fpMpp)) * fpImgRect.width"
              :cy="(pt.floor_m[1] / (fpHeight * fpMpp)) * fpImgRect.height"
              r="2.5"
              :fill="pointColor(i)"
            />
            <text
              v-bind="haloSm"
              :x="(pt.floor_m[0] / (fpWidth * fpMpp)) * fpImgRect.width + 12"
              :y="(pt.floor_m[1] / (fpHeight * fpMpp)) * fpImgRect.height - 6"
              :fill="pointColor(i)"
              font-size="12"
              font-weight="700"
              style="pointer-events: none"
            >
              {{ i + 1 }}
            </text>
          </g>
          <!-- Awaiting-click indicator: pulsing crosshair target -->
          <g v-if="pendingPixel">
            <line
              x1="0"
              :y1="fpImgRect.height / 2"
              :x2="fpImgRect.width"
              :y2="fpImgRect.height / 2"
              stroke="#f59e0b"
              stroke-width="0.5"
              stroke-dasharray="6 4"
              opacity="0.4"
            />
            <line
              :x1="fpImgRect.width / 2"
              y1="0"
              :x2="fpImgRect.width / 2"
              :y2="fpImgRect.height"
              stroke="#f59e0b"
              stroke-width="0.5"
              stroke-dasharray="6 4"
              opacity="0.4"
            />
            <text
              x="50%"
              y="50%"
              text-anchor="middle"
              dominant-baseline="middle"
              fill="#f59e0b"
              font-size="13"
              font-weight="600"
              opacity="0.8"
            >
              Click here to place point {{ points.length + 1 }}
            </text>
          </g>
        </svg>
      </div>
      <div class="d-flex align-center px-3 py-2 text-caption text-medium-emphasis">
        <v-icon size="13" class="mr-1">mdi-map-marker</v-icon>
        Points are placed in the floor plan coordinate frame
        <template v-if="fpMpp"> &nbsp;({{ fpMpp }} m/px) </template>
      </div>
    </v-card-text>
  </v-card>
</template>

<script setup>
import { ref } from "vue";
import { HALO, qualityColor } from "@/composables/useAnnotationStyle.js";

// haloSm: floor-plan display-pixel SVG (viewBox = displayed size, font-size 12)
//   stroke-width 2 ≈ 17% of 12
const haloSm = HALO.attrs(2);

const props = defineProps({
  floorPlanUrl: { type: String, default: null },
  fpWidth: { type: Number, required: true },
  fpHeight: { type: Number, required: true },
  fpMpp: { type: Number, required: true },
  previewCoveragePolygon: { type: String, default: null },
  previewStatus: { type: String, default: null },
  pointColor: { type: Function, required: true },
  consumeAutoSuggestion: { type: Function, required: true },
});

const points = defineModel("points", { type: Array, required: true });
const pendingPixel = defineModel("pendingPixel", { type: Array, default: null });
const fpImgRect = defineModel("fpImgRect", { type: Object, default: null });

const fpImgEl = ref(null);

function onFpImageLoad() {
  if (!fpImgEl.value) return;
  const r = fpImgEl.value.getBoundingClientRect();
  fpImgRect.value = { width: r.width, height: r.height };
}

// ── Floor plan click (pick mode) ──────────────────────────────────────────
function onFloorPlanClick(e) {
  if (!pendingPixel.value || !fpImgEl.value) return;
  const r = fpImgEl.value.getBoundingClientRect();
  const xn = (e.clientX - r.left) / r.width;
  const yn = (e.clientY - r.top) / r.height;
  if (xn < 0 || xn > 1 || yn < 0 || yn > 1) return;

  const floorX = parseFloat((xn * props.fpWidth * props.fpMpp).toFixed(3));
  const floorY = parseFloat((yn * props.fpHeight * props.fpMpp).toFixed(3));

  points.value.push({
    pixel: pendingPixel.value,
    floor_m: [floorX, floorY],
  });
  props.consumeAutoSuggestion(pendingPixel.value);
  pendingPixel.value = null;
}

// ── Drag: floor plan pane ──────────────────────────────────────────────────
const floorDragIdx = ref(null);

function startFloorDrag(i, e) {
  e.preventDefault();
  e.stopPropagation();
  floorDragIdx.value = i;
  window.addEventListener("mousemove", onFloorDragMove);
  window.addEventListener("mouseup", stopFloorDrag);
}

function onFloorDragMove(e) {
  if (floorDragIdx.value === null) return;
  if (!fpImgEl.value || !fpImgRect.value) return;

  const r = fpImgEl.value.getBoundingClientRect();
  const xn = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
  const yn = Math.max(0, Math.min(1, (e.clientY - r.top) / r.height));

  const floorX = parseFloat((xn * props.fpWidth * props.fpMpp).toFixed(3));
  const floorY = parseFloat((yn * props.fpHeight * props.fpMpp).toFixed(3));

  const updated = points.value.map((pt, idx) =>
    idx === floorDragIdx.value ? { ...pt, floor_m: [floorX, floorY] } : pt,
  );
  points.value = updated;
}

function stopFloorDrag() {
  floorDragIdx.value = null;
  window.removeEventListener("mousemove", onFloorDragMove);
  window.removeEventListener("mouseup", stopFloorDrag);
}

defineExpose({ stopFloorDrag });
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

.fp-idle {
  cursor: default;
  opacity: 0.85;
}

.fp-awaiting {
  outline: 2px solid #f59e0b;
  outline-offset: -2px;
  border-radius: 4px;
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
