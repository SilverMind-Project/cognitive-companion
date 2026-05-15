<template>
  <div class="cts-floor-plan-view pa-4">
    <v-toolbar flat density="compact" color="transparent">
      <v-toolbar-title>Floor Plan</v-toolbar-title>
      <v-spacer />
      <v-btn
        :icon="paused ? 'mdi-play' : 'mdi-pause'"
        variant="text"
        @click="paused = !paused"
      />
    </v-toolbar>

    <!-- Floor plan canvas -->
    <div ref="canvasContainer" class="floor-plan-canvas">
      <svg
        ref="svgEl"
        :viewBox="`0 0 ${canvasW} ${canvasH}`"
        preserveAspectRatio="xMidYMid meet"
        class="floor-plan-svg"
      >
        <!-- Reference image (when uploaded) -->
        <image
          v-if="floorPlanUrl"
          :href="floorPlanUrl"
          width="100%"
          height="100%"
          opacity="0.4"
        />

        <!-- Identity dots + fading trails -->
        <g v-for="(trail, identityId) in identityTrails" :key="identityId">
          <!-- Fading trail polyline -->
          <polyline
            v-if="trail.points.length > 1"
            :points="trail.points.map(p => `${p.x},${p.y}`).join(' ')"
            :stroke="trail.color"
            stroke-width="3"
            fill="none"
            opacity="0.5"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
          <!-- Current position dot -->
          <circle
            v-if="trail.current"
            :cx="trail.current.x"
            :cy="trail.current.y"
            r="8"
            :fill="trail.color"
            stroke="#fff"
            stroke-width="2"
          />
          <!-- Identity label -->
          <text
            v-if="trail.current"
            :x="trail.current.x + 12"
            :y="trail.current.y - 8"
            :fill="trail.color"
            font-size="12"
            font-weight="bold"
          >
            {{ trail.displayName || identityId }}
          </text>
        </g>

        <!-- Empty state -->
        <text
          v-if="Object.keys(identityTrails).length === 0"
          x="50%"
          y="50%"
          text-anchor="middle"
          fill="#888"
          font-size="16"
        >
          No active tracks. Enable live view to see people on the floor plan.
        </text>
      </svg>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, shallowRef } from "vue";
import { identityColor } from "@/composables/useIdentityColor";
import { useCtsWebSocket } from "@/composables/useCtsWebSocket";

const canvasW = ref(1000);
const canvasH = ref(800);
const paused = ref(false);
const svgEl = ref(null);
const floorPlanUrl = ref(null);

// identityId → { points: [{x, y, ts}], current: {x, y}, color, displayName }
const identityTrails = shallowRef({});

const MAX_TRAIL_POINTS = 60;

const ws = useCtsWebSocket();

function onLiveFrame(frame) {
  if (paused.value) return;

  const detections = frame.detections || [];
  const identities = frame.identities || {};
  const frameW = frame.frame_width || 640;
  const frameH = frame.frame_height || 480;

  const trails = { ...identityTrails.value };

  for (const det of detections) {
    const gtId = det.global_track_id;
    const identityInfo = identities[gtId];
    if (!identityInfo) continue;

    const identityId = identityInfo[0] || gtId;
    const bbox = det.bbox;

    // Use bottom-center of bbox as foot position, remapped to canvas.
    const fx = bbox ? ((bbox.x_min + bbox.x_max) / 2) / frameW * canvasW.value : 0;
    const fy = bbox ? bbox.y_max / frameH * canvasH.value : 0;

    let trail = trails[identityId];
    if (!trail) {
      trail = {
        points: [],
        current: null,
        color: identityColor(identityId),
        displayName: identityId,
      };
      trails[identityId] = trail;
    }

    trail.points.push({ x: fx, y: fy, ts: Date.now() });
    if (trail.points.length > MAX_TRAIL_POINTS) {
      trail.points = trail.points.slice(-MAX_TRAIL_POINTS);
    }
    trail.current = { x: fx, y: fy };
  }

  identityTrails.value = trails;
}

onMounted(() => {
  ws.on("cts_live_frame", onLiveFrame);
});

onUnmounted(() => {
  ws.off("cts_live_frame", onLiveFrame);
});
</script>

<style scoped>
.cts-floor-plan-view {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.floor-plan-canvas {
  flex: 1;
  background: #1a1a2e;
  border-radius: 8px;
  overflow: hidden;
  position: relative;
}

.floor-plan-svg {
  width: 100%;
  height: 100%;
}
</style>
