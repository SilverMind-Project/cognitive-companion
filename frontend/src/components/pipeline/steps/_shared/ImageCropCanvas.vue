<!--
  Crop-region editor canvas. Modelled on the keyframe annotation editor
  (components/cts/keyframes/BboxCanvas.vue): an <img> shows the sample frame, a
  transparent <canvas> overlay handles interaction and selection, and (in
  Marauder's Map mode) an SVG overlay renders committed regions as hand-drawn
  ink boxes. Drag to draw a region, drag the interior to move, drag a corner to
  resize. A bare click never creates a region (a drag must exceed a minimum),
  so the canvas never produces a degenerate 0x0 region.

  Shares pure interaction geometry with the annotation canvas via
  composables/bboxGeometry.js. Regions are stored as ratios ({x, y, width,
  height} in 0..1) so they are resolution-independent.
-->
<template>
  <div ref="wrapperRef" class="crop-canvas-wrapper" :style="{ minHeight: imageLoaded ? null : '200px' }">
    <div v-if="!imageUrl" class="crop-canvas-placeholder d-flex align-center justify-center">
      <div class="text-center text-medium-emphasis">
        <v-icon size="48" color="var(--cc-text-3)">mdi-image-outline</v-icon>
        <div class="text-body-2 mt-2">Load a sample image, then drag to draw a crop region</div>
      </div>
    </div>

    <template v-else>
      <img
        ref="imgRef"
        :src="imageUrl"
        class="crop-image"
        draggable="false"
        @load="onImageLoad"
      />
      <canvas
        ref="canvasRef"
        class="crop-overlay"
        :style="{ cursor: cursorStyle }"
        @mousedown="onPointerDown"
        @mousemove="onPointerMove"
        @mouseup="onPointerUp"
        @mouseleave="onPointerUp"
        @touchstart.prevent="onPointerDown"
        @touchmove.prevent="onPointerMove"
        @touchend="onPointerUp"
      />
      <!-- Hand-drawn committed regions for Marauder's mode. pointer-events:none
           so gestures pass through to the canvas. The actively-dragged region is
           excluded (drawn plain on the canvas) to avoid per-frame ink reseed. -->
      <svg
        v-if="marauders.state.enabled && dispW > 0"
        class="crop-ink-overlay"
        :viewBox="`0 0 ${dispW} ${dispH}`"
      >
        <MaraudersInkBox
          v-for="{ region, index } in inkRegions"
          :key="region.id ?? index"
          :x="region.x * dispW"
          :y="region.y * dispH"
          :w="region.width * dispW"
          :h="region.height * dispH"
          :seed-key="String(region.id ?? index)"
        />
      </svg>
    </template>
  </div>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { ccToken } from "@/composables/useChartTheme.js";
import { useMaraudersMode } from "@/composables/useMaraudersMode.js";
import MaraudersInkBox from "@/components/marauders/MaraudersInkBox.vue";
import {
  applyCornerDrag,
  clamp01,
  hitTestRect,
  normalizeRect,
} from "@/composables/bboxGeometry.js";

const props = defineProps({
  imageUrl: { type: String, default: "" },
  regions: { type: Array, default: () => [] },
  selectedIndex: { type: Number, default: -1 },
});

const emit = defineEmits(["update:regions", "select-region"]);

const marauders = useMaraudersMode();

const imgRef = ref(null);
const canvasRef = ref(null);
const imageLoaded = ref(false);
// Displayed (CSS-pixel) size of the image/overlay. The ink overlay draws in
// this space so MaraudersInkBox's stroke width and rough.js wobble are visible
// at screen scale (a natural-pixel viewBox would shrink them to sub-pixel).
const dispW = ref(0);
const dispH = ref(0);

// Visual handle box size (px) and the minimum drag (px) that creates a region.
const HANDLE_SIZE = 8;
const MIN_DRAW_PX = 6;

// Active gesture. mode: "existing" (move/resize) | "draw" (new box).
const drag = { active: false, mode: null, corner: null, lastX: 0, lastY: 0 };
// Index of the region being actively dragged (-1 = none). A ref so the ink
// overlay reactively excludes it during a drag (no sketchy reseed shimmer).
const activeDragIndex = ref(-1);
// Live draw preview, in canvas px. Null when not drawing.
const draft = ref(null);

const cursorStyle = computed(() => {
  if (drag.active && drag.mode === "existing") {
    return drag.corner === "move" ? "move" : "nwse-resize";
  }
  return "crosshair";
});

// Committed regions rendered as ink in Marauder's mode, excluding the region
// currently being dragged (it is drawn plain on the canvas instead).
const inkRegions = computed(() => {
  if (!marauders.state.enabled) return [];
  return (props.regions || [])
    .map((region, index) => ({ region, index }))
    .filter(({ index }) => index !== activeDragIndex.value);
});

// ---- Image load + sizing ----

function onImageLoad() {
  const imgEl = imgRef.value;
  const canvas = canvasRef.value;
  if (!imgEl || !canvas) return;
  // Size the overlay to the displayed image so canvas px map 1:1 to CSS px.
  canvas.width = imgEl.clientWidth;
  canvas.height = imgEl.clientHeight;
  dispW.value = canvas.width;
  dispH.value = canvas.height;
  imageLoaded.value = true;
  draw();
}

// Redraw when regions, selection, or the theme change.
watch(
  () => [props.regions, props.selectedIndex, marauders.state.enabled],
  draw,
  { deep: true },
);

// ---- Coordinate conversion (ratio <-> canvas px) ----

function clientToCanvas(clientX, clientY) {
  const canvas = canvasRef.value;
  if (!canvas) return { x: 0, y: 0 };
  const rect = canvas.getBoundingClientRect();
  const sx = rect.width ? canvas.width / rect.width : 1;
  const sy = rect.height ? canvas.height / rect.height : 1;
  return { x: (clientX - rect.left) * sx, y: (clientY - rect.top) * sy };
}

function pointerPos(e) {
  if (e.touches) {
    if (e.touches.length === 0) return null;
    return clientToCanvas(e.touches[0].clientX, e.touches[0].clientY);
  }
  return clientToCanvas(e.clientX, e.clientY);
}

function regionToRect(r) {
  const canvas = canvasRef.value;
  return {
    x1: r.x * canvas.width,
    y1: r.y * canvas.height,
    x2: (r.x + r.width) * canvas.width,
    y2: (r.y + r.height) * canvas.height,
  };
}

function rectToRegion(rect) {
  const canvas = canvasRef.value;
  const n = normalizeRect(rect);
  const x = clamp01(n.x1 / canvas.width);
  const y = clamp01(n.y1 / canvas.height);
  return {
    x,
    y,
    width: clamp01(n.x2 / canvas.width) - x,
    height: clamp01(n.y2 / canvas.height) - y,
  };
}

// ---- Drawing ----

function draw() {
  const canvas = canvasRef.value;
  if (!canvas || !imageLoaded.value) return;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // Selection accent is the DS brand (sage in ccWarm, parchment-brown in
  // ccMarauders). Unselected boxes use white-on-photo for universal contrast
  // over an arbitrary camera image -- the canvas annotation convention (see
  // front-end skill), theme-agnostic by design, not a token candidate.
  const brand = ccToken("--cc-brand");
  const neutral = ccToken("--cc-text-1");
  const ink = marauders.state.enabled;

  (props.regions || []).forEach((r, i) => {
    const selected = i === props.selectedIndex;
    const dragging = i === activeDragIndex.value;
    // In Marauder's mode committed boxes are drawn as SVG ink. The canvas only
    // adds something for the selected box (grab handles over the ink) and the
    // actively-dragged box (a crisp plain rect, since it is excluded from ink).
    if (ink && !selected && !dragging) return;

    const rect = regionToRect(r);

    // Selected but not being dragged, in ink mode: the ink box IS the outline,
    // so only paint the grab handles -- no solid fill/stroke (that is what made
    // drawn regions look like plain rectangles).
    if (ink && selected && !dragging) {
      drawHandles(ctx, rect, brand);
      return;
    }

    const w = rect.x2 - rect.x1;
    const h = rect.y2 - rect.y1;

    ctx.fillStyle = selected ? withAlpha(brand, 0.16) : "rgba(255, 255, 255, 0.06)";
    ctx.fillRect(rect.x1, rect.y1, w, h);

    ctx.strokeStyle = selected ? brand : "rgba(255, 255, 255, 0.7)";
    ctx.lineWidth = selected ? 2.5 : 1.5;
    ctx.strokeRect(rect.x1, rect.y1, w, h);

    // Canvas label only in the default theme (the ink box carries the visual).
    if (!ink) {
      const label = r.name || r.id || `Region ${i + 1}`;
      ctx.font = "12px sans-serif";
      const textW = ctx.measureText(label).width;
      const labelY = rect.y1 - 6 > 16 ? rect.y1 - 6 : rect.y1 + 16;
      ctx.fillStyle = selected ? brand : neutral;
      ctx.fillRect(rect.x1, labelY - 12, textW + 8, 16);
      ctx.fillStyle = "#fff";
      ctx.fillText(label, rect.x1 + 4, labelY);
    }

    if (selected || dragging) drawHandles(ctx, rect, brand);
  });

  if (draft.value) {
    const n = normalizeRect(draft.value);
    ctx.strokeStyle = brand;
    ctx.lineWidth = 2;
    ctx.setLineDash([6, 3]);
    ctx.strokeRect(n.x1, n.y1, n.x2 - n.x1, n.y2 - n.y1);
    ctx.setLineDash([]);
  }
}

function drawHandles(ctx, rect, color) {
  ctx.fillStyle = color;
  for (const [hx, hy] of [
    [rect.x1, rect.y1],
    [rect.x2, rect.y1],
    [rect.x2, rect.y2],
    [rect.x1, rect.y2],
  ]) {
    ctx.fillRect(hx - HANDLE_SIZE / 2, hy - HANDLE_SIZE / 2, HANDLE_SIZE, HANDLE_SIZE);
  }
}

function withAlpha(color, alpha) {
  const m = color.trim().match(/^#?([0-9a-f]{6})$/i);
  if (m) {
    const n = parseInt(m[1], 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
  }
  const rgb = color.match(/\d+/g);
  if (rgb && rgb.length >= 3) {
    return `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${alpha})`;
  }
  // Theme-neutral fallback (only if a token failed to resolve to hex/rgb).
  return `rgba(127, 127, 127, ${alpha})`;
}

// ---- Hit testing ----

function hitRegion(px, py) {
  const regions = props.regions || [];
  for (let i = regions.length - 1; i >= 0; i--) {
    const part = hitTestRect(px, py, regionToRect(regions[i]));
    if (!part) continue;
    // Corner handles only resize the already-selected region; otherwise the
    // gesture selects and moves the region.
    const corner = part !== "move" && i === props.selectedIndex ? part : "move";
    return { index: i, corner };
  }
  return null;
}

// ---- Pointer gesture (shared by mouse + touch) ----

function onPointerDown(e) {
  if (!imageLoaded.value) return;
  const pos = pointerPos(e);
  if (!pos) return;

  const hit = hitRegion(pos.x, pos.y);
  if (hit) {
    drag.active = true;
    drag.mode = "existing";
    drag.corner = hit.corner;
    drag.lastX = pos.x;
    drag.lastY = pos.y;
    activeDragIndex.value = hit.index;
    emit("select-region", hit.index);
    draw();
    return;
  }

  // Start a draw. Do NOT create a region yet: a bare click must not persist a
  // degenerate box. The region is materialised on release if big enough.
  drag.active = true;
  drag.mode = "draw";
  draft.value = { x1: pos.x, y1: pos.y, x2: pos.x, y2: pos.y };
  draw();
}

function onPointerMove(e) {
  if (!drag.active || !imageLoaded.value) return;
  const pos = pointerPos(e);
  if (!pos) return;

  if (drag.mode === "draw") {
    draft.value.x2 = pos.x;
    draft.value.y2 = pos.y;
    draw();
    return;
  }

  const dx = pos.x - drag.lastX;
  const dy = pos.y - drag.lastY;
  drag.lastX = pos.x;
  drag.lastY = pos.y;

  const regions = [...(props.regions || [])];
  const current = regions[activeDragIndex.value];
  if (!current) return;
  const moved = applyCornerDrag(regionToRect(current), drag.corner, dx, dy);
  regions[activeDragIndex.value] = { ...current, ...rectToRegion(moved) };
  emit("update:regions", regions);
}

function onPointerUp() {
  if (!drag.active) return;

  if (drag.mode === "draw" && draft.value) {
    const { x1, y1, x2, y2 } = draft.value;
    if (Math.abs(x2 - x1) >= MIN_DRAW_PX && Math.abs(y2 - y1) >= MIN_DRAW_PX) {
      const region = rectToRegion(draft.value);
      const next = props.regions || [];
      const newRegion = {
        id: `region_${next.length + 1}`,
        name: `Region ${next.length + 1}`,
        ...region,
      };
      emit("update:regions", [...next, newRegion]);
      emit("select-region", next.length);
    }
  }

  drag.active = false;
  drag.mode = null;
  drag.corner = null;
  activeDragIndex.value = -1;
  draft.value = null;
  draw();
}

defineExpose({ draw });
</script>

<style scoped>
.crop-canvas-wrapper {
  position: relative;
  display: block;
  overflow: hidden;
  background: var(--cc-surface-2);
  border-radius: var(--cc-radius-md);
}
.crop-canvas-placeholder {
  min-height: 200px;
  margin: 8px;
  border: 2px dashed var(--cc-divider-strong);
  border-radius: var(--cc-radius-md);
}
.crop-image {
  display: block;
  width: 100%;
  height: auto;
  user-select: none;
  border-radius: var(--cc-radius-md);
}
.crop-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
}
.crop-ink-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}
</style>
