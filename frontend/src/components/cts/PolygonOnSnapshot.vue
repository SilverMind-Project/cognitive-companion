<template>
  <div>
    <div
      ref="containerEl"
      class="polygon-outer"
      @wheel.prevent="zoom.actions.onWheel"
      @mousedown="onContainerMouseDown"
      @contextmenu.prevent
    >
      <div class="polygon-zoom-content" :style="zoom.state.transformStyle">
        <img
          v-if="imageUrl"
          ref="imgEl"
          :src="imageUrl"
          class="polygon-img"
          draggable="false"
          @load="onImageLoad"
        />
        <div v-else class="polygon-empty d-flex align-center justify-center">
          <v-icon color="medium-emphasis" size="32">mdi-image-outline</v-icon>
          <span class="text-medium-emphasis text-body-2 ml-2">No snapshot loaded</span>
        </div>

        <svg
          v-if="svgReady"
          ref="svgEl"
          class="polygon-overlay"
          :viewBox="`0 0 ${svgW} ${svgH}`"
          :style="`width:${svgW}px;height:${svgH}px;top:${svgOffY}px;left:${svgOffX}px`"
          @click.exact="onSvgClick"
          @dblclick="onDblClick"
        >
          <!-- Polygon translucent fill -->
          <polygon
            v-if="pts.length >= 3"
            :points="svgPtsStr"
            class="poly-fill"
          />
          <!-- Open polyline edges -->
          <polyline
            v-if="pts.length >= 2"
            :points="svgPtsStr"
            class="poly-edge"
          />
          <!-- Dashed closing edge hint -->
          <line
            v-if="pts.length >= 3"
            :x1="sx(pts[pts.length - 1][0])"
            :y1="sy(pts[pts.length - 1][1])"
            :x2="sx(pts[0][0])"
            :y2="sy(pts[0][1])"
            class="poly-edge-close"
          />
          <!-- Vertex handles -->
          <g
            v-for="(pt, i) in pts"
            :key="i"
            :style="readonly ? '' : 'cursor:grab'"
            @click.stop
            @mousedown.stop="startDrag(i, $event)"
            @contextmenu.prevent.stop="deleteVertex(i)"
          >
            <!-- Invisible hit target (larger radius) -->
            <circle :cx="sx(pt[0])" :cy="sy(pt[1])" r="12" style="fill:transparent" />
            <!-- Visible dot -->
            <circle :cx="sx(pt[0])" :cy="sy(pt[1])" r="5" class="vertex-dot" />
            <!-- Label -->
            <text :x="sx(pt[0]) + 9" :y="sy(pt[1]) - 5" class="vertex-label">{{ i + 1 }}</text>
          </g>
        </svg>
      </div>

      <CcZoomControls
        :zoom="zoom.state.zoom"
        :pan-x="zoom.state.panX"
        :pan-y="zoom.state.panY"
        @zoom-in="zoom.actions.zoomIn(containerEl)"
        @zoom-out="zoom.actions.zoomOut(containerEl)"
        @reset="zoom.actions.reset()"
      />
    </div>

    <div v-if="!readonly" class="d-flex align-center mt-2">
      <span class="text-caption text-medium-emphasis">
        {{ pts.length }} {{ pts.length === 1 ? 'point' : 'points' }}
        <template v-if="minPoints && pts.length < minPoints">
          — {{ minPoints - pts.length }} more needed
        </template>
      </span>
      <v-spacer />
      <v-btn
        v-if="pts.length >= minPoints"
        size="x-small"
        variant="tonal"
        class="mr-2"
        @click="emit('closed', pts)"
      >
        Close polygon
      </v-btn>
      <v-btn
        v-if="pts.length > 0"
        size="x-small"
        variant="text"
        color="error"
        @click="clearAll"
      >
        Clear
      </v-btn>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from "vue";
import { useCanvasZoom } from "@/composables/useCanvasZoom.js";
import CcZoomControls from "@/components/common/CcZoomControls.vue";

const props = defineProps({
  imageUrl: { type: String, default: null },
  modelValue: { type: Array, default: () => [] },
  readonly: { type: Boolean, default: false },
  minPoints: { type: Number, default: 3 },
  maxPoints: { type: Number, default: null },
});

const emit = defineEmits(["update:modelValue", "closed", "clear"]);

// ── zoom / pan ──────────────────────────────────────────────────────────
const containerEl = ref(null);
const zoom = useCanvasZoom();

function onContainerMouseDown(e) {
  // Always arm pan — the 3px threshold gate in useCanvasZoom prevents accidental
  // drags from registering as pans. Vertex and edge drags use @mousedown.stop so
  // they never bubble here. onSvgClick checks zoom.state.didPan before placing
  // a vertex, so a true drag never places a point.
  zoom.actions.startPan(e);
}

// ── image + SVG overlay sizing ──────────────────────────────────────────
const imgEl = ref(null);
const svgEl = ref(null);
const svgW = ref(0);
const svgH = ref(0);
const svgOffX = ref(0);
const svgOffY = ref(0);
const svgReady = computed(() => svgW.value > 0 && svgH.value > 0);
const pts = computed(() => props.modelValue);

let resizeObserver = null;

/**
 * Compute SVG overlay position / size to match the image content area.
 * Uses offset* properties (pre-transform layout values) so the overlay
 * alignment stays correct regardless of the zoom/pan CSS transform.
 */
function syncSize() {
  if (!imgEl.value) return;
  const nw = imgEl.value.naturalWidth;
  const nh = imgEl.value.naturalHeight;
  const elW = imgEl.value.offsetWidth;
  const elH = imgEl.value.offsetHeight;
  const elLeft = imgEl.value.offsetLeft;
  const elTop = imgEl.value.offsetTop;

  if (!nw || !nh) {
    svgW.value = Math.round(elW);
    svgH.value = Math.round(elH);
    svgOffX.value = Math.round(elLeft);
    svgOffY.value = Math.round(elTop);
    return;
  }

  // Compute letterboxing within the <img> element (object-fit: contain).
  const naturalRatio = nw / nh;
  const elRatio = elW / elH;
  let contentW, contentH, offX, offY;

  if (naturalRatio > elRatio) {
    // Image wider than element → letterbox top/bottom.
    contentW = elW;
    contentH = elW / naturalRatio;
    offX = 0;
    offY = (elH - contentH) / 2;
  } else {
    // Image taller than element → pillarbox left/right.
    contentH = elH;
    contentW = elH * naturalRatio;
    offX = (elW - contentW) / 2;
    offY = 0;
  }

  svgW.value = Math.round(contentW);
  svgH.value = Math.round(contentH);
  svgOffX.value = Math.round(elLeft + offX);
  svgOffY.value = Math.round(elTop + offY);
}

function onImageLoad() {
  syncSize();
}

onMounted(() => {
  if (typeof ResizeObserver !== "undefined") {
    resizeObserver = new ResizeObserver(syncSize);
    if (imgEl.value) resizeObserver.observe(imgEl.value);
  }
});

watch(imgEl, (el) => {
  if (resizeObserver && el) resizeObserver.observe(el);
});

// ── coordinate helpers (viewBox units) ──────────────────────────────────
function sx(nx) { return nx * svgW.value; }
function sy(ny) { return ny * svgH.value; }

const svgPtsStr = computed(() =>
  pts.value.map(([x, y]) => `${sx(x)},${sy(y)}`).join(" ")
);

// ── vertex placement (click) ────────────────────────────────────────────
function onSvgClick(e) {
  if (props.readonly) return;
  // Ignore when the user was panning (didPan = true means drag exceeded threshold).
  if (zoom.state.didPan) { zoom.state.didPan = false; return; }
  if (e.detail >= 2) return;
  if (props.maxPoints != null && pts.value.length >= props.maxPoints) return;

  const rect = svgEl.value.getBoundingClientRect();
  const x = parseFloat(((e.clientX - rect.left) / rect.width).toFixed(4));
  const y = parseFloat(((e.clientY - rect.top) / rect.height).toFixed(4));
  if (x < 0 || x > 1 || y < 0 || y > 1) return;
  emit("update:modelValue", [...pts.value, [x, y]]);
}

function onDblClick() {
  if (pts.value.length >= (props.minPoints ?? 3)) {
    emit("closed", pts.value);
  }
}

function deleteVertex(i) {
  if (props.readonly) return;
  emit("update:modelValue", pts.value.filter((_, idx) => idx !== i));
}

function clearAll() {
  emit("update:modelValue", []);
  emit("clear");
}

// ── vertex dragging ─────────────────────────────────────────────────────
let dragIdx = -1;

function startDrag(i, e) {
  if (props.readonly) return;
  dragIdx = i;
  window.addEventListener("mousemove", onDragMove);
  window.addEventListener("mouseup", stopDrag);
  e.preventDefault();
}

function onDragMove(e) {
  if (dragIdx < 0 || !svgEl.value) return;
  const rect = svgEl.value.getBoundingClientRect();
  const x = parseFloat(Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width)).toFixed(4));
  const y = parseFloat(Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height)).toFixed(4));
  emit(
    "update:modelValue",
    pts.value.map((pt, i) => (i === dragIdx ? [x, y] : pt))
  );
}

function stopDrag() {
  dragIdx = -1;
  window.removeEventListener("mousemove", onDragMove);
  window.removeEventListener("mouseup", stopDrag);
}

onBeforeUnmount(() => {
  if (resizeObserver) {
    resizeObserver.disconnect();
    resizeObserver = null;
  }
  stopDrag();
});
</script>

<style scoped>
/* ── outer container clips zoomed content ──────────────────────────── */
.polygon-outer {
  position: relative;
  overflow: hidden;
  min-height: 320px;
  max-height: min(640px, 72vh);
  background: var(--cc-surface-2);
  border: 1px solid var(--cc-divider-strong);
  border-radius: 8px;
}

/* ── inner wrapper receives the zoom/pan CSS transform ─────────────── */
.polygon-zoom-content {
  position: relative;
  display: inline-block;
  min-width: 100%;
  will-change: transform;
}

.polygon-img {
  display: block;
  width: 100%;
  max-height: min(640px, 72vh);
  object-fit: contain;
}

.polygon-empty {
  height: 320px;
  border: 1px dashed var(--cc-divider-strong);
  border-radius: 8px;
  background: var(--cc-surface-2);
}

.polygon-overlay {
  position: absolute;
  cursor: crosshair;
  pointer-events: all;
}

.poly-fill {
  fill: rgba(99, 102, 241, 0.15);
  stroke: none;
  pointer-events: none;
}

.poly-edge {
  fill: none;
  stroke: var(--cc-brand);
  stroke-width: 2;
  pointer-events: none;
}

.poly-edge-close {
  stroke: var(--cc-brand);
  stroke-width: 2;
  stroke-dasharray: 5 4;
  pointer-events: none;
}

.vertex-dot {
  fill: var(--cc-brand);
  stroke: white;
  stroke-width: 1.5;
}

.vertex-label {
  fill: var(--cc-brand);
  font-size: 11px;
  font-weight: 600;
  pointer-events: none;
}

/* Zoom controls are rendered by CcZoomControls using global .cc-zoom-controls */
</style>
