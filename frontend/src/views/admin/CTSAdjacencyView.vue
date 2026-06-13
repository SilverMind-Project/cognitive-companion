<template>
  <div>
    <!-- Page header -->
    <div class="d-flex align-center mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Camera Adjacency</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Define which cameras share a physical boundary. Use "Infer from coverage"
          for a starting point, then adjust transit times as needed.
        </div>
      </div>
      <v-spacer />
      <v-tooltip
        :text="hasPolygons ? 'Analyze visibility polygons to suggest adjacency edges' : 'Calibrate at least one camera homography to enable inference'"
      >
        <template #activator="{ props }">
          <v-btn
            v-bind="props"
            variant="tonal"
            class="mr-2"
            prepend-icon="mdi-auto-fix"
            :loading="inferring"
            :disabled="!hasPolygons"
            @click="inferAdjacency"
          >
            Infer from coverage
          </v-btn>
        </template>
      </v-tooltip>
      <v-btn color="primary" variant="flat" prepend-icon="mdi-plus" @click="openCreate">
        Add Edge
      </v-btn>
    </div>

    <!-- Two-panel layout -->
    <v-row>
      <!-- Left: Floor plan coverage map with edge lines -->
      <v-col cols="12" md="7">
        <v-card class="glass-card">
          <v-card-title class="text-body-1 font-weight-medium">Coverage Map</v-card-title>
          <v-divider />
          <v-card-text class="pa-0">
            <div style="position:relative;overflow:hidden">
              <template v-if="floorPlanUrl">
                <img
                  :src="floorPlanUrl"
                  class="marauders-no-paint"
                  style="display:block;width:100%;height:auto"
                  ref="mapImgRef"
                  @load="onMapImgLoad"
                />
                <svg
                  v-if="mapImgLoaded"
                  :viewBox="`0 0 ${mapImgW} ${mapImgH}`"
                  style="position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <!-- Camera visibility polygons (muted, background) -->
                  <template v-for="cam in coverageCameras" :key="cam.camera_id">
                    <polygon
                      v-if="cam.visibility_polygon"
                      :points="toSvgPoints(cam.visibility_polygon)"
                      fill="var(--cc-info)"
                      fill-opacity="0.12"
                      stroke="var(--cc-info)"
                      stroke-width="1.5"
                    />
                  </template>
                  <!-- Adjacency edge lines -->
                  <line
                    v-for="edge in allEdgesForMap"
                    :key="edge._key"
                    :x1="centroidOf(edge.from)[0]"
                    :y1="centroidOf(edge.from)[1]"
                    :x2="centroidOf(edge.to)[0]"
                    :y2="centroidOf(edge.to)[1]"
                    :stroke="edge.overlap ? 'var(--cc-success)' : 'var(--cc-chart-2)'"
                    stroke-width="2"
                    :stroke-dasharray="edge._staged ? '6,3' : 'none'"
                    opacity="0.8"
                  />
                  <!-- Camera labels at polygon centroids -->
                  <template v-for="cam in coverageCameras" :key="`lbl-${cam.camera_id}`">
                    <text
                      v-if="cam.visibility_polygon"
                      :x="centroidOf(cam.camera_id)[0]"
                      :y="centroidOf(cam.camera_id)[1]"
                      text-anchor="middle"
                      dominant-baseline="middle"
                      font-size="11"
                      font-family="sans-serif"
                      fill="white"
                      paint-order="stroke"
                      stroke="black"
                      stroke-width="3"
                    >
                      {{ cam.camera_name }}
                    </text>
                  </template>
                </svg>
              </template>
              <div v-else class="pa-6 text-center">
                <v-card flat>
                  <v-card-text class="text-grey text-h6">No floor plan uploaded</v-card-text>
                  <v-card-text class="text-grey">
                    Upload a floor plan with its scale in Floor Plan settings
                    to see camera coverage and infer adjacency.
                  </v-card-text>
                </v-card>
              </div>
            </div>
            <div class="d-flex align-center flex-wrap ga-3 px-4 py-2 text-caption">
              <span class="d-flex align-center ga-1">
                <svg width="20" height="10"><line x1="0" y1="5" x2="20" y2="5" stroke="var(--cc-success)" stroke-width="2"/></svg>
                Overlap
              </span>
              <span class="d-flex align-center ga-1">
                <svg width="20" height="10"><line x1="0" y1="5" x2="20" y2="5" stroke="var(--cc-chart-2)" stroke-width="2"/></svg>
                Adjacent
              </span>
              <span class="d-flex align-center ga-1">
                <svg width="20" height="10"><line x1="0" y1="5" x2="20" y2="5" stroke="var(--cc-text-3)" stroke-width="2" stroke-dasharray="4,2"/></svg>
                Staged (unsaved)
              </span>
            </div>
            <v-alert
              v-if="floorPlanUrl && !hasPolygons && !loadingEdges"
              type="info"
              density="compact"
              variant="tonal"
              class="ma-4"
            >
              <template v-if="calibratedWithoutPolygons.length > 0">
                Coverage polygons could not be computed for
                {{ calibratedWithoutPolygons.length }} calibrated camera(s).
                Recompute coverage in Floor Plan settings, or revisit the calibration point correspondences.
              </template>
              <template v-else>
                Calibrate camera homographies in
                <router-link to="/admin/cts/calibration" class="text-primary">Homography Calibration</router-link>
                to compute visibility polygons and enable coverage-based inference.
              </template>
            </v-alert>
          </v-card-text>
        </v-card>
      </v-col>

      <!-- Right: Edge list -->
      <v-col cols="12" md="5">
        <!-- Staged edges -->
        <v-card v-if="stagedEdges.length > 0" class="glass-card mb-3">
          <v-card-title class="d-flex align-center text-body-1">
            Staged
            <v-spacer />
            <v-chip size="x-small" color="warning" variant="tonal">Unsaved</v-chip>
          </v-card-title>
          <v-divider />
          <v-list density="compact">
            <v-list-item
              v-for="edge in stagedEdges"
              :key="edge._key"
              class="py-1"
            >
              <template #prepend>
                <v-icon
                  :color="edge.overlap ? 'success' : 'secondary'"
                  size="small"
                >
                  {{ edge.overlap ? 'mdi-link-variant' : 'mdi-arrow-right' }}
                </v-icon>
              </template>
              <v-list-item-title class="text-body-2">
                {{ edge.from }} → {{ edge.to }}
              </v-list-item-title>
              <v-list-item-subtitle class="text-caption">
                {{ edge.min_transit_s }}s – {{ edge.max_transit_s }}s
                <span v-if="edge.overlap" class="ml-1 text-success">overlap</span>
              </v-list-item-subtitle>
              <template #append>
                <v-btn icon="mdi-pencil" size="x-small" variant="text" color="primary" @click="openEdit(edge)" />
                <v-btn icon="mdi-delete" size="x-small" variant="text" color="error" @click="removeEdge(edge)" />
              </template>
            </v-list-item>
          </v-list>
          <v-card-actions>
            <v-spacer />
            <v-btn
              color="primary"
              variant="flat"
              size="small"
              :loading="saving"
              prepend-icon="mdi-content-save"
              @click="saveAdjacency"
            >
              Save All
            </v-btn>
          </v-card-actions>
        </v-card>

        <!-- Saved edges -->
        <v-card class="glass-card">
          <v-card-title class="d-flex align-center text-body-1">
            Saved Edges
            <v-spacer />
            <span class="text-caption text-medium-emphasis">{{ savedEdges.length }}</span>
          </v-card-title>
          <v-divider />
          <v-list v-if="savedEdges.length > 0" density="compact">
            <v-list-item
              v-for="edge in savedEdges"
              :key="edge._key"
              class="py-1"
            >
              <template #prepend>
                <v-icon
                  :color="edge.overlap ? 'success' : 'secondary'"
                  size="small"
                >
                  {{ edge.overlap ? 'mdi-link-variant' : 'mdi-arrow-right' }}
                </v-icon>
              </template>
              <v-list-item-title class="text-body-2">
                {{ edge.from }} → {{ edge.to }}
              </v-list-item-title>
              <v-list-item-subtitle class="text-caption">
                {{ edge.min_transit_s }}s – {{ edge.max_transit_s }}s
              </v-list-item-subtitle>
              <template #append>
                <v-btn icon="mdi-pencil" size="x-small" variant="text" color="primary" @click="stageForEdit(edge)" />
              </template>
            </v-list-item>
          </v-list>
          <div v-else class="pa-6 text-center">
            <v-card flat>
              <v-card-text class="text-grey">No saved edges</v-card-text>
            </v-card>
          </div>
        </v-card>

        <!-- Skipped cameras -->
        <v-alert
          v-if="skippedCameraIds.length > 0"
          type="info"
          density="compact"
          variant="tonal"
          class="mt-3"
        >
          {{ skippedCameraIds.length }} camera(s) skipped (no polygon):
          {{ skippedCameraIds.join(', ') }}. Calibrate or place them to include in inference.
        </v-alert>
      </v-col>
    </v-row>

    <!-- Add / Edit edge dialog -->
    <v-dialog v-model="dialog" max-width="500" persistent>
      <v-card>
        <DialogHeader
          icon="mdi-graph"
          :label="editingIdx !== null ? 'Edit' : 'Add'"
          title="Adjacency Edge"
          @close="dialog = false"
        />
        <v-card-text>
          <v-autocomplete
            v-model="form.from"
            :items="cameraOptions"
            item-title="name"
            item-value="id"
            label="From Camera"
            variant="outlined"
            class="mb-3"
            clearable
          />
          <v-autocomplete
            v-model="form.to"
            :items="cameraOptions"
            item-title="name"
            item-value="id"
            label="To Camera"
            variant="outlined"
            class="mb-3"
            clearable
          />
          <v-alert
            v-if="sameOverlapGroupHint"
            type="info"
            density="compact"
            variant="tonal"
            class="mb-3"
          >
            These cameras share overlap group "{{ sameOverlapGroupHint }}".
            <v-btn size="x-small" variant="text" @click="applyGroupDefaults">
              Apply overlap defaults (0–2 s)
            </v-btn>
          </v-alert>
          <v-row dense>
            <v-col cols="6">
              <v-text-field
                v-model.number="form.min_transit_s"
                label="Min transit (s)"
                variant="outlined"
                type="number" min="0" step="0.5"
                density="compact"
              />
            </v-col>
            <v-col cols="6">
              <v-text-field
                v-model.number="form.max_transit_s"
                label="Max transit (s)"
                variant="outlined"
                type="number" min="0" step="1"
                density="compact"
              />
            </v-col>
          </v-row>
          <v-alert
            v-if="form.max_transit_s < form.min_transit_s"
            type="error"
            density="compact"
            class="mt-2"
          >
            Max transit must be at least min transit.
          </v-alert>
          <v-switch v-model="form.overlap" label="Field-of-view overlap" color="success" class="mt-1" />
          <div class="text-caption text-medium-emphasis mt-1">
            Enable when cameras physically share a viewing zone (e.g. two cameras covering the same doorway).
            The cross-camera resolver will treat detections as potentially simultaneous rather than sequential.
          </div>
          <v-switch
            v-model="form.addSymmetric"
            label="Also add reverse direction (B&rarr;A)"
            color="primary"
            class="mt-1"
            :disabled="editingIdx !== null"
          />
          <div class="text-caption text-medium-emphasis mt-1">
            Most adjacencies are bidirectional. Uncheck only for one-way flows
            (e.g. exit-only camera).
          </div>
        </v-card-text>
        <DialogFooter
          hint="Adjacency edges define directed transit paths between cameras. A&rarr;B is not the same as B&rarr;A. For most physical adjacencies, add both directions."
          :confirm-label="editingIdx !== null ? 'Update' : 'Add'"
          :confirm-disabled="form.max_transit_s < form.min_transit_s || !form.from || !form.to || form.from === form.to"
          @cancel="dialog = false"
          @confirm="commitEdge"
        />
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snack" :color="snackColor" timeout="3500">{{ snackText }}</v-snackbar>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { cts } from "../../services/cts.js";
import { household } from "../../services/household.js";
import { useNotify } from "../../composables/useNotify.js";
import DialogHeader from "../../components/common/DialogHeader.vue";
import DialogFooter from "../../components/common/DialogFooter.vue";

const { snack, snackText, snackColor, notify } = useNotify();

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/**
 * @typedef {{ camera_id: string, camera_name: string, has_homography: boolean, visibility_polygon: number[][] | null }} CameraPolygon
 * @typedef {{ cameras: CameraPolygon[], floor_meters_per_pixel: number | null, floor_plan_width_px: number | null, floor_plan_height_px: number | null }} VisibilityPolygonsPayload
 * @typedef {{ from: string, to: string, min_transit_s: number, max_transit_s: number, overlap: boolean }} AdjacencyEdge
 * @typedef {{ id: string, name: string }} CameraOption
 */

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

/** @type {import('vue').Ref<CameraOption[]>} */
const cameraOptions = ref([]);
/** @type {import('vue').Ref<CameraPolygon[]>} */
const coverageCameras = ref([]);
const overlapGroups = ref([]);
/** @type {import('vue').Ref<AdjacencyEdge[]>} */
const savedEdges = ref([]);
/** @type {import('vue').Ref<AdjacencyEdge[]>} */
const stagedEdges = ref([]);
const skippedCameraIds = ref([]);
const loadingEdges = ref(false);
const inferring = ref(false);
const saving = ref(false);

// Map image state
const mapImgRef = ref(null);
const mapImgLoaded = ref(false);
const mapImgW = ref(0);
const mapImgH = ref(0);
const floorPlanUrl = ref(null);

// Dialog state
const dialog = ref(false);
const editingIdx = ref(null);
const form = ref(emptyForm());

// ---------------------------------------------------------------------------
// Derived
// ---------------------------------------------------------------------------

const hasPolygons = computed(() =>
  coverageCameras.value.some((c) => c.visibility_polygon)
);

const calibratedWithoutPolygons = computed(() =>
  coverageCameras.value.filter((c) => c.has_homography && !c.visibility_polygon)
);

const allEdgesForMap = computed(() => {
  const saved = savedEdges.value.map((e) => ({ ...e, _staged: false }));
  const staged = stagedEdges.value.map((e) => ({ ...e, _staged: true }));
  const byKey = {};
  for (const e of [...saved, ...staged]) byKey[e._key] = e;
  return Object.values(byKey);
});

const centroidMap = computed(() => {
  const result = {};
  for (const cam of coverageCameras.value) {
    if (!cam.visibility_polygon || !mapImgW.value) continue;
    const pts = cam.visibility_polygon;
    const sx = pts.reduce((s, [x]) => s + x, 0);
    const sy = pts.reduce((s, [, y]) => s + y, 0);
    result[cam.camera_id] = [
      (sx / pts.length) * mapImgW.value,
      (sy / pts.length) * mapImgH.value,
    ];
  }
  return result;
});

const sameOverlapGroupHint = computed(() => {
  if (!form.value.from || !form.value.to) return null;
  for (const grp of overlapGroups.value) {
    const ids = grp.camera_ids || [];
    if (ids.includes(form.value.from) && ids.includes(form.value.to)) {
      return grp.name || grp.camera_ids.join(", ");
    }
  }
  return null;
});

// ---------------------------------------------------------------------------
// Boundary validation
// ---------------------------------------------------------------------------

/**
 * Validate and sanitize the visibility polygons API response.
 *
 * The backend contract is VisibilityPolygonsResponse:
 *   { cameras: [{ camera_id: string, camera_name: string,
 *                 visibility_polygon: number[][] | null }],
 *     floor_meters_per_pixel: number | null, ... }
 *
 * Rejects entries that don't match the contract and logs what was wrong
 * so the operator can fix the source (database content, serialization).
 *
 * @param {unknown} raw - raw JSON parsed from GET /calibration/visibility_polygons
 * @returns {CameraPolygon[]}
 */
function validateVisibilityPolygons(raw) {
  if (!raw || typeof raw !== "object") {
    console.warn("cts_visibility_polygons_not_object", raw);
    return [];
  }

  const cameras = raw.cameras;
  if (!Array.isArray(cameras)) {
    console.warn("cts_visibility_polygons_cameras_not_array", typeof cameras, cameras);
    return [];
  }

  /** @type {CameraPolygon[]} */
  const valid = [];
  for (let i = 0; i < cameras.length; i++) {
    const c = cameras[i];
    if (!c || typeof c !== "object") {
      console.warn("cts_visibility_polygons_entry_not_object", i, c);
      continue;
    }
    if (typeof c.camera_id !== "string") {
      console.warn("cts_visibility_polygons_entry_missing_camera_id", i, c);
      continue;
    }
    // visibility_polygon is either null or an array of [number, number] pairs.
    // Accept anything truthy that is an array; null/undefined → null.
    const poly = Array.isArray(c.visibility_polygon) ? c.visibility_polygon : null;
    valid.push({
      camera_id: c.camera_id,
      camera_name: typeof c.camera_name === "string" ? c.camera_name : c.camera_id,
      has_homography: c.has_homography === true,
      visibility_polygon: poly,
    });
  }

  if (valid.length !== cameras.length) {
    console.warn(
      "cts_visibility_polygons_dropped_entries",
      `kept ${valid.length} / dropped ${cameras.length - valid.length}`,
    );
  }

  return valid;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function emptyForm() {
  return { from: "", to: "", min_transit_s: 0.5, max_transit_s: 30, overlap: false, addSymmetric: true };
}

function toSvgPoints(polygon) {
  if (!mapImgW.value || !mapImgH.value) return "";
  return polygon.map(([x, y]) => `${(x * mapImgW.value).toFixed(1)},${(y * mapImgH.value).toFixed(1)}`).join(" ");
}

function centroidOf(cameraId) {
  return centroidMap.value[cameraId] ?? [0, 0];
}

function onMapImgLoad() {
  if (!mapImgRef.value) return;
  mapImgW.value = mapImgRef.value.naturalWidth;
  mapImgH.value = mapImgRef.value.naturalHeight;
  mapImgLoaded.value = true;
}

function applyGroupDefaults() {
  form.value.min_transit_s = 0;
  form.value.max_transit_s = 2;
  form.value.overlap = true;
}

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------

async function loadAll() {
  await Promise.all([loadCameras(), loadCoverage(), loadSavedEdges(), loadFloorPlan(), loadOverlapGroups()]);
}

async function loadCameras() {
  try {
    cameraOptions.value = await cts.getCameras();
  } catch {
    // orchestrator may be offline in dev
  }
}

async function loadCoverage() {
  try {
    const data = await cts.getVisibilityPolygons();
    coverageCameras.value = validateVisibilityPolygons(data);
  } catch (err) {
    console.warn("cts_visibility_polygons_load_failed", err);
    coverageCameras.value = [];
  }
}

async function loadSavedEdges() {
  loadingEdges.value = true;
  try {
    const data = await cts.getAdjacency();
    savedEdges.value = (data.edges || []).map((e) => ({
      ...e,
      _key: `${e.from}->${e.to}`,
    }));
  } catch {
    savedEdges.value = [];
  } finally {
    loadingEdges.value = false;
  }
}

async function loadFloorPlan() {
  try {
    const data = await household.getFloorPlan();
    if (data?.floor_plan_url) {
      floorPlanUrl.value = data.floor_plan_url;
    }
  } catch {
    floorPlanUrl.value = null;
  }
}

async function loadOverlapGroups() {
  try {
    overlapGroups.value = await cts.getOverlapGroups();
  } catch {
    overlapGroups.value = [];
  }
}

// ---------------------------------------------------------------------------
// Inference
// ---------------------------------------------------------------------------

async function inferAdjacency() {
  inferring.value = true;
  try {
    const data = await cts.getInferredAdjacency();
    skippedCameraIds.value = data.skipped_camera_ids || [];
    overlapGroups.value = data.overlap_groups || [];

    const savedKeys = new Set(savedEdges.value.map((e) => e._key));
    const newEdges = (data.edges || [])
      .filter((e) => !savedKeys.has(`${e.from}->${e.to}`))
      .map((e) => ({
        from: e.from,
        to: e.to,
        min_transit_s: e.min_transit_s,
        max_transit_s: e.max_transit_s,
        overlap: e.overlap,
        _key: `${e.from}->${e.to}`,
      }));

    stagedEdges.value = newEdges;

    if (newEdges.length === 0 && data.edges.length > 0) {
      notify("All inferred edges are already saved.", "info");
    } else {
      notify(`${newEdges.length} edge(s) staged from inference. Review and save.`, "success");
    }

    if (skippedCameraIds.value.length > 0) {
      notify(
        `${skippedCameraIds.value.length} camera(s) skipped (no polygon): ${skippedCameraIds.value.join(", ")}`,
        "warning",
      );
    }
  } catch (e) {
    notify(e.message, "error");
  } finally {
    inferring.value = false;
  }
}

// ---------------------------------------------------------------------------
// Edge CRUD
// ---------------------------------------------------------------------------

function openCreate() {
  editingIdx.value = null;
  form.value = emptyForm();
  dialog.value = true;
}

function openEdit(edge) {
  editingIdx.value = stagedEdges.value.indexOf(edge);
  form.value = { ...edge };
  dialog.value = true;
}

function stageForEdit(savedEdge) {
  const existingIdx = stagedEdges.value.findIndex(
    (e) => e.from === savedEdge.from && e.to === savedEdge.to
  );
  if (existingIdx >= 0) {
    editingIdx.value = existingIdx;
    form.value = { ...stagedEdges.value[existingIdx] };
  } else {
    const staged = { ...savedEdge };
    stagedEdges.value.push(staged);
    editingIdx.value = stagedEdges.value.length - 1;
    form.value = { ...staged };
  }
  dialog.value = true;
}

function commitEdge() {
  const edge = { ...form.value, _key: `${form.value.from}->${form.value.to}` };
  if (editingIdx.value !== null) {
    stagedEdges.value[editingIdx.value] = edge;
  } else {
    stagedEdges.value.push(edge);

    if (form.value.addSymmetric) {
      const reverseEdge = {
        from: form.value.to,
        to: form.value.from,
        min_transit_s: form.value.min_transit_s,
        max_transit_s: form.value.max_transit_s,
        overlap: form.value.overlap,
        _key: `${form.value.to}->${form.value.from}`,
      };
      stagedEdges.value.push(reverseEdge);
    }
  }
  dialog.value = false;
}

function removeEdge(edge) {
  stagedEdges.value = stagedEdges.value.filter((e) => e !== edge);
}

async function saveAdjacency() {
  saving.value = true;
  try {
    const byKey = {};
    for (const e of [...savedEdges.value, ...stagedEdges.value]) {
      byKey[e._key] = e;
    }
    const payload = Object.values(byKey).map(({ _key: _k, _staged: _s, ...rest }) => rest);
    await cts.postAdjacency(payload);
    notify("Adjacency graph saved");
    stagedEdges.value = [];
    await loadSavedEdges();
  } catch (e) {
    notify(e.message, "error");
  } finally {
    saving.value = false;
  }
}

onMounted(loadAll);
</script>
