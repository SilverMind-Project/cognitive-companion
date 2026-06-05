<template>
  <div>
    <div
      ref="containerEl"
      class="cc-spatial-editor"
      :style="containerStyle"
      @wheel.prevent="spatial.zoom.actions.onWheel"
      @mousedown="spatial.zoom.actions.startPan"
      @contextmenu.prevent
    >
      <div class="cc-spatial-editor__content" :style="spatial.zoom.state.transformStyle">
        <img
          v-if="imageUrl"
          ref="imgEl"
          :src="imageUrl"
          class="cc-spatial-editor__image"
          :class="imageClass"
          draggable="false"
          alt=""
          @load="syncImageSize"
        />
        <div v-else class="cc-spatial-editor__empty d-flex align-center justify-center">
          <v-icon color="medium-emphasis" size="32">mdi-image-outline</v-icon>
          <span class="text-medium-emphasis text-body-2 ml-2">No image loaded</span>
        </div>

        <svg
          v-if="contentReady"
          ref="svgEl"
          class="cc-spatial-editor__overlay"
          :viewBox="`0 0 ${overlayWidth} ${overlayHeight}`"
          :style="overlayStyle"
          @click.exact="onOverlayClick"
          @mousedown="onOverlayMouseDown"
          @mouseleave="onOverlayMouseLeave"
          @dblclick.stop="onDblClick"
          @touchstart.prevent="onOverlayTouchStart"
          @touchend.prevent="onOverlayTouchEnd"
        >
          <slot
            name="overlay"
            :to-canvas="toCanvas"
            :content-rect="spatial.contentRect.value"
            :zoom="spatial.zoom"
            :is-dragging="isDragging"
          />

          <g
            v-for="(shape, shapeIndex) in internalShapes"
            :key="shape.id ?? shapeIndex"
            class="cc-spatial-editor__shape"
            :class="{ 'cc-spatial-editor__shape--selected': shapeIndex === selectedIndex }"
            @click.stop="selectShape(shapeIndex)"
          >
            <template v-if="(!hideInternalPolygon || isDragging) && shape.type === 'polygon'">
              <polygon
                v-if="shape.points.length >= 3"
                :points="pointsString(shape.points)"
                class="cc-spatial-editor__fill"
                @mousedown.stop="startShapeDrag(shapeIndex, $event)"
              />
              <polyline
                v-if="shape.points.length >= 2"
                :points="pointsString(shape.points)"
                class="cc-spatial-editor__edge"
                @mousedown.stop="startShapeDrag(shapeIndex, $event)"
              />
              <line
                v-if="shape.points.length >= 3"
                :x1="toCanvas(shape.points[shape.points.length - 1]).x"
                :y1="toCanvas(shape.points[shape.points.length - 1]).y"
                :x2="toCanvas(shape.points[0]).x"
                :y2="toCanvas(shape.points[0]).y"
                class="cc-spatial-editor__edge cc-spatial-editor__edge--hint"
              />
            </template>

            <template v-else-if="(!hideInternalPolygon || isDragging) && shape.type === 'line'">
              <line
                v-if="shape.points.length >= 2"
                :x1="toCanvas(shape.points[0]).x"
                :y1="toCanvas(shape.points[0]).y"
                :x2="toCanvas(shape.points[1]).x"
                :y2="toCanvas(shape.points[1]).y"
                class="cc-spatial-editor__edge"
                @mousedown.stop="startShapeDrag(shapeIndex, $event)"
              />
            </template>

            <template v-else-if="(!hideInternalPolygon || isDragging) && shape.type === 'rect'">
              <rect
                :x="rectCanvas(shape).x"
                :y="rectCanvas(shape).y"
                :width="rectCanvas(shape).w"
                :height="rectCanvas(shape).h"
                class="cc-spatial-editor__rect"
                @mousedown.stop="startShapeDrag(shapeIndex, $event)"
              />
            </template>

            <template v-else-if="(!hideInternalPolygon || isDragging) && shape.type === 'point'">
              <circle
                :cx="toCanvas(shape.point).x"
                :cy="toCanvas(shape.point).y"
                r="6"
                class="cc-spatial-editor__point"
                @mousedown.stop="startShapeDrag(shapeIndex, $event)"
              />
            </template>

            <g v-for="handle in handlesForShape(shape, shapeIndex)" :key="handle.key">
              <circle
                :cx="handle.x"
                :cy="handle.y"
                r="12"
                class="cc-spatial-editor__handle-hit"
                @mousedown.stop="startHandleDrag(handle, $event)"
                @touchstart.prevent.stop="startHandleTouchDrag(handle, $event)"
                @contextmenu.prevent.stop="deleteHandle(handle)"
              />
              <circle
                :cx="handle.x"
                :cy="handle.y"
                r="5"
                class="cc-spatial-editor__handle"
              />
              <text
                v-if="showHandleLabels && handle.label"
                v-bind="mapLabelAttrs"
                :x="handle.x + 9"
                :y="handle.y - 5"
                class="cc-spatial-editor__label"
              >{{ handle.label }}</text>
            </g>

            <slot name="shape-label" :shape="toEmitShape(shape)" :index="shapeIndex" />
          </g>

          <slot
            name="overlay-top"
            :to-canvas="toCanvas"
            :content-rect="spatial.contentRect.value"
            :zoom="spatial.zoom"
            :is-dragging="isDragging"
          />
        </svg>
      </div>

      <CcZoomControls
        v-if="showZoom"
        :zoom="spatial.zoom.state.zoom"
        :pan-x="spatial.zoom.state.panX"
        :pan-y="spatial.zoom.state.panY"
        :min-zoom="minZoom"
        :max-zoom="maxZoom"
        :show-fit="true"
        @zoom-in="spatial.zoom.actions.zoomIn(containerEl)"
        @zoom-out="spatial.zoom.actions.zoomOut(containerEl)"
        @reset="spatial.zoom.actions.reset()"
        @fit="spatial.zoom.actions.reset()"
      />
    </div>

    <div v-if="!readonly && showFooter" class="d-flex align-center mt-2">
      <span class="text-caption text-medium-emphasis">
        {{ statusText }}
      </span>
      <v-spacer />
      <v-btn
        v-if="canClose"
        size="small"
        variant="tonal"
        class="mr-2"
        @click="emit('closed', toEmitShape(activeShape))"
      >
        Close polygon
      </v-btn>
      <v-btn
        v-if="internalShapes.length > 0"
        size="small"
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
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { MAP_LABEL } from "@/composables/useAnnotationStyle.js";
import { useSpatialCanvas } from "@/composables/useSpatialCanvas.js";
import CcZoomControls from "@/components/common/CcZoomControls.vue";

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  imageUrl: { type: String, default: null },
  imageClass: { type: String, default: "" },
  mode: { type: String, default: "polygon" },
  coordSpace: { type: String, default: "normalized" },
  naturalWidth: { type: Number, default: 0 },
  naturalHeight: { type: Number, default: 0 },
  mpp: { type: Number, default: null },
  maxShapes: { type: Number, default: null },
  readonly: { type: Boolean, default: false },
  minPoints: { type: Number, default: 3 },
  maxPoints: { type: Number, default: null },
  showZoom: { type: Boolean, default: true },
  showFooter: { type: Boolean, default: true },
  showHandleLabels: { type: Boolean, default: true },
  hideInternalPolygon: { type: Boolean, default: false },
  minZoom: { type: Number, default: 0.2 },
  maxZoom: { type: Number, default: 6 },
});

const emit = defineEmits(["update:modelValue", "select", "create", "closed", "clear", "delete-vertex"]);

const containerEl = ref(null);
const imgEl = ref(null);
const svgEl = ref(null);
const selectedIndex = ref(-1);
const isDragging = ref(false);
const mapLabelAttrs = MAP_LABEL.attrs();
let resizeObserver = null;

const spatial = useSpatialCanvas({
  naturalWidth: props.naturalWidth,
  naturalHeight: props.naturalHeight,
  coordSpace: props.coordSpace,
  mpp: props.mpp,
  zoomOptions: { minZoom: props.minZoom, maxZoom: props.maxZoom },
});

// Geometry is normalized internally so every consumer crosses the coordinate
// boundary once. This is the guardrail for the M2b door-zone coordinate bug.
const internalShapes = computed(() =>
  props.modelValue.map((shape, index) => normalizeShape(spatial.fromEmit(shape, props.coordSpace), index))
);

const contentReady = computed(() => spatial.contentRect.value.width > 0 && spatial.contentRect.value.height > 0);
const overlayWidth = computed(() => spatial.contentRect.value.width);
const overlayHeight = computed(() => spatial.contentRect.value.height);
const activeShape = computed(() => internalShapes.value[selectedIndex.value] ?? internalShapes.value[0] ?? null);
const canClose = computed(() =>
  props.mode === "polygon" && activeShape.value?.points?.length >= props.minPoints
);

const statusText = computed(() => {
  if (props.mode === "polygon") {
    const count = activeShape.value?.points?.length ?? 0;
    if (props.minPoints && count < props.minPoints) {
      return `${count} ${count === 1 ? "point" : "points"} - ${props.minPoints - count} more needed`;
    }
    return `${count} ${count === 1 ? "point" : "points"}`;
  }
  return `${internalShapes.value.length} ${internalShapes.value.length === 1 ? "shape" : "shapes"}`;
});

const containerStyle = computed(() => {
  if (props.naturalWidth > 0 && props.naturalHeight > 0) {
    return { aspectRatio: `${props.naturalWidth}/${props.naturalHeight}` };
  }
  return {};
});

const overlayStyle = computed(() => ({
  width: `${spatial.contentRect.value.width}px`,
  height: `${spatial.contentRect.value.height}px`,
  left: `${spatial.contentRect.value.offsetX}px`,
  top: `${spatial.contentRect.value.offsetY}px`,
}));

function normalizeShape(shape, index) {
  const type = shape.type ?? props.mode;
  const id = shape.id ?? `shape-${index}`;
  if (type === "rect") {
    return {
      ...shape,
      id,
      type,
      x: shape.x ?? 0,
      y: shape.y ?? 0,
      w: shape.w ?? 0,
      h: shape.h ?? 0,
    };
  }
  if (type === "point") {
    return { ...shape, id, type, point: shape.point ?? [0, 0] };
  }
  return { ...shape, id, type, points: shape.points ?? [] };
}

function syncImageSize() {
  if (imgEl.value) {
    spatial.actions.syncFromImageElement(imgEl.value);
    return;
  }
  if (props.naturalWidth > 0 && props.naturalHeight > 0 && containerEl.value) {
    const rect = containerEl.value.getBoundingClientRect();
    spatial.actions.setViewport({
      width: rect.width,
      height: rect.height,
      imageNaturalWidth: props.naturalWidth,
      imageNaturalHeight: props.naturalHeight,
    });
  }
}

function syncAfterLayout() {
  nextTick(syncImageSize);
}

onMounted(() => {
  syncAfterLayout();
  if (typeof ResizeObserver !== "undefined") {
    resizeObserver = new ResizeObserver(syncImageSize);
    if (imgEl.value) resizeObserver.observe(imgEl.value);
    if (containerEl.value) resizeObserver.observe(containerEl.value);
  }
});

watch(imgEl, (el) => {
  if (resizeObserver && el) resizeObserver.observe(el);
  syncAfterLayout();
});

watch(() => [props.naturalWidth, props.naturalHeight, props.imageUrl], syncAfterLayout);

function toCanvas(point) {
  return spatial.fromNormalized(point, "content");
}

function pointFromEvent(e) {
  const rect = containerEl.value.getBoundingClientRect();
  return spatial.toNormalized({
    x: e.clientX - rect.left,
    y: e.clientY - rect.top,
  });
}

function pointFromTouch(e) {
  const touch = e.changedTouches?.[0] ?? e.touches?.[0];
  if (!touch) return null;
  return pointFromEvent(touch);
}

function toEmitShape(shape) {
  return spatial.toEmit(shape, props.coordSpace);
}

function emitShapes(shapes) {
  emit("update:modelValue", shapes.map((shape) => toEmitShape(shape)));
}

function selectShape(index) {
  selectedIndex.value = index;
  emit("select", toEmitShape(internalShapes.value[index]), index);
}

function hasShapeCapacity() {
  return props.maxShapes == null || internalShapes.value.length < props.maxShapes;
}

function nextShapeId() {
  return `shape-${Date.now()}-${internalShapes.value.length}`;
}

function createShapeAt(point) {
  if (!hasShapeCapacity()) return null;
  let shape;
  if (props.mode === "point") {
    shape = { id: nextShapeId(), type: "point", point };
  } else {
    shape = { id: nextShapeId(), type: props.mode, points: [point] };
  }
  const shapes = [...internalShapes.value, shape];
  selectedIndex.value = shapes.length - 1;
  emitShapes(shapes);
  emit("create", toEmitShape(shape));
  return shape;
}

function onOverlayClick(e) {
  if (props.readonly || !contentReady.value) return;
  if (spatial.zoom.state.didPan) {
    spatial.zoom.state.didPan = false;
    return;
  }
  if (e.detail >= 2) return;
  addPoint(pointFromEvent(e));
}

function onOverlayMouseDown(e) {
  if (props.mode !== "rect" || props.readonly || !contentReady.value || e.button !== 0) return;
  e.stopPropagation();
  const start = pointFromEvent(e);
  const shape = { id: nextShapeId(), type: "rect", x: start[0], y: start[1], w: 0, h: 0 };
  const baseShapes = hasShapeCapacity() ? [...internalShapes.value, shape] : internalShapes.value;
  if (baseShapes === internalShapes.value) return;
  selectedIndex.value = baseShapes.length - 1;
  let latestShape = shape;

  function move(moveEvent) {
    const next = pointFromEvent(moveEvent);
    const rectShape = {
      ...shape,
      x: Math.min(start[0], next[0]),
      y: Math.min(start[1], next[1]),
      w: Math.abs(next[0] - start[0]),
      h: Math.abs(next[1] - start[1]),
    };
    latestShape = rectShape;
    emitShapes([...baseShapes.slice(0, -1), rectShape]);
  }
  function stop() {
    window.removeEventListener("mousemove", move);
    window.removeEventListener("mouseup", stop);
    emit("create", toEmitShape(latestShape));
  }
  window.addEventListener("mousemove", move);
  window.addEventListener("mouseup", stop);
}

function addPoint(point) {
  if (!point) return;
  if (props.mode === "point") {
    createShapeAt(point);
    return;
  }
  if (props.mode === "rect") return;

  const shapes = internalShapes.value.slice();
  let index = selectedIndex.value >= 0 ? selectedIndex.value : shapes.length - 1;
  let shape = shapes[index];

  if (!shape || shape.type !== props.mode) {
    shape = createShapeAt(point);
    return;
  }
  if (props.maxPoints != null && shape.points.length >= props.maxPoints) return;
  if (props.mode === "line" && shape.points.length >= 2) {
    if (!hasShapeCapacity()) return;
    createShapeAt(point);
    return;
  }

  shape = { ...shape, points: [...shape.points, point] };
  shapes[index] = shape;
  emitShapes(shapes);
}

function onDblClick() {
  if (canClose.value) emit("closed", toEmitShape(activeShape.value));
}

function onOverlayTouchStart(e) {
  if (props.readonly || e.touches.length !== 1) return;
  touchStartPoint = pointFromTouch(e);
}

let touchStartPoint = null;
function onOverlayTouchEnd(e) {
  if (props.readonly || !touchStartPoint) return;
  const endPoint = pointFromTouch(e);
  if (!endPoint) return;
  const moved = Math.abs(touchStartPoint[0] - endPoint[0]) + Math.abs(touchStartPoint[1] - endPoint[1]);
  if (moved < 0.01) addPoint(endPoint);
  touchStartPoint = null;
}

function pointsString(points) {
  return points.map((point) => {
    const canvas = toCanvas(point);
    return `${canvas.x},${canvas.y}`;
  }).join(" ");
}

function rectCanvas(shape) {
  const p1 = toCanvas([shape.x, shape.y]);
  const p2 = toCanvas([shape.x + shape.w, shape.y + shape.h]);
  return {
    x: Math.min(p1.x, p2.x),
    y: Math.min(p1.y, p2.y),
    w: Math.abs(p2.x - p1.x),
    h: Math.abs(p2.y - p1.y),
  };
}

function handlesForShape(shape, shapeIndex) {
  if (shape.type === "rect") {
    const points = [
      { key: `${shapeIndex}-nw`, corner: "nw", point: [shape.x, shape.y] },
      { key: `${shapeIndex}-ne`, corner: "ne", point: [shape.x + shape.w, shape.y] },
      { key: `${shapeIndex}-se`, corner: "se", point: [shape.x + shape.w, shape.y + shape.h] },
      { key: `${shapeIndex}-sw`, corner: "sw", point: [shape.x, shape.y + shape.h] },
    ];
    return points.map((handle) => ({ ...handle, ...toCanvas(handle.point), shapeIndex, label: "" }));
  }
  if (shape.type === "point") {
    return [{ key: `${shapeIndex}-point`, pointIndex: 0, shapeIndex, label: "", ...toCanvas(shape.point) }];
  }
  return (shape.points ?? []).map((point, pointIndex) => ({
    key: `${shapeIndex}-${pointIndex}`,
    pointIndex,
    shapeIndex,
    label: String(pointIndex + 1),
    ...toCanvas(point),
  }));
}

function updateShape(shapeIndex, updater) {
  const shapes = internalShapes.value.slice();
  shapes[shapeIndex] = updater(shapes[shapeIndex]);
  emitShapes(shapes);
}

let dragState = null;

function startHandleDrag(handle, e) {
  if (props.readonly) return;
  selectedIndex.value = handle.shapeIndex;
  isDragging.value = true;
  dragState = { kind: "handle", handle };
  window.addEventListener("mousemove", onDragMove);
  window.addEventListener("mouseup", stopDrag);
  e.preventDefault();
}

function startHandleTouchDrag(handle, e) {
  if (props.readonly) return;
  selectedIndex.value = handle.shapeIndex;
  isDragging.value = true;
  dragState = { kind: "handle", handle, touch: true };
  window.addEventListener("touchmove", onDragMove, { passive: false });
  window.addEventListener("touchend", stopDrag);
  e.preventDefault();
}

function startShapeDrag(shapeIndex, e) {
  if (props.readonly) return;
  selectedIndex.value = shapeIndex;
  dragState = {
    kind: "shape",
    shapeIndex,
    start: pointFromEvent(e),
    shape: internalShapes.value[shapeIndex],
  };
  window.addEventListener("mousemove", onDragMove);
  window.addEventListener("mouseup", stopDrag);
  e.preventDefault();
}

function onOverlayMouseLeave() {
  if (dragState?.kind === "handle") stopDrag();
}

function onDragMove(e) {
  if (!dragState) return;
  if (e.cancelable) e.preventDefault();
  const point = "changedTouches" in e || "touches" in e ? pointFromTouch(e) : pointFromEvent(e);
  if (!point) return;

  if (dragState.kind === "handle") {
    const { handle } = dragState;
    updateShape(handle.shapeIndex, (shape) => moveHandle(shape, handle, point));
    return;
  }

  const dx = point[0] - dragState.start[0];
  const dy = point[1] - dragState.start[1];
  updateShape(dragState.shapeIndex, () => translateShape(dragState.shape, dx, dy));
}

function moveHandle(shape, handle, point) {
  if (shape.type === "point") return { ...shape, point };
  if (shape.type === "rect") {
    const right = shape.x + shape.w;
    const bottom = shape.y + shape.h;
    const corners = {
      nw: [point[0], point[1], right, bottom],
      ne: [shape.x, point[1], point[0], bottom],
      se: [shape.x, shape.y, point[0], point[1]],
      sw: [point[0], shape.y, right, point[1]],
    };
    const [x1, y1, x2, y2] = corners[handle.corner];
    return { ...shape, x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1), h: Math.abs(y2 - y1) };
  }
  return {
    ...shape,
    points: shape.points.map((existing, index) => (index === handle.pointIndex ? point : existing)),
  };
}

function translatePoint(point, dx, dy) {
  return [
    Math.max(0, Math.min(1, point[0] + dx)),
    Math.max(0, Math.min(1, point[1] + dy)),
  ];
}

function translateShape(shape, dx, dy) {
  if (shape.type === "point") return { ...shape, point: translatePoint(shape.point, dx, dy) };
  if (shape.type === "rect") return { ...shape, x: translatePoint([shape.x, shape.y], dx, dy)[0], y: translatePoint([shape.x, shape.y], dx, dy)[1] };
  return { ...shape, points: shape.points.map((point) => translatePoint(point, dx, dy)) };
}

function stopDrag() {
  dragState = null;
  isDragging.value = false;
  window.removeEventListener("mousemove", onDragMove);
  window.removeEventListener("mouseup", stopDrag);
  window.removeEventListener("touchmove", onDragMove);
  window.removeEventListener("touchend", stopDrag);
}

function deleteHandle(handle) {
  if (props.readonly) return;
  const shape = internalShapes.value[handle.shapeIndex];
  if (!shape) return;
  if (shape.type === "point") {
    emitShapes(internalShapes.value.filter((_, index) => index !== handle.shapeIndex));
    return;
  }
  if (shape.type === "rect") return;
  const nextPoints = shape.points.filter((_, index) => index !== handle.pointIndex);
  updateShape(handle.shapeIndex, (existing) => ({ ...existing, points: nextPoints }));
  emit("delete-vertex", { shape: toEmitShape(shape), shapeIndex: handle.shapeIndex, pointIndex: handle.pointIndex });
}

function clearAll() {
  selectedIndex.value = -1;
  emit("update:modelValue", []);
  emit("clear");
}

onBeforeUnmount(() => {
  if (resizeObserver) resizeObserver.disconnect();
  stopDrag();
});
</script>

<style scoped>
.cc-spatial-editor {
  position: relative;
  overflow: hidden;
  min-height: 320px;
  max-height: min(640px, 72vh);
  background: var(--cc-surface-2);
  border: 1px solid var(--cc-divider-strong);
  border-radius: 8px;
}

.cc-spatial-editor__content {
  position: relative;
  display: inline-block;
  min-width: 100%;
  will-change: transform;
}

.cc-spatial-editor__image {
  display: block;
  width: 100%;
  max-height: min(640px, 72vh);
  object-fit: contain;
}

.cc-spatial-editor__empty {
  height: 320px;
  border: 1px dashed var(--cc-divider-strong);
  border-radius: 8px;
  background: var(--cc-surface-2);
}

.cc-spatial-editor__overlay {
  position: absolute;
  cursor: crosshair;
  pointer-events: all;
  touch-action: none;
}

.cc-spatial-editor__fill,
.cc-spatial-editor__rect {
  fill: color-mix(in srgb, var(--cc-brand) 16%, transparent);
  stroke: var(--cc-brand);
  stroke-width: 2;
}

.cc-spatial-editor__edge {
  fill: none;
  stroke: var(--cc-brand);
  stroke-width: 2;
}

.cc-spatial-editor__edge--hint {
  stroke-dasharray: 5 4;
  pointer-events: none;
}

.cc-spatial-editor__point,
.cc-spatial-editor__handle {
  fill: var(--cc-brand);
  stroke: var(--cc-bg-elevated);
  stroke-width: 1.5;
}

.cc-spatial-editor__handle-hit {
  fill: transparent;
  cursor: grab;
}

.cc-spatial-editor__label {
  font-size: 11px;
  font-weight: 500;
  pointer-events: none;
}

.cc-spatial-editor__shape--selected .cc-spatial-editor__edge,
.cc-spatial-editor__shape--selected .cc-spatial-editor__fill,
.cc-spatial-editor__shape--selected .cc-spatial-editor__rect {
  stroke: var(--cc-warning);
}
</style>
