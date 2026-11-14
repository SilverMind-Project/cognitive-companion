<template>
  <div>
    <div class="mb-6">
      <h2 class="text-h4 font-weight-bold tracking-tight">Shared Views</h2>
      <div class="text-body-2 text-medium-emphasis mt-1">
        Tell tracking which cameras see the same floor area at the same time, so one person seen by
        two cameras stays one person. Walk times between cameras are learned automatically.
      </div>
    </div>

    <v-alert type="info" variant="tonal" density="compact" class="mb-4" icon="mdi-information">
      <strong>Calibration</strong> places each camera's view on the floor plan (one camera at a
      time, on
      <router-link to="/admin/cts/calibration" class="text-primary">Calibration</router-link>). A
      <strong>shared view</strong> says several cameras look at the same place at the same moment.
      Two calibrated cameras already agree through the floor plan; a shared view matters whenever
      one of the cameras is not calibrated. Cameras you walk between, without seeing the same spot,
      need nothing here: tracking learns those transitions.
    </v-alert>

    <v-row>
      <v-col cols="12" md="7">
        <v-card class="glass-card">
          <v-card-title class="text-body-1 font-weight-medium">Calibrated Coverage</v-card-title>
          <v-divider />
          <v-card-text class="pa-0">
            <div style="position: relative; overflow: hidden">
              <template v-if="floorPlanUrl">
                <img
                  ref="mapImgRef"
                  :src="floorPlanUrl"
                  class="marauders-no-paint"
                  style="display: block; width: 100%; height: auto"
                  alt="Floor plan with calibrated camera coverage"
                  @load="onMapImgLoad"
                />
                <svg
                  v-if="mapImgLoaded"
                  :viewBox="`0 0 ${mapImgW} ${mapImgH}`"
                  class="coverage-overlay"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <template v-for="cam in coverageCameras" :key="cam.camera_id">
                    <polygon
                      v-if="cam.visibility_polygon"
                      :points="toSvgPoints(cam.visibility_polygon)"
                      :fill="isGrouped(cam.camera_id) ? 'var(--cc-success)' : 'var(--cc-info)'"
                      fill-opacity="0.14"
                      :stroke="isGrouped(cam.camera_id) ? 'var(--cc-success)' : 'var(--cc-info)'"
                      stroke-width="1.5"
                    />
                  </template>
                  <template v-for="cam in coverageCameras" :key="`lbl-${cam.camera_id}`">
                    <text
                      v-if="cam.visibility_polygon"
                      :x="centroidOf(cam)[0]"
                      :y="centroidOf(cam)[1]"
                      class="coverage-label"
                      text-anchor="middle"
                      dominant-baseline="middle"
                    >
                      {{ cam.camera_name }}
                    </text>
                  </template>
                </svg>
              </template>
              <div v-else class="pa-6 text-center text-body-2 text-medium-emphasis">
                No floor plan uploaded. Upload one with its scale in
                <router-link to="/admin/cts/floor-plan" class="text-primary"
                  >Floor Plan settings</router-link
                >
                to see where calibrated cameras look.
              </div>
            </div>
            <div class="d-flex align-center flex-wrap ga-3 px-4 py-2 text-caption">
              <span class="d-flex align-center ga-1">
                <span class="legend-swatch legend-swatch--grouped" />In a shared view
              </span>
              <span class="d-flex align-center ga-1">
                <span class="legend-swatch legend-swatch--alone" />Calibrated, not grouped
              </span>
              <span v-if="uncalibratedNames.length" class="text-medium-emphasis">
                Not calibrated (not drawn): {{ uncalibratedNames.join(", ") }}
              </span>
            </div>
          </v-card-text>
        </v-card>

        <LearnedTransitionsCard :camera-names="cameraNames" class="mt-3" />
      </v-col>

      <v-col cols="12" md="5">
        <OverlapGroupSuggestions
          :suggestions="suggestions"
          :camera-names="cameraNames"
          @use="(ids) => groupsCard?.prefill(ids)"
        />
        <OverlapGroupsCard
          ref="groupsCard"
          :groups="overlapGroups"
          :cameras="cameraOptions"
          @changed="reloadGroups"
        />
      </v-col>
    </v-row>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { cts } from "@/services/cts.js";
import { household } from "@/services/household.js";
import OverlapGroupsCard from "@/components/cts/OverlapGroupsCard.vue";
import OverlapGroupSuggestions from "@/components/cts/OverlapGroupSuggestions.vue";
import LearnedTransitionsCard from "@/components/cts/LearnedTransitionsCard.vue";

/**
 * @typedef {{ camera_id: string, camera_name: string, visibility_polygon: number[][] | null }} CameraPolygon
 * @typedef {{ id: string, name: string }} CameraOption
 */

/** @type {import('vue').Ref<CameraOption[]>} */
const cameraOptions = ref([]);
/** @type {import('vue').Ref<CameraPolygon[]>} */
const coverageCameras = ref([]);
const overlapGroups = ref([]);
const suggestions = ref({ groups: [], uncalibrated_camera_ids: [] });
const floorPlanUrl = ref(null);
const groupsCard = ref(null);

const mapImgRef = ref(null);
const mapImgLoaded = ref(false);
const mapImgW = ref(0);
const mapImgH = ref(0);

const cameraNames = computed(() =>
  Object.fromEntries(cameraOptions.value.map((c) => [c.id, c.name || c.id])),
);
const groupedCameraIds = computed(
  () => new Set(overlapGroups.value.flatMap((g) => g.camera_ids || [])),
);
const uncalibratedNames = computed(() =>
  suggestions.value.uncalibrated_camera_ids.map((id) => cameraNames.value[id] || id),
);

function isGrouped(cameraId) {
  return groupedCameraIds.value.has(cameraId);
}

function toSvgPoints(polygon) {
  return polygon
    .map(([x, y]) => `${(x * mapImgW.value).toFixed(1)},${(y * mapImgH.value).toFixed(1)}`)
    .join(" ");
}

function centroidOf(cam) {
  const pts = cam.visibility_polygon;
  const sx = pts.reduce((s, [x]) => s + x, 0);
  const sy = pts.reduce((s, [, y]) => s + y, 0);
  return [(sx / pts.length) * mapImgW.value, (sy / pts.length) * mapImgH.value];
}

function onMapImgLoad() {
  if (!mapImgRef.value) return;
  mapImgW.value = mapImgRef.value.naturalWidth;
  mapImgH.value = mapImgRef.value.naturalHeight;
  mapImgLoaded.value = true;
}

async function loadCameras() {
  try {
    cameraOptions.value = await cts.getCameras();
  } catch (err) {
    console.warn("cts_cameras_load_failed", err);
    cameraOptions.value = [];
  }
}

async function loadCoverage() {
  try {
    const data = await cts.getVisibilityPolygons();
    coverageCameras.value = Array.isArray(data?.cameras)
      ? data.cameras.filter((c) => typeof c?.camera_id === "string")
      : [];
  } catch (err) {
    console.warn("cts_visibility_polygons_load_failed", err);
    coverageCameras.value = [];
  }
}

async function loadFloorPlan() {
  try {
    floorPlanUrl.value = (await household.getFloorPlan())?.floor_plan_url || null;
  } catch {
    floorPlanUrl.value = null;
  }
}

async function reloadGroups() {
  const [groups, suggested] = await Promise.allSettled([
    cts.getOverlapGroups(),
    cts.getOverlapGroupSuggestions(),
  ]);
  overlapGroups.value = groups.status === "fulfilled" ? groups.value : [];
  suggestions.value =
    suggested.status === "fulfilled"
      ? suggested.value
      : { groups: [], uncalibrated_camera_ids: [] };
}

onMounted(() => Promise.all([loadCameras(), loadCoverage(), loadFloorPlan(), reloadGroups()]));
</script>

<style scoped>
.coverage-overlay {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}
.coverage-label {
  font-size: 11px;
  fill: var(--cc-text-1);
  paint-order: stroke;
  stroke: var(--cc-bg);
  stroke-width: 3px;
}
.legend-swatch {
  display: inline-block;
  width: 14px;
  height: 10px;
  border-radius: 2px;
  border: 1.5px solid;
}
.legend-swatch--grouped {
  border-color: var(--cc-success);
}
.legend-swatch--alone {
  border-color: var(--cc-info);
}
</style>
