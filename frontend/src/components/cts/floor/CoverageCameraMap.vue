<template>
  <v-card class="glass-card floor-plan-visual-card">
    <v-card-title class="floor-plan-card-title d-flex align-center">
      Camera Coverage
      <v-spacer />
      <v-btn
        variant="tonal"
        size="small"
        prepend-icon="mdi-refresh"
        :loading="loading"
        class="mr-2"
        @click="emit('refresh')"
      >
        Refresh
      </v-btn>
    </v-card-title>
    <v-divider />

    <div class="d-flex align-center flex-wrap ga-4 px-4 py-2 text-caption text-medium-emphasis">
      <span class="d-flex align-center ga-1">
        <span
          class="coverage-legend-swatch"
          :style="{ borderColor: tokBrand, background: tokBrandSoft }"
        />
        Calibrated
      </span>
      <span class="d-flex align-center ga-1">
        <span
          class="coverage-legend-swatch"
          :style="{
            borderColor: tokText3,
            background: 'rgba(128,128,128,0.1)',
            borderStyle: 'dotted',
          }"
        />
        Not calibrated
      </span>
    </div>
    <v-divider />

    <v-card-text class="pa-0">
      <div class="coverage-canvas-wrap">
        <img
          v-if="floorPlanUrl"
          :src="floorPlanUrl"
          class="coverage-fp-img cc-floor-plan-background-image marauders-no-paint"
          alt="Floor plan"
          draggable="false"
          @load="emit('img-load', $event.target)"
        />

        <svg
          v-if="imgReady && floorPlanUrl"
          class="coverage-svg-overlay"
          :viewBox="`0 0 ${imgW} ${imgH}`"
          xmlns="http://www.w3.org/2000/svg"
        >
          <g v-for="cam in cameras" :key="cam.camera_id">
            <defs v-if="getFalloff(cam) && !maraudersEnabled">
              <radialGradient
                :id="`falloff-${cam.camera_id}`"
                gradientUnits="userSpaceOnUse"
                :cx="getFalloff(cam).cx"
                :cy="getFalloff(cam).cy"
                :r="getFalloff(cam).r"
              >
                <stop
                  v-for="(s, i) in getFalloff(cam).stops"
                  :key="i"
                  :offset="s.offset"
                  :stop-color="tokBrandSoft"
                  :stop-opacity="s.opacity"
                />
              </radialGradient>
            </defs>
            <MaraudersInkPolygon
              v-if="maraudersEnabled && cam.visibility_polygon"
              :points="cam.visibility_polygon"
              :canvas-w="imgW"
              :canvas-h="imgH"
              :seed-key="`coverage-${cam.camera_id}`"
            />
            <polygon
              v-else-if="cam.visibility_polygon"
              :points="toSvgPoints(cam.visibility_polygon)"
              :fill="getFalloff(cam) ? `url(#falloff-${cam.camera_id})` : tokBrandSoft"
              :stroke="tokBrand"
              stroke-width="2"
            />
            <g v-if="getMarker(cam)">
              <g
                :transform="`translate(${getLabelPos(cam)[0]}, ${getLabelPos(cam)[1]}) ${getMarker(cam).heading_deg != null ? 'rotate(' + getMarker(cam).heading_deg + ')' : ''}`"
              >
                <line
                  v-if="getMarker(cam).heading_deg != null"
                  x1="0"
                  y1="0"
                  x2="0"
                  y2="-24"
                  :stroke="
                    getMarker(cam).source === 'derived' ? 'rgb(var(--v-theme-warning))' : tokBrand
                  "
                  stroke-width="2"
                  stroke-dasharray="2,2"
                />
                <circle
                  r="12"
                  :fill="
                    getMarker(cam).source === 'derived' ? 'rgb(var(--v-theme-warning))' : tokBrand
                  "
                />
                <foreignObject x="-12" y="-12" width="24" height="24">
                  <div
                    style="
                      width: 24px;
                      height: 24px;
                      display: flex;
                      align-items: center;
                      justify-content: center;
                    "
                  >
                    <v-icon size="14" color="white" style="line-height: 1">mdi-cctv</v-icon>
                  </div>
                </foreignObject>
              </g>
            </g>
            <text
              v-if="cam.visibility_polygon || getMarker(cam)"
              :x="getLabelPos(cam)[0]"
              :y="getLabelPos(cam)[1] + (getMarker(cam) ? 20 : 0)"
              text-anchor="middle"
              dominant-baseline="middle"
              font-size="12"
              font-family="system-ui, sans-serif"
              fill="white"
              paint-order="stroke"
              stroke="rgba(0,0,0,0.7)"
              stroke-width="3"
              style="pointer-events: none"
            >
              {{ cam.camera_name }}
            </text>
          </g>
        </svg>

        <div
          v-if="!floorPlanUrl"
          class="coverage-empty d-flex flex-column align-center justify-center"
        >
          <v-icon size="48" color="medium-emphasis">mdi-floor-plan</v-icon>
          <div class="text-body-2 text-medium-emphasis mt-2">Upload a floor plan first.</div>
          <v-btn variant="tonal" size="small" class="mt-3" @click="emit('go-upload')">
            Go to Floor Plan
          </v-btn>
        </div>
      </div>

      <div v-if="uncalibrated.length > 0" class="px-4 py-3">
        <v-alert type="warning" density="compact" variant="tonal">
          <strong>{{ uncalibrated.length }} camera(s) not shown</strong>
          <ul class="ml-4 mt-1">
            <li v-for="g in summary" :key="g.status">
              {{ g.count }}x {{ g.text }}
              <span v-if="g.status === 'no_homography'">
                <v-btn variant="text" size="x-small" class="ml-1" :to="{ name: 'cts-calibration' }">
                  Calibrate &rarr;
                </v-btn>
              </span>
              <span v-else-if="g.status === 'scale_missing'">
                (<a href="#" class="text-primary" @click.prevent="emit('go-upload')"
                  >Floor Plan settings</a
                >)
              </span>
            </li>
          </ul>
        </v-alert>
      </div>
    </v-card-text>
  </v-card>
</template>

<script setup>
import { computed } from "vue";
import MaraudersInkPolygon from "@/components/marauders/MaraudersInkPolygon.vue";
import { falloffStops } from "./coverageFalloff.js";

const props = defineProps({
  loading: { type: Boolean, default: false },
  floorPlanUrl: { type: String, default: null },
  imgReady: { type: Boolean, default: false },
  imgW: { type: Number, default: 0 },
  imgH: { type: Number, default: 0 },
  cameras: { type: Array, required: true },
  uncalibrated: { type: Array, required: true },
  maraudersEnabled: { type: Boolean, default: false },
  toSvgPoints: { type: Function, required: true },
  centroid: { type: Function, required: true },
  tokBrand: { type: String, required: true },
  tokBrandSoft: { type: String, required: true },
  tokText3: { type: String, required: true },
});
const emit = defineEmits(["refresh", "img-load", "go-upload"]);

function getMarker(cam) {
  return cam.marker || cam.marker_estimate || null;
}

function getFalloff(cam) {
  const marker = getMarker(cam);
  if (!marker || !cam.visibility_polygon) return null;
  return falloffStops(marker, cam.visibility_polygon, props.imgW, props.imgH);
}

function getLabelPos(cam) {
  const m = getMarker(cam);
  if (m && props.imgReady) {
    return [m.x_norm * props.imgW, m.y_norm * props.imgH];
  }
  if (cam.visibility_polygon) {
    return props.centroid(cam.visibility_polygon);
  }
  return [0, 0];
}

const summary = computed(() => {
  const map = {
    no_homography: "no homography calibration yet.",
    scale_missing: "floor plan scale (m/pixel) not set.",
    no_floor_side: "calibration sees no floor area.",
    degenerate_matrix: "homography math failed (degenerate matrix).",
    unknown: "visibility polygon could not be computed.",
  };
  const counts = {};
  for (const c of props.uncalibrated) {
    const st = c.visibility_status || "unknown";
    counts[st] = (counts[st] || 0) + 1;
  }
  return Object.keys(counts).map((st) => ({
    status: st,
    count: counts[st],
    text: map[st] || map.unknown,
  }));
});
</script>

<style scoped>
.coverage-canvas-wrap {
  position: relative;
  overflow: hidden;
  background: var(--cc-surface-2);
  min-height: 260px;
  max-height: 58vh;
}

.coverage-fp-img {
  display: block;
  width: 100%;
  max-height: 58vh;
  height: auto;
  object-fit: contain;
  object-position: center;
}

.coverage-svg-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.coverage-empty {
  min-height: 260px;
}

.coverage-legend-swatch {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid;
  border-radius: 3px;
  vertical-align: middle;
}

@media (max-width: 959px) {
  .coverage-canvas-wrap {
    max-height: 62vh;
  }
}
</style>
