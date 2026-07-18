<template>
  <v-card class="glass-card floor-plan-visual-card">
    <v-card-title class="floor-plan-card-title d-flex align-center">
      <span>Live Floor Plan</span>
      <v-spacer />
      <v-chip
        v-if="!floorPlanUrl"
        color="warning"
        size="small"
        variant="tonal"
        prepend-icon="mdi-alert-outline"
        class="mr-2"
      >
        No floor plan
      </v-chip>
      <v-chip
        v-if="uncalibratedPhCount > 0"
        color="warning"
        size="small"
        variant="tonal"
        prepend-icon="mdi-crosshairs-off"
        class="mr-2"
        @click="emit('go-calibration')"
      >
        {{ uncalibratedPhCount }} person(s) off-plan
      </v-chip>
      <v-chip :color="worldStatusColor" size="small" variant="tonal">
        <v-icon start size="14">{{ worldStatusIcon }}</v-icon>
        {{ worldStatusLabel }}
      </v-chip>
    </v-card-title>
    <v-divider />
    <v-card-text class="pa-0">
      <!-- Floor plan canvas with pan/zoom. The outer div clips the zoomed
           content; the inner zoom-content div receives the CSS transform. -->
      <div
        ref="liveCanvasRef"
        class="floor-plan-canvas"
        :style="{ aspectRatio: `${canvasW}/${canvasH}` }"
        @wheel.prevent="liveZoom.actions.onWheel"
      >
        <div
          class="floor-plan-zoom-content"
          :style="liveZoom.state.transformStyle"
          @mousedown="emit('canvas-mousedown', $event)"
        >
          <svg :viewBox="`0 0 ${canvasW} ${canvasH}`" class="floor-plan-svg">
            <!-- Background floor plan image -->
            <image
              v-if="floorPlanUrl"
              :href="floorPlanUrl"
              :width="canvasW"
              :height="canvasH"
              class="cc-floor-plan-background-image marauders-no-paint"
            />

            <!-- Room polygons -->
            <g v-for="room in rooms" :key="room.id">
              <MaraudersInkPolygon
                v-if="
                  maraudersState.enabled && room.floor_polygon && room.floor_polygon.length >= 3
                "
                :points="room.floor_polygon"
                :canvas-w="canvasW"
                :canvas-h="canvasH"
                :seed-key="`room-${room.id}`"
                :label="room.name"
              />
              <template v-else-if="room.floor_polygon && room.floor_polygon.length >= 3">
                <polygon
                  :points="
                    room.floor_polygon.map(([x, y]) => `${x * canvasW},${y * canvasH}`).join(' ')
                  "
                  class="room-poly"
                />
                <text
                  :x="centroidX(room.floor_polygon) * canvasW"
                  :y="centroidY(room.floor_polygon) * canvasH"
                  class="room-label"
                >
                  {{ room.name }}
                </text>
              </template>
            </g>

            <!-- PH-driven markers: smoothedMarkers are rAF-interpolated positions.
                 phCount uses worldPhMarkers.length to avoid a flash where
                 smoothedMarkers is briefly empty while the rAF tween starts.
                 M4 seam: MaraudersFloorMarkers renders disappearing footprints
                 when marauders mode is ON; FloorMarkerLayer otherwise. -->
            <MaraudersFloorMarkers
              v-if="maraudersState.enabled"
              :markers="smoothedMarkers"
              :ph-count="phCount"
              :canvas-h="canvasH"
              :trails="trailBuffers"
              :now-ms="footprintNow"
              :fp-width="fpWidth"
              :fp-height="fpHeight"
              :fp-mpp="fpMpp"
              :canvas-w="canvasW"
              :reduced-motion="maraudersState.reducedMotion"
              @ph-click="emit('ph-click', $event)"
            />
            <FloorMarkerLayer
              v-else
              :markers="smoothedMarkers"
              :ph-count="phCount"
              :canvas-h="canvasH"
              @ph-click="emit('ph-click', $event)"
            />
            <MaraudersAmbientLayer
              v-if="maraudersState.enabled"
              :canvas-w="canvasW"
              :canvas-h="canvasH"
              :now-ms="footprintNow"
              :reduced-motion="maraudersState.reducedMotion"
            />
          </svg>
        </div>

        <CcZoomControls
          :zoom="liveZoom.state.zoom"
          :pan-x="liveZoom.state.panX"
          :pan-y="liveZoom.state.panY"
          :max-zoom="5"
          :min-zoom="0.3"
          @zoom-in="liveZoom.actions.zoomIn(liveCanvasRef)"
          @zoom-out="liveZoom.actions.zoomOut(liveCanvasRef)"
          @reset="liveZoom.actions.reset()"
        />
      </div>

      <!-- Legend -->
      <div class="floor-plan-legend d-flex align-center flex-wrap ga-4 px-3 py-2">
        <div class="d-flex align-center ga-1 text-caption text-medium-emphasis">
          <svg width="28" height="14">
            <line
              x1="0"
              y1="7"
              x2="28"
              y2="7"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
            />
            <circle cx="14" cy="7" r="5" fill="currentColor" stroke="#fff" stroke-width="1.5" />
          </svg>
          Floor-mapped
        </div>
        <div class="d-flex align-center ga-1 text-caption text-medium-emphasis">
          <svg width="28" height="14">
            <line
              x1="0"
              y1="7"
              x2="28"
              y2="7"
              stroke="currentColor"
              stroke-width="2"
              stroke-dasharray="5 3"
              stroke-linecap="round"
            />
            <circle
              cx="14"
              cy="7"
              r="5"
              fill="none"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-dasharray="4 2"
            />
          </svg>
          Estimated (no homography)
        </div>
      </div>
    </v-card-text>
  </v-card>
</template>

<script setup>
import { ref } from "vue";
import CcZoomControls from "@/components/common/CcZoomControls.vue";
import MaraudersInkPolygon from "@/components/marauders/MaraudersInkPolygon.vue";
import MaraudersFloorMarkers from "@/components/marauders/MaraudersFloorMarkers.vue";
import MaraudersAmbientLayer from "@/components/marauders/MaraudersAmbientLayer.vue";
import FloorMarkerLayer from "@/components/cts/floor/FloorMarkerLayer.vue";

defineProps({
  floorPlanUrl: { type: String, default: null },
  canvasW: { type: Number, required: true },
  canvasH: { type: Number, required: true },
  fpWidth: { type: Number, default: null },
  fpHeight: { type: Number, default: null },
  fpMpp: { type: Number, default: null },
  rooms: { type: Array, required: true },
  maraudersState: { type: Object, required: true },
  liveZoom: { type: Object, required: true },
  smoothedMarkers: { type: Array, required: true },
  phCount: { type: Number, required: true },
  trailBuffers: { type: [Map, Object], required: true },
  footprintNow: { type: Number, required: true },
  uncalibratedPhCount: { type: Number, required: true },
  worldStatusColor: { type: String, required: true },
  worldStatusIcon: { type: String, required: true },
  worldStatusLabel: { type: String, required: true },
});
const emit = defineEmits(["ph-click", "canvas-mousedown", "go-calibration"]);

const liveCanvasRef = ref(null);

function centroidX(polygon) {
  return polygon.reduce((s, [x]) => s + x, 0) / polygon.length;
}
function centroidY(polygon) {
  return polygon.reduce((s, [, y]) => s + y, 0) / polygon.length;
}
</script>
