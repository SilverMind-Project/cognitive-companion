<template>
  <div ref="wrapperRef" class="bbox-canvas-wrapper">
    <img
      :src="imageUrl"
      class="keyframe-image"
      @load="onImageLoad"
      draggable="false"
    />
    <canvas
      ref="canvasRef"
      class="bbox-overlay"
      @mousedown="onMouseDown"
      @mousemove="onMouseMove"
      @mouseup="onMouseUp"
      @mouseleave="onMouseUp"
    />
    <!-- Ink overlay for committed boxes in marauders mode.
         pointer-events: none so mouse events pass through to the canvas. -->
    <svg
      v-if="maraudersMode && imageNaturalWidth > 0"
      class="bbox-ink-overlay"
      :viewBox="`0 0 ${imageNaturalWidth} ${imageNaturalHeight}`"
    >
      <MaraudersInkBox
        v-for="box in boxes"
        :key="box.annotationId ?? `${box.x1}-${box.y1}`"
        :x="box.x1"
        :y="box.y1"
        :w="box.x2 - box.x1"
        :h="box.y2 - box.y1"
        :seed-key="String(box.annotationId ?? box.x1)"
      />
    </svg>
    <Teleport to="body">
      <BboxTagPopover
        v-if="selectedBox && popoverPosition"
        :position="popoverPosition"
        :identities="identities"
        @tag="onTag"
        @delete="onDeleteBox"
        @close="selectedBox = null"
      />
    </Teleport>
  </div>
</template>

<script setup>
import { ref, reactive, watch } from "vue";
import BboxTagPopover from "./BboxTagPopover.vue";
import MaraudersInkBox from "@/components/marauders/MaraudersInkBox.vue";

const props = defineProps({
  imageUrl: { type: String, required: true },
  keyframeId: { type: String, required: true },
  initialBboxes: { type: Array, default: () => [] },
  identities: { type: Array, default: () => [] },
  readonly: { type: Boolean, default: false },
  maraudersMode: { type: Boolean, default: false },
});

const emit = defineEmits([
  "bbox-tagged",     // { annotationId, identityId, reason }
  "bbox-overridden", // { annotationId, x1, y1, x2, y2 }
  "bbox-created",    // { x1, y1, x2, y2 }
  "bbox-deleted",    // { annotationId }
]);

const canvasRef = ref(null);
const wrapperRef = ref(null);
const imageNaturalWidth = ref(0);
const imageNaturalHeight = ref(0);
const canvasRect = ref(null);
const selectedBox = ref(null);
const popoverPosition = ref(null);

// boxes: [{ annotationId, x1, y1, x2, y2, identityId, identityLabel, isOverride, isNew }]
const boxes = ref([]);

// drawState: null | { startX, startY, currentX, currentY } (in canvas space)
const drawState = ref(null);

// resizeState: null | { box, corner, startX, startY } (corner: "tl"|"tr"|"bl"|"br")
const resizeState = ref(null);

const HANDLE_SIZE = 8;

// -- Coordinate conversion ---------------------------------------------------

function toCanvas(xOrig, yOrig) {
  const cw = canvasRef.value?.width || 1;
  const ch = canvasRef.value?.height || 1;
  const iw = imageNaturalWidth.value || cw;
  const ih = imageNaturalHeight.value || ch;
  return { x: (xOrig / iw) * cw, y: (yOrig / ih) * ch };
}

function toOrig(xCanvas, yCanvas) {
  const cw = canvasRef.value?.width || 1;
  const ch = canvasRef.value?.height || 1;
  const iw = imageNaturalWidth.value || cw;
  const ih = imageNaturalHeight.value || ch;
  return { x: (xCanvas / cw) * iw, y: (yCanvas / ch) * ih };
}

// -- Image load ---------------------------------------------------------------

function onImageLoad(event) {
  const img = event.target;
  imageNaturalWidth.value = img.naturalWidth;
  imageNaturalHeight.value = img.naturalHeight;

  // Size canvas to match the displayed image dimensions
  const canvas = canvasRef.value;
  if (canvas) {
    canvas.width = img.clientWidth;
    canvas.height = img.clientHeight;
  }
  syncBoxesFromProps();
  render();
}

// -- Box management -----------------------------------------------------------

function syncBoxesFromProps() {
  boxes.value = (props.initialBboxes || []).map((b) => {
    // Use override coords if present, otherwise YOLO coords
    const hasOverride = b.override_x1 != null && b.override_y1 != null
      && b.override_x2 != null && b.override_y2 != null;
    const identityLabel = lookupIdentityLabel(b.identity_id);
    return {
      annotationId: b.id,
      x1: hasOverride ? b.override_x1 : b.x1,
      y1: hasOverride ? b.override_y1 : b.y1,
      x2: hasOverride ? b.override_x2 : b.x2,
      y2: hasOverride ? b.override_y2 : b.y2,
      identityId: b.identity_id,
      identityLabel,
      isOverride: hasOverride,
      isNew: b.isNew || false,
    };
  });
}

function lookupIdentityLabel(identityId) {
  if (!identityId) return null;
  const found = props.identities.find(
    (id) => id.id === identityId || id.identity_id === identityId
  );
  return found ? (found.display_name || found.name || identityId) : identityId;
}

// -- Canvas rendering ---------------------------------------------------------

function render() {
  const canvas = canvasRef.value;
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  for (const box of boxes.value) {
    // In marauders mode, committed boxes are rendered by the SVG ink overlay.
    // Only draw the selected/active box on canvas so drag handles stay precise.
    if (props.maraudersMode && box !== selectedBox.value) continue;

    const { x: cx1, y: cy1 } = toCanvas(box.x1, box.y1);
    const { x: cx2, y: cy2 } = toCanvas(box.x2, box.y2);
    const w = cx2 - cx1;
    const h = cy2 - cy1;

    // Stroke color
    if (box === selectedBox.value) {
      ctx.strokeStyle = "#FFD700";
    } else if (box.isNew) {
      ctx.strokeStyle = "#00E5FF";
    } else {
      ctx.strokeStyle = "#4CAF50";
    }
    ctx.lineWidth = 2;
    ctx.strokeRect(cx1, cy1, w, h);

    // Identity label
    if (box.identityLabel) {
      ctx.font = "12px Inter, sans-serif";
      const textWidth = ctx.measureText(box.identityLabel).width;
      ctx.fillStyle = "rgba(0,0,0,0.55)";
      ctx.fillRect(cx1, cy1 - 20, textWidth + 8, 20);
      ctx.fillStyle = "#FFFFFF";
      ctx.fillText(box.identityLabel, cx1 + 4, cy1 - 5);
    }

    // Corner handles for selected box
    if (box === selectedBox.value) {
      drawHandle(ctx, cx1, cy1);
      drawHandle(ctx, cx2 - HANDLE_SIZE, cy1);
      drawHandle(ctx, cx1, cy2 - HANDLE_SIZE);
      drawHandle(ctx, cx2 - HANDLE_SIZE, cy2 - HANDLE_SIZE);
    }
  }

  // Drawing preview
  if (drawState.value) {
    const { startX, startY, currentX, currentY } = drawState.value;
    const x = Math.min(startX, currentX);
    const y = Math.min(startY, currentY);
    const w = Math.abs(currentX - startX);
    const h = Math.abs(currentY - startY);
    ctx.strokeStyle = "#00E5FF";
    ctx.lineWidth = 2;
    ctx.setLineDash([6, 3]);
    ctx.strokeRect(x, y, w, h);
    ctx.setLineDash([]);
  }
}

function drawHandle(ctx, x, y) {
  ctx.fillStyle = "#FFD700";
  ctx.fillRect(x, y, HANDLE_SIZE, HANDLE_SIZE);
  ctx.strokeStyle = "#000";
  ctx.lineWidth = 1;
  ctx.strokeRect(x, y, HANDLE_SIZE, HANDLE_SIZE);
}

// -- Mouse events -------------------------------------------------------------

function getCanvasPos(event) {
  const rect = canvasRef.value.getBoundingClientRect();
  return { x: event.clientX - rect.left, y: event.clientY - rect.top };
}

function findBoxAt(cx, cy) {
  // Search in reverse so topmost (last-drawn) box is picked first
  for (let i = boxes.value.length - 1; i >= 0; i--) {
    const box = boxes.value[i];
    const { x: bx1, y: by1 } = toCanvas(box.x1, box.y1);
    const { x: bx2, y: by2 } = toCanvas(box.x2, box.y2);
    if (cx >= bx1 && cx <= bx2 && cy >= by1 && cy <= by2) {
      return box;
    }
  }
  return null;
}

function findHandleAt(cx, cy) {
  if (!selectedBox.value) return null;
  const box = selectedBox.value;
  const { x: bx1, y: by1 } = toCanvas(box.x1, box.y1);
  const { x: bx2, y: by2 } = toCanvas(box.x2, box.y2);

  const handles = {
    tl: { x: bx1, y: by1 },
    tr: { x: bx2 - HANDLE_SIZE, y: by1 },
    bl: { x: bx1, y: by2 - HANDLE_SIZE },
    br: { x: bx2 - HANDLE_SIZE, y: by2 - HANDLE_SIZE },
  };

  for (const [corner, pos] of Object.entries(handles)) {
    if (cx >= pos.x && cx <= pos.x + HANDLE_SIZE
      && cy >= pos.y && cy <= pos.y + HANDLE_SIZE) {
      return corner;
    }
  }
  return null;
}

function updatePopoverPosition(box) {
  if (!box || !wrapperRef.value) {
    popoverPosition.value = null;
    return;
  }
  const { x: cx2, y: cy1 } = toCanvas(box.x2, box.y1);
  const { x: cx1 } = toCanvas(box.x1, box.y1);

  const wrapperRect = wrapperRef.value.getBoundingClientRect();
  const popoverWidth = 308; // 300px card + 8px gap
  const gap = 8;

  // Convert to viewport coordinates (popover card is absolute within position:fixed backdrop)
  let left = wrapperRect.left + cx2 + gap;
  const top = wrapperRect.top + cy1;

  // Flip to the left of the bbox when popover would overflow the right edge
  if (left + popoverWidth > window.innerWidth - gap) {
    left = Math.max(gap, wrapperRect.left + cx1 - popoverWidth);
  }

  popoverPosition.value = { top, left };
}

function onMouseDown(event) {
  if (props.readonly) return;
  canvasRect.value = canvasRef.value.getBoundingClientRect();
  const pos = getCanvasPos(event);

  // Check corner handles of selected box first
  const handle = findHandleAt(pos.x, pos.y);
  if (handle && selectedBox.value) {
    resizeState.value = {
      box: selectedBox.value,
      corner: handle,
      startX: pos.x,
      startY: pos.y,
    };
    return;
  }

  // Check if clicking inside an existing box
  const box = findBoxAt(pos.x, pos.y);
  if (box) {
    selectedBox.value = box;
    updatePopoverPosition(box);
    render();
    return;
  }

  // Start drawing a new box
  selectedBox.value = null;
  popoverPosition.value = null;
  drawState.value = { startX: pos.x, startY: pos.y, currentX: pos.x, currentY: pos.y };
  render();
}

function onMouseMove(event) {
  const pos = getCanvasPos(event);

  if (resizeState.value) {
    const { box, corner, startX, startY } = resizeState.value;
    const dx = pos.x - startX;
    const dy = pos.y - startY;

    const orig = toOrig(1, 1);
    const orig0 = toOrig(0, 0);
    const pxInOrig = orig.x - orig0.x;

    if (corner === "tl") {
      box.x1 += dx * pxInOrig;
      box.y1 += dy * pxInOrig;
    } else if (corner === "tr") {
      box.x2 += dx * pxInOrig;
      box.y1 += dy * pxInOrig;
    } else if (corner === "bl") {
      box.x1 += dx * pxInOrig;
      box.y2 += dy * pxInOrig;
    } else if (corner === "br") {
      box.x2 += dx * pxInOrig;
      box.y2 += dy * pxInOrig;
    }

    resizeState.value.startX = pos.x;
    resizeState.value.startY = pos.y;
    updatePopoverPosition(box);
    render();
    return;
  }

  if (drawState.value) {
    drawState.value.currentX = pos.x;
    drawState.value.currentY = pos.y;
    render();
  }
}

function onMouseUp(_event) {
  if (resizeState.value) {
    const box = resizeState.value.box;
    resizeState.value = null;
    render();
    if (box.annotationId) {
      emit("bbox-overridden", {
        annotationId: box.annotationId,
        x1: Math.round(box.x1),
        y1: Math.round(box.y1),
        x2: Math.round(box.x2),
        y2: Math.round(box.y2),
      });
    }
    return;
  }

  if (drawState.value) {
    const { startX, startY, currentX, currentY } = drawState.value;
    drawState.value = null;
    render();

    const w = Math.abs(currentX - startX);
    const h = Math.abs(currentY - startY);
    // Minimum 10px box size to prevent accidental clicks
    if (w < 10 || h < 10) return;

    const { x: ox1, y: oy1 } = toOrig(
      Math.min(startX, currentX),
      Math.min(startY, currentY)
    );
    const { x: ox2, y: oy2 } = toOrig(
      Math.max(startX, currentX),
      Math.max(startY, currentY)
    );

    const newBox = {
      annotationId: null,
      x1: Math.round(ox1),
      y1: Math.round(oy1),
      x2: Math.round(ox2),
      y2: Math.round(oy2),
      identityId: null,
      identityLabel: null,
      isOverride: false,
      isNew: true,
    };
    boxes.value.push(newBox);
    selectedBox.value = newBox;
    updatePopoverPosition(newBox);
    render();

    emit("bbox-created", {
      x1: newBox.x1,
      y1: newBox.y1,
      x2: newBox.x2,
      y2: newBox.y2,
    });
  }
}

// -- Tag / Delete handlers ----------------------------------------------------

function onTag({ identityId, reason }) {
  if (!selectedBox.value) return;
  const box = selectedBox.value;

  const label = lookupIdentityLabel(identityId);
  box.identityId = identityId;
  box.identityLabel = label || identityId;

  emit("bbox-tagged", {
    annotationId: box.annotationId,
    identityId,
    reason: reason || "",
  });

  selectedBox.value = null;
  popoverPosition.value = null;
  render();
}

function onDeleteBox() {
  const box = selectedBox.value;
  if (!box) return;
  boxes.value = boxes.value.filter((b) => b !== box);
  emit("bbox-deleted", { annotationId: box.annotationId });
  selectedBox.value = null;
  popoverPosition.value = null;
  render();
}

// -- Watch for prop changes ---------------------------------------------------

watch(() => props.initialBboxes, () => {
  syncBoxesFromProps();
  render();
});
</script>

<style scoped>
.bbox-canvas-wrapper {
  position: relative;
  display: inline-block;
  width: 100%;
  background: #000;
  border-radius: 8px;
  overflow: hidden;
}
.keyframe-image {
  display: block;
  width: 100%;
  height: auto;
  user-select: none;
}
.bbox-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  cursor: crosshair;
}
.bbox-ink-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}
</style>
