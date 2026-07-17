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
              :fill="tokBrandSoft"
              :stroke="tokBrand"
              stroke-width="2"
            />
            <text
              v-if="cam.visibility_polygon"
              :x="centroid(cam.visibility_polygon)[0]"
              :y="centroid(cam.visibility_polygon)[1]"
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

        <div v-if="!floorPlanUrl" class="coverage-empty d-flex flex-column align-center justify-center">
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
          &mdash;
          <span v-if="uncalibrated.some((c) => c.has_homography)">
            visibility polygon could not be computed. Check that the floor plan scale (m/pixel)
            is correct in
            <a href="#" class="text-primary" @click.prevent="emit('go-upload')">Floor Plan settings</a>.
          </span>
          <span v-else>
            no homography calibration yet.
            <v-btn variant="text" size="x-small" class="ml-1" :to="{ name: 'cts-calibration' }">
              Calibrate &rarr;
            </v-btn>
          </span>
        </v-alert>
      </div>
    </v-card-text>
  </v-card>
</template>

<script setup>
import MaraudersInkPolygon from "@/components/marauders/MaraudersInkPolygon.vue";

defineProps({
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
