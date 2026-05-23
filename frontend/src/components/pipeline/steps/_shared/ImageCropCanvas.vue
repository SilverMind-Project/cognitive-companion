<template>
  <div class="crop-canvas-wrapper" :style="{ minHeight: minCanvasHeight + 'px' }">
    <div v-if="!imageLoaded" class="crop-canvas-placeholder d-flex align-center justify-center">
      <div class="text-center text-medium-emphasis">
        <v-icon size="48" color="grey-lighten-1">mdi-image-outline</v-icon>
        <div class="text-body-2 mt-2">Load a sample image to draw regions</div>
      </div>
    </div>
    <canvas
      ref="canvasRef"
      :style="{ display: imageLoaded ? 'block' : 'none', cursor: cursorStyle }"
      @mousedown="onPointerDown"
      @mousemove="onPointerMove"
      @mouseup="onPointerUp"
      @mouseleave="onPointerUp"
      @touchstart.prevent="onTouchStart"
      @touchmove.prevent="onTouchMove"
      @touchend="onPointerUp"
    />
  </div>
</template>

<script setup>
import { ref, watch, computed, onMounted, nextTick } from "vue";

const props = defineProps({
  imageUrl: { type: String, default: "" },
  regions: { type: Array, default: () => [] },
  selectedIndex: { type: Number, default: -1 },
});

const emit = defineEmits(["update:regions", "select-region"]);

const canvasRef = ref(null);
const imageLoaded = ref(false);
const canvasWidth = ref(800);
const minCanvasHeight = ref(200);

// Drawing state
let img = null;
let scaleX = 1;
let scaleY = 1;
let offsetX = 0;
let offsetY = 0;
let dragging = false;
let dragCorner = null;
let dragStartX = 0;
let dragStartY = 0;
let dragRegionIndex = -1;

const cursorStyle = computed(() => {
  if (!imageLoaded.value) return "default";
  if (dragging && dragCorner) return dragCorner.includes("move") ? "move" : "nwse-resize";
  return "crosshair";
});

// Size of handle boxes in CSS pixels
const HANDLE_SIZE = 8;

function loadImage() {
  if (!props.imageUrl) {
    imageLoaded.value = false;
    return;
  }
  img = new Image();
  img.crossOrigin = "anonymous";
  img.onload = () => {
    imageLoaded.value = true;
    nextTick(() => fitToCanvas());
  };
  img.onerror = () => {
    imageLoaded.value = false;
  };
  img.src = props.imageUrl;
}

watch(() => props.imageUrl, loadImage, { immediate: true });

function fitToCanvas() {
  const canvas = canvasRef.value;
  if (!canvas || !img) return;

  const maxWidth = canvas.parentElement ? canvas.parentElement.clientWidth - 16 : 800;
  const ratio = img.naturalWidth / img.naturalHeight;
  canvasWidth.value = Math.min(maxWidth, 800);
  const h = canvasWidth.value / ratio;
  minCanvasHeight.value = Math.max(200, Math.round(h));

  canvas.width = canvasWidth.value;
  canvas.height = Math.round(h);

  scaleX = canvasWidth.value / img.naturalWidth;
  scaleY = canvas.height / img.naturalHeight;
  offsetX = 0;
  offsetY = 0;

  draw();
}

// ---- Coordinate conversion ----

function clientToCanvas(clientX, clientY) {
  const canvas = canvasRef.value;
  if (!canvas) return { x: 0, y: 0 };
  const rect = canvas.getBoundingClientRect();
  return {
    x: (clientX - rect.left) * (canvas.width / rect.width),
    y: (clientY - rect.top) * (canvas.height / rect.height),
  };
}

function canvasToRatio(cx, cy) {
  return {
    x: Math.max(0, Math.min(1, (cx - offsetX) / (img.naturalWidth * scaleX))),
    y: Math.max(0, Math.min(1, (cy - offsetY) / (img.naturalHeight * scaleY))),
  };
}

function ratioToCanvas(rx, ry) {
  return {
    x: offsetX + rx * img.naturalWidth * scaleX,
    y: offsetY + ry * img.naturalHeight * scaleY,
  };
}

// ---- Drawing ----

function draw() {
  const canvas = canvasRef.value;
  if (!canvas || !img) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;

  ctx.clearRect(0, 0, w, h);
  ctx.drawImage(img, offsetX, offsetY, img.naturalWidth * scaleX, img.naturalHeight * scaleY);

  const regions = props.regions || [];
  regions.forEach((r, i) => {
    const tl = ratioToCanvas(r.x, r.y);
    const br = ratioToCanvas(r.x + r.width, r.y + r.height);
    const rw = br.x - tl.x;
    const rh = br.y - tl.y;
    const selected = i === props.selectedIndex;

    // Fill
    ctx.fillStyle = selected ? "rgba(0, 188, 212, 0.15)" : "rgba(255, 255, 255, 0.08)";
    ctx.fillRect(tl.x, tl.y, rw, rh);

    // Border
    ctx.strokeStyle = selected ? "rgb(0, 188, 212)" : "rgba(255, 255, 255, 0.6)";
    ctx.lineWidth = selected ? 2.5 : 1.5;
    ctx.strokeRect(tl.x, tl.y, rw, rh);

    // Label
    const label = r.name || r.id || `Region ${i + 1}`;
    ctx.font = "12px sans-serif";
    const textW = ctx.measureText(label).width;
    const labelY = tl.y - 6 > 16 ? tl.y - 6 : tl.y + 16;
    ctx.fillStyle = selected ? "rgba(0, 188, 212, 0.9)" : "rgba(0, 0, 0, 0.7)";
    ctx.fillRect(tl.x, labelY - 12, textW + 8, 16);
    ctx.fillStyle = "#fff";
    ctx.fillText(label, tl.x + 4, labelY);

    // Handles on selected region
    if (selected) {
      const handles = [
        { x: tl.x, y: tl.y },
        { x: br.x, y: tl.y },
        { x: br.x, y: br.y },
        { x: tl.x, y: br.y },
      ];
      ctx.fillStyle = "rgb(0, 188, 212)";
      handles.forEach((hh) => {
        ctx.fillRect(hh.x - HANDLE_SIZE / 2, hh.y - HANDLE_SIZE / 2, HANDLE_SIZE, HANDLE_SIZE);
      });
    }
  });
}

// ---- Hit testing ----

function hitTest(cx, cy) {
  const regions = props.regions || [];
  for (let i = regions.length - 1; i >= 0; i--) {
    const r = regions[i];
    const tl = ratioToCanvas(r.x, r.y);
    const br = ratioToCanvas(r.x + r.width, r.y + r.height);

    // Check handles first (if selected)
    if (i === props.selectedIndex) {
      const handles = [
        { x: tl.x, y: tl.y, corner: "nw" },
        { x: br.x, y: tl.y, corner: "ne" },
        { x: br.x, y: br.y, corner: "se" },
        { x: tl.x, y: br.y, corner: "sw" },
      ];
      for (const hh of handles) {
        if (Math.abs(cx - hh.x) <= HANDLE_SIZE && Math.abs(cy - hh.y) <= HANDLE_SIZE) {
          return { index: i, corner: hh.corner };
        }
      }
    }

    // Check box interior
    if (cx >= tl.x && cx <= br.x && cy >= tl.y && cy <= br.y) {
      const pad = props.selectedIndex === i ? 6 : 2;
      if (cx >= tl.x + pad && cx <= br.x - pad && cy >= tl.y + pad && cy <= br.y - pad) {
        return { index: i, corner: "move" };
      }
      return { index: i, corner: "move" };
    }
  }
  return null;
}

// ---- Pointer events ----

function onPointerDown(e) {
  if (!imageLoaded.value) return;
  const pos = clientToCanvas(e.clientX, e.clientY);
  const hit = hitTest(pos.x, pos.y);

  if (hit) {
    dragRegionIndex = hit.index;
    dragCorner = hit.corner;
    emit("select-region", hit.index);
  } else {
    // Start drawing a new region
    const ratio = canvasToRatio(pos.x, pos.y);
    const newRegion = {
      id: `region_${Date.now()}`,
      name: `Region ${(props.regions || []).length + 1}`,
      x: ratio.x,
      y: ratio.y,
      width: 0,
      height: 0,
    };
    const updated = [...(props.regions || []), newRegion];
    dragRegionIndex = updated.length - 1;
    dragCorner = "se";
    emit("update:regions", updated);
    emit("select-region", dragRegionIndex);
  }

  dragging = true;
  dragStartX = pos.x;
  dragStartY = pos.y;
}

function onPointerMove(e) {
  if (!dragging || !imageLoaded.value) return;
  const pos = clientToCanvas(e.clientX, e.clientY);
  const dx = pos.x - dragStartX;
  const dy = pos.y - dragStartY;
  dragStartX = pos.x;
  dragStartY = pos.y;

  const regions = [...(props.regions || [])];
  const r = { ...regions[dragRegionIndex] };
  if (!r) return;

  const tl = ratioToCanvas(r.x, r.y);
  const br = ratioToCanvas(r.x + r.width, r.y + r.height);

  let newTl = { x: tl.x, y: tl.y };
  let newBr = { x: br.x, y: br.y };

  switch (dragCorner) {
    case "move":
      newTl.x += dx;
      newTl.y += dy;
      newBr.x += dx;
      newBr.y += dy;
      break;
    case "nw":
      newTl.x += dx;
      newTl.y += dy;
      break;
    case "ne":
      newBr.x += dx;
      newTl.y += dy;
      break;
    case "se":
      newBr.x += dx;
      newBr.y += dy;
      break;
    case "sw":
      newTl.x += dx;
      newBr.y += dy;
      break;
  }

  // Clamp to canvas
  newTl.x = Math.max(0, Math.min(canvasRef.value.width, newTl.x));
  newTl.y = Math.max(0, Math.min(canvasRef.value.height, newTl.y));
  newBr.x = Math.max(0, Math.min(canvasRef.value.width, newBr.x));
  newBr.y = Math.max(0, Math.min(canvasRef.value.height, newBr.y));

  // Convert back to ratios
  const imgW = img.naturalWidth * scaleX;
  const imgH = img.naturalHeight * scaleY;
  r.x = Math.max(0, Math.min(1, (Math.min(newTl.x, newBr.x) - offsetX) / imgW));
  r.y = Math.max(0, Math.min(1, (Math.min(newTl.y, newBr.y) - offsetY) / imgH));
  r.width = Math.abs(newBr.x - newTl.x) / imgW;
  r.height = Math.abs(newBr.y - newTl.y) / imgH;

  regions[dragRegionIndex] = { ...r };
  emit("update:regions", regions);
}

function onPointerUp() {
  if (!dragging) return;
  dragging = false;
  dragCorner = null;
  dragRegionIndex = -1;
}

// ---- Touch events ----

function getTouchPos(e) {
  if (e.touches.length === 0) return null;
  const t = e.touches[0];
  return clientToCanvas(t.clientX, t.clientY);
}

function onTouchStart(e) {
  if (!imageLoaded.value) return;
  const pos = getTouchPos(e);
  if (!pos) return;
  const hit = hitTest(pos.x, pos.y);

  if (hit) {
    dragRegionIndex = hit.index;
    dragCorner = hit.corner;
    emit("select-region", hit.index);
  } else {
    const ratio = canvasToRatio(pos.x, pos.y);
    const newRegion = {
      id: `region_${Date.now()}`,
      name: `Region ${(props.regions || []).length + 1}`,
      x: ratio.x,
      y: ratio.y,
      width: 0,
      height: 0,
    };
    const updated = [...(props.regions || []), newRegion];
    dragRegionIndex = updated.length - 1;
    dragCorner = "se";
    emit("update:regions", updated);
    emit("select-region", dragRegionIndex);
  }

  dragging = true;
  dragStartX = pos.x;
  dragStartY = pos.y;
}

function onTouchMove(e) {
  if (!dragging || !imageLoaded.value) return;
  const pos = getTouchPos(e);
  if (!pos) return;
  const dx = pos.x - dragStartX;
  const dy = pos.y - dragStartY;
  dragStartX = pos.x;
  dragStartY = pos.y;

  const regions = [...(props.regions || [])];
  const r = { ...regions[dragRegionIndex] };
  if (!r) return;

  const tl = ratioToCanvas(r.x, r.y);
  const br = ratioToCanvas(r.x + r.width, r.y + r.height);
  let newTl = { x: tl.x, y: tl.y };
  let newBr = { x: br.x, y: br.y };

  switch (dragCorner) {
    case "move": newTl.x += dx; newTl.y += dy; newBr.x += dx; newBr.y += dy; break;
    case "nw": newTl.x += dx; newTl.y += dy; break;
    case "ne": newBr.x += dx; newTl.y += dy; break;
    case "se": newBr.x += dx; newBr.y += dy; break;
    case "sw": newTl.x += dx; newBr.y += dy; break;
  }

  newTl.x = Math.max(0, Math.min(canvasRef.value.width, newTl.x));
  newTl.y = Math.max(0, Math.min(canvasRef.value.height, newTl.y));
  newBr.x = Math.max(0, Math.min(canvasRef.value.width, newBr.x));
  newBr.y = Math.max(0, Math.min(canvasRef.value.height, newBr.y));

  const imgW = img.naturalWidth * scaleX;
  const imgH = img.naturalHeight * scaleY;
  r.x = Math.max(0, Math.min(1, (Math.min(newTl.x, newBr.x) - offsetX) / imgW));
  r.y = Math.max(0, Math.min(1, (Math.min(newTl.y, newBr.y) - offsetY) / imgH));
  r.width = Math.abs(newBr.x - newTl.x) / imgW;
  r.height = Math.abs(newBr.y - newTl.y) / imgH;

  regions[dragRegionIndex] = { ...r };
  emit("update:regions", regions);
}

// Expose for parent to trigger redraw
defineExpose({ draw });
</script>

<style scoped>
.crop-canvas-wrapper {
  position: relative;
  background: rgba(0, 0, 0, 0.08);
  border-radius: 8px;
  overflow: hidden;
}
.crop-canvas-placeholder {
  min-height: 200px;
  border: 2px dashed rgba(var(--v-theme-on-surface), 0.15);
  border-radius: 8px;
  margin: 8px;
}
canvas {
  max-width: 100%;
  height: auto;
  border-radius: 8px;
}
</style>
