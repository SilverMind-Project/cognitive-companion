<template>
  <div ref="wrapper" class="bbox-canvas-wrapper">
    <canvas
      ref="canvas"
      :width="canvasWidth"
      :height="canvasHeight"
      style="border: 1px solid #ccc; cursor: crosshair; display: block; max-width: 100%"
      @mousedown="onMouseDown"
      @mousemove="onMouseMove"
      @mouseup="onMouseUp"
    />
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted, nextTick } from "vue";

const props = defineProps({
  imageUrl: { type: String, default: "" },
  regions: { type: Array, default: () => [] },
  selectedIndex: { type: Number, default: -1 },
  templateWidth: { type: Number, default: 800 },
  templateHeight: { type: Number, default: 480 },
});

const emit = defineEmits(["update:regions", "select-region"]);

const canvas = ref(null);
const wrapper = ref(null);
const canvasWidth = ref(800);
const canvasHeight = ref(480);

let bgImage = null;
let drawing = false;
let dragging = false;
let dragStartX = 0;
let dragStartY = 0;
let newRect = null;
let scale = 1;

function toCanvas(val) {
  return val * scale;
}

function toTemplate(val) {
  return Math.round(val / scale);
}

function draw() {
  const ctx = canvas.value?.getContext("2d");
  if (!ctx) return;

  ctx.clearRect(0, 0, canvasWidth.value, canvasHeight.value);

  // Draw background image
  if (bgImage) {
    ctx.drawImage(bgImage, 0, 0, canvasWidth.value, canvasHeight.value);
  } else {
    ctx.fillStyle = "#1e1e1e";
    ctx.fillRect(0, 0, canvasWidth.value, canvasHeight.value);
  }

  // Draw regions
  props.regions.forEach((r, i) => {
    const x = toCanvas(r.x);
    const y = toCanvas(r.y);
    const w = toCanvas(r.width);
    const h = toCanvas(r.height);

    const isSelected = i === props.selectedIndex;

    // Draw region background fill (mirrors actual rendered appearance)
    const bg = r.bg_color || [0, 0, 0, 160];
    if (bg[3] > 0) {
      ctx.fillStyle = `rgba(${bg[0]},${bg[1]},${bg[2]},${bg[3] / 255})`;
      ctx.fillRect(x, y, w, h);
    }

    // Draw border
    ctx.strokeStyle = isSelected ? "#2196F3" : "#4CAF50";
    ctx.lineWidth = isSelected ? 3 : 2;
    ctx.setLineDash(isSelected ? [] : [6, 3]);
    ctx.strokeRect(x, y, w, h);
    ctx.setLineDash([]);

    // Label badge
    const label = r.name || `Region ${i}`;
    ctx.font = "12px sans-serif";
    const badgeColor = isSelected ? "#2196F3" : "#4CAF50";
    ctx.fillStyle = badgeColor;
    const textWidth = ctx.measureText(label).width;
    ctx.fillRect(x, y - 18, textWidth + 8, 18);
    ctx.fillStyle = "#fff";
    ctx.fillText(label, x + 4, y - 5);
  });

  // Draw new rect being drawn
  if (newRect) {
    ctx.strokeStyle = "#FF9800";
    ctx.lineWidth = 2;
    ctx.setLineDash([4, 4]);
    ctx.strokeRect(newRect.x, newRect.y, newRect.w, newRect.h);
    ctx.setLineDash([]);
  }
}

function loadImage() {
  if (!props.imageUrl) {
    bgImage = null;
    draw();
    return;
  }
  const img = new Image();
  img.crossOrigin = "anonymous";
  img.onload = () => {
    bgImage = img;
    draw();
  };
  img.src = props.imageUrl;
}

function getMousePos(e) {
  const rect = canvas.value.getBoundingClientRect();
  const scaleX = canvasWidth.value / rect.width;
  const scaleY = canvasHeight.value / rect.height;
  return {
    x: (e.clientX - rect.left) * scaleX,
    y: (e.clientY - rect.top) * scaleY,
  };
}

function hitTest(pos) {
  for (let i = props.regions.length - 1; i >= 0; i--) {
    const r = props.regions[i];
    const x = toCanvas(r.x);
    const y = toCanvas(r.y);
    const w = toCanvas(r.width);
    const h = toCanvas(r.height);
    if (pos.x >= x && pos.x <= x + w && pos.y >= y && pos.y <= y + h) {
      return i;
    }
  }
  return -1;
}

function onMouseDown(e) {
  const pos = getMousePos(e);
  const hit = hitTest(pos);

  if (hit >= 0) {
    emit("select-region", hit);
    dragging = true;
    dragStartX = pos.x - toCanvas(props.regions[hit].x);
    dragStartY = pos.y - toCanvas(props.regions[hit].y);
  } else {
    drawing = true;
    dragStartX = pos.x;
    dragStartY = pos.y;
    newRect = { x: pos.x, y: pos.y, w: 0, h: 0 };
  }
}

function onMouseMove(e) {
  const pos = getMousePos(e);

  if (drawing && newRect) {
    newRect.w = pos.x - dragStartX;
    newRect.h = pos.y - dragStartY;
    draw();
  } else if (dragging && props.selectedIndex >= 0) {
    const updated = [...props.regions];
    const r = { ...updated[props.selectedIndex] };
    r.x = toTemplate(pos.x - dragStartX);
    r.y = toTemplate(pos.y - dragStartY);
    // Clamp to bounds
    r.x = Math.max(0, Math.min(r.x, props.templateWidth - r.width));
    r.y = Math.max(0, Math.min(r.y, props.templateHeight - r.height));
    updated[props.selectedIndex] = r;
    emit("update:regions", updated);
  }
}

function onMouseUp() {
  if (drawing && newRect) {
    const x = Math.min(dragStartX, dragStartX + newRect.w);
    const y = Math.min(dragStartY, dragStartY + newRect.h);
    const w = Math.abs(newRect.w);
    const h = Math.abs(newRect.h);

    if (w > 10 && h > 10) {
      const region = {
        name: `region_${props.regions.length}`,
        x: toTemplate(x),
        y: toTemplate(y),
        width: toTemplate(w),
        height: toTemplate(h),
        font_size_max: 48,
        font_size_min: 12,
        align: "center",
        bg_color: [0, 0, 0, 160],
        text_color: [255, 255, 255, 255],
        multiline: true,
      };
      emit("update:regions", [...props.regions, region]);
      emit("select-region", props.regions.length);
    }
    newRect = null;
  }
  drawing = false;
  dragging = false;
  draw();
}

function updateCanvasSize() {
  if (!wrapper.value) return;
  const wrapperWidth = wrapper.value.clientWidth;
  scale = Math.min(1, wrapperWidth / props.templateWidth);
  canvasWidth.value = Math.round(props.templateWidth * scale);
  canvasHeight.value = Math.round(props.templateHeight * scale);
  nextTick(draw);
}

watch(() => props.imageUrl, loadImage);
watch(() => props.regions, draw, { deep: true });
watch(() => props.selectedIndex, draw);

// Called by the parent (EInkTemplatesView) when the Regions tab is activated.
// The wrapper has zero width while the tab is hidden, so we must re-measure
// and redraw once it becomes visible.
function activate() {
  nextTick(() => {
    updateCanvasSize();
    loadImage();
  });
}

defineExpose({ activate });

let resizeObserver = null;

onMounted(() => {
  // ResizeObserver fires whenever the wrapper's size changes, including the
  // first time it becomes visible after being hidden inside a v-window-item.
  if (wrapper.value && typeof ResizeObserver !== "undefined") {
    resizeObserver = new ResizeObserver(() => {
      if (wrapper.value && wrapper.value.clientWidth > 0) {
        updateCanvasSize();
      }
    });
    resizeObserver.observe(wrapper.value);
  }

  updateCanvasSize();
  loadImage();
});

onUnmounted(() => {
  if (resizeObserver) {
    resizeObserver.disconnect();
    resizeObserver = null;
  }
});
</script>

<style scoped>
.bbox-canvas-wrapper {
  width: 100%;
}
</style>
