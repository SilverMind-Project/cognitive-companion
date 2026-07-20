<template>
  <div ref="wrapRef" class="camera-placement-map" @mousedown="onMouseDown" @mousemove="onMouseMove" @mouseup="onMouseUp" @mouseleave="onMouseUp">
    <img
      v-if="floorPlanUrl"
      :src="floorPlanUrl"
      class="fp-img cc-floor-plan-background-image"
      draggable="false"
      @load="onImgLoad"
    />
    
    <svg
      v-if="imgReady && floorPlanUrl"
      class="svg-overlay"
      :viewBox="`0 0 ${imgW} ${imgH}`"
      xmlns="http://www.w3.org/2000/svg"
    >
      <g v-if="markerX != null && markerY != null">
        <!-- Translucent cone -->
        <polygon
          v-if="headingDeg != null"
          :points="conePoints"
          fill="rgba(var(--v-theme-primary), 0.2)"
          stroke="none"
        />
        <!-- Camera icon -->
        <g :transform="`translate(${markerX * imgW}, ${markerY * imgH}) ${headingDeg != null ? 'rotate(' + headingDeg + ')' : ''}`">
          <circle r="16" :fill="source === 'derived' ? 'rgb(var(--v-theme-warning))' : 'rgb(var(--v-theme-primary))'" />
          <foreignObject x="-12" y="-12" width="24" height="24">
            <div style="width: 24px; height: 24px; display: flex; align-items: center; justify-content: center;">
              <v-icon size="16" color="white">mdi-cctv</v-icon>
            </div>
          </foreignObject>
        </g>
      </g>
    </svg>
    <div v-if="!floorPlanUrl" class="pa-4 text-center text-medium-emphasis">
      No floor plan available.
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue';

const props = defineProps({
  floorPlanUrl: { type: String, default: null },
  initialMarker: { type: Object, default: null }, // { x_norm, y_norm, heading_deg, source }
});

const emit = defineEmits(['placed']);

const wrapRef = ref(null);
const imgReady = ref(false);
const imgW = ref(0);
const imgH = ref(0);

const markerX = ref(null);
const markerY = ref(null);
const headingDeg = ref(null);
const source = ref('operator');

let isDragging = false;
let startX = 0;
let startY = 0;

watch(() => props.initialMarker, (val) => {
  if (val) {
    markerX.value = val.x_norm;
    markerY.value = val.y_norm;
    headingDeg.value = val.heading_deg;
    source.value = val.source || 'operator';
  } else {
    markerX.value = null;
    markerY.value = null;
    headingDeg.value = null;
    source.value = 'operator';
  }
}, { immediate: true });

function onImgLoad(e) {
  imgW.value = e.target.naturalWidth;
  imgH.value = e.target.naturalHeight;
  imgReady.value = true;
}

const conePoints = computed(() => {
  if (markerX.value == null || markerY.value == null || headingDeg.value == null || !imgReady.value) return "";
  
  const cx = markerX.value * imgW.value;
  const cy = markerY.value * imgH.value;
  const h_rad = (headingDeg.value - 90) * Math.PI / 180;
  
  const len = Math.max(imgW.value, imgH.value) * 0.15;
  const spread = (45 / 2) * Math.PI / 180;
  
  const p1x = cx + len * Math.cos(h_rad - spread);
  const p1y = cy + len * Math.sin(h_rad - spread);
  
  const p2x = cx + len * Math.cos(h_rad + spread);
  const p2y = cy + len * Math.sin(h_rad + spread);
  
  return `${cx},${cy} ${p1x},${p1y} ${p2x},${p2y}`;
});

function getNormCoords(e) {
  const rect = wrapRef.value.getBoundingClientRect();
  const x = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
  const y = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));
  return { x, y };
}

function onMouseDown(e) {
  isDragging = true;
  const { x, y } = getNormCoords(e);
  markerX.value = x;
  markerY.value = y;
  headingDeg.value = null;
  source.value = 'operator';
  startX = x;
  startY = y;
}

function onMouseMove(e) {
  if (!isDragging) return;
  const { x, y } = getNormCoords(e);
  
  const dx = x - startX;
  const dy = y - startY;
  
  if (Math.hypot(dx, dy) > 0.01) {
    const angle = Math.atan2(dx, -dy) * 180 / Math.PI;
    headingDeg.value = (angle + 360) % 360;
  }
}

function onMouseUp() {
  if (!isDragging) return;
  isDragging = false;
  emit('placed', {
    x_norm: markerX.value,
    y_norm: markerY.value,
    heading_deg: headingDeg.value,
  });
}
</script>

<style scoped>
.camera-placement-map {
  position: relative;
  width: 100%;
  max-height: 60vh;
  overflow: hidden;
  cursor: crosshair;
  background: var(--cc-surface-2);
}
.fp-img {
  display: block;
  width: 100%;
  max-height: 60vh;
  object-fit: contain;
}
.svg-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}
</style>
