<template>
  <div>
    <div
      ref="containerEl"
      class="polygon-container"
      @contextmenu.prevent
    >
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
        :style="`width:${svgW}px;height:${svgH}px`"
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

const props = defineProps({
  imageUrl: { type: String, default: null },
  modelValue: { type: Array, default: () => [] },
  readonly: { type: Boolean, default: false },
  minPoints: { type: Number, default: 3 },
  maxPoints: { type: Number, default: null },
});

const emit = defineEmits(["update:modelValue", "closed", "clear"]);

const imgEl = ref(null);
const svgEl = ref(null);
const svgW = ref(0);
const svgH = ref(0);
const svgReady = computed(() => svgW.value > 0 && svgH.value > 0);
const pts = computed(() => props.modelValue);

let resizeObserver = null;

function syncSize() {
  if (!imgEl.value) return;
  const r = imgEl.value.getBoundingClientRect();
  svgW.value = Math.round(r.width);
  svgH.value = Math.round(r.height);
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

function sx(nx) { return nx * svgW.value; }
function sy(ny) { return ny * svgH.value; }

const svgPtsStr = computed(() =>
  pts.value.map(([x, y]) => `${sx(x)},${sy(y)}`).join(" ")
);

function onSvgClick(e) {
  if (props.readonly) return;
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

// Drag-to-move
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
.polygon-container {
  position: relative;
  display: inline-block;
  width: 100%;
  user-select: none;
}

.polygon-img {
  display: block;
  width: 100%;
  max-height: 420px;
  object-fit: contain;
}

.polygon-empty {
  height: 220px;
  border: 1px dashed var(--cc-divider-strong);
  border-radius: 8px;
  background: var(--cc-surface-2);
}

.polygon-overlay {
  position: absolute;
  top: 0;
  left: 0;
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
</style>
