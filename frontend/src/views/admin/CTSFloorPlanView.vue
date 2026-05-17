<template>
  <div>
    <!-- Header -->
    <div class="d-flex align-center mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Floor Plan</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Upload a floor plan image and draw room polygons. Active people appear as dots in real time.
        </div>
      </div>
      <v-spacer />
      <v-btn-group variant="tonal" density="compact" class="mr-3">
        <v-btn
          :variant="mode === 'live' ? 'flat' : 'tonal'"
          color="primary"
          @click="mode = 'live'"
        >
          Live
        </v-btn>
        <v-btn
          :variant="mode === 'edit' ? 'flat' : 'tonal'"
          color="primary"
          @click="mode = 'edit'"
        >
          Edit Rooms
        </v-btn>
        <v-btn
          :variant="mode === 'upload' ? 'flat' : 'tonal'"
          color="primary"
          @click="mode = 'upload'"
        >
          Floor Plan
        </v-btn>
      </v-btn-group>
      <v-btn
        v-if="mode === 'live'"
        :icon="paused ? 'mdi-play' : 'mdi-pause'"
        variant="text"
        @click="paused = !paused"
      />
    </div>

    <!-- ── Upload panel ───────────────────────────────────────────────────── -->
    <template v-if="mode === 'upload'">
      <v-card variant="flat" border class="mb-4">
        <v-card-title>Upload Floor Plan Image</v-card-title>
        <v-card-text>
          <v-alert type="info" variant="tonal" density="compact" class="mb-4 text-body-2">
            Upload a top-down floor plan of the home. The system will overlay person positions on
            it using homography data from each camera. JPEG or PNG, up to 10 MB.
          </v-alert>

          <v-row dense>
            <v-col cols="12" md="6">
              <v-file-input
                v-model="uploadFile"
                label="Floor plan image"
                accept="image/jpeg,image/png"
                variant="outlined"
                prepend-icon="mdi-image-outline"
                class="mb-3"
                density="compact"
                hide-details
              />
            </v-col>
            <v-col cols="12" md="2">
              <v-text-field
                v-model.number="uploadWidth"
                label="Width (px)"
                variant="outlined"
                density="compact"
                type="number"
                hide-details
              />
            </v-col>
            <v-col cols="12" md="2">
              <v-text-field
                v-model.number="uploadHeight"
                label="Height (px)"
                variant="outlined"
                density="compact"
                type="number"
                hide-details
              />
            </v-col>
            <v-col cols="12" md="2">
              <v-text-field
                v-model.number="uploadMpp"
                label="m/px"
                variant="outlined"
                density="compact"
                type="number"
                step="0.001"
                hint="Metres per pixel"
                persistent-hint
              />
            </v-col>
          </v-row>
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn
            color="primary"
            variant="flat"
            :loading="uploading"
            :disabled="!uploadFile && !uploadWidth && !uploadHeight && !uploadMpp"
            prepend-icon="mdi-upload"
            @click="uploadFloorPlan"
          >
            Save
          </v-btn>
        </v-card-actions>
      </v-card>

      <!-- Current floor plan preview -->
      <v-card v-if="floorPlanUrl" variant="flat" border>
        <v-card-title>Current Floor Plan</v-card-title>
        <v-card-text>
          <img :src="floorPlanUrl" class="floor-plan-preview" alt="Floor plan" />
          <div class="text-caption text-medium-emphasis mt-2">
            <template v-if="fpWidth && fpHeight">{{ fpWidth }} × {{ fpHeight }} px</template>
            <template v-if="fpMpp"> · {{ fpMpp }} m/px</template>
          </div>
        </v-card-text>
      </v-card>
    </template>

    <!-- ── Edit rooms panel ───────────────────────────────────────────────── -->
    <template v-else-if="mode === 'edit'">
      <v-alert type="info" variant="tonal" density="compact" class="mb-4 text-body-2">
        Select a room, then draw its polygon on the floor plan below. Right-click a vertex to
        delete it. Drag vertices to adjust. Click "Save polygon" to persist.
      </v-alert>

      <v-row>
        <v-col cols="12" md="3">
          <v-list density="compact" nav>
            <v-list-subheader>Rooms</v-list-subheader>
            <v-list-item
              v-for="room in rooms"
              :key="room.id"
              :title="room.name"
              :subtitle="room.floor_polygon ? `${room.floor_polygon.length} pts` : 'No polygon'"
              :value="room.id"
              :active="editingRoom?.id === room.id"
              rounded="lg"
              @click="selectRoom(room)"
            >
              <template #append>
                <v-icon v-if="room.floor_polygon" color="success" size="small">mdi-check-circle</v-icon>
              </template>
            </v-list-item>
            <v-list-item v-if="rooms.length === 0" class="text-medium-emphasis text-body-2">
              No rooms configured. Add rooms in the Rooms view.
            </v-list-item>
          </v-list>
        </v-col>

        <v-col cols="12" md="9">
          <v-card>
            <v-card-title class="d-flex align-center">
              <span>{{ editingRoom ? editingRoom.name : 'Select a room' }}</span>
              <v-spacer />
              <v-btn
                v-if="editingRoom && editPolygon.length > 0"
                size="small"
                variant="text"
                color="error"
                class="mr-2"
                @click="editPolygon = []"
              >
                Clear
              </v-btn>
              <v-btn
                v-if="editingRoom"
                color="primary"
                variant="flat"
                size="small"
                :loading="savingRoom"
                :disabled="editPolygon.length < 3"
                @click="saveRoomPolygon"
              >
                Save polygon
              </v-btn>
            </v-card-title>
            <v-card-text class="pa-0">
              <PolygonOnSnapshot
                :image-url="floorPlanUrl"
                :model-value="editPolygon"
                :min-points="3"
                :readonly="!editingRoom"
                @update:model-value="editPolygon = $event"
              />
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>
    </template>

    <!-- ── Live view ─────────────────────────────────────────────────────── -->
    <template v-else>
      <div ref="canvasContainer" class="floor-plan-canvas">
        <svg
          ref="svgEl"
          :viewBox="`0 0 ${canvasW} ${canvasH}`"
          preserveAspectRatio="xMidYMid meet"
          class="floor-plan-svg"
        >
          <!-- Background floor plan image -->
          <image
            v-if="floorPlanUrl"
            :href="floorPlanUrl"
            :width="canvasW"
            :height="canvasH"
            opacity="0.45"
          />

          <!-- Room polygons -->
          <g v-for="room in rooms" :key="room.id">
            <polygon
              v-if="room.floor_polygon && room.floor_polygon.length >= 3"
              :points="room.floor_polygon.map(([x, y]) => `${x * canvasW},${y * canvasH}`).join(' ')"
              class="room-poly"
            />
            <!-- Room label at centroid -->
            <text
              v-if="room.floor_polygon && room.floor_polygon.length >= 3"
              :x="centroidX(room.floor_polygon) * canvasW"
              :y="centroidY(room.floor_polygon) * canvasH"
              class="room-label"
            >
              {{ room.name }}
            </text>
          </g>

          <!-- Identity trails and dots -->
          <g v-for="(trail, identityId) in identityTrails" :key="identityId">
            <polyline
              v-if="trail.points.length > 1"
              :points="trail.points.map(p => `${p.x},${p.y}`).join(' ')"
              :stroke="trail.color"
              stroke-width="2.5"
              fill="none"
              opacity="0.45"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
            <circle
              v-if="trail.current"
              :cx="trail.current.x"
              :cy="trail.current.y"
              r="8"
              :fill="trail.color"
              stroke="#fff"
              stroke-width="2"
            />
            <text
              v-if="trail.current"
              :x="trail.current.x + 12"
              :y="trail.current.y - 8"
              :fill="trail.color"
              font-size="12"
              font-weight="bold"
              class="identity-label"
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
            No active tracks. Waiting for live data…
          </text>
        </svg>
      </div>
    </template>

    <v-snackbar v-model="snack" :color="snackColor" timeout="3500">{{ snackText }}</v-snackbar>
  </div>
</template>

<script setup>
import { onMounted, ref, shallowRef } from "vue";
import { identityColor } from "@/composables/useIdentityColor";
import { useCtsWebSocket } from "@/composables/useCtsWebSocket";
import { useNotify } from "@/composables/useNotify";
import { household } from "@/services/household";
import PolygonOnSnapshot from "@/components/cts/PolygonOnSnapshot.vue";

const { snack, snackText, snackColor, notify } = useNotify();

// ── Floor plan state ───────────────────────────────────────────────────────
const floorPlanUrl = ref(null);
const fpWidth = ref(null);
const fpHeight = ref(null);
const fpMpp = ref(null);

// ── Upload state ───────────────────────────────────────────────────────────
const uploading = ref(false);
const uploadFile = ref(null);
const uploadWidth = ref(null);
const uploadHeight = ref(null);
const uploadMpp = ref(null);

// ── Rooms state ────────────────────────────────────────────────────────────
const rooms = ref([]);
const editingRoom = ref(null);
const editPolygon = ref([]);
const savingRoom = ref(false);

// ── Live view state ────────────────────────────────────────────────────────
const canvasW = ref(1200);
const canvasH = ref(800);
const paused = ref(false);
const identityTrails = shallowRef({});
const MAX_TRAIL_POINTS = 60;
const TRAIL_MAX_AGE_MS = 30_000;

// ── Mode ──────────────────────────────────────────────────────────────────
const mode = ref("live");

// ── WS ───────────────────────────────────────────────────────────────────
function onWsMessage(msg) {
  if (msg?.type === "cts_live_frame") onLiveFrame(msg);
}
useCtsWebSocket(onWsMessage);

// ── Helpers ───────────────────────────────────────────────────────────────
function centroidX(polygon) {
  return polygon.reduce((s, [x]) => s + x, 0) / polygon.length;
}
function centroidY(polygon) {
  return polygon.reduce((s, [, y]) => s + y, 0) / polygon.length;
}

// ── Load ─────────────────────────────────────────────────────────────────
async function loadFloorPlan() {
  try {
    const data = await household.getFloorPlan();
    floorPlanUrl.value = data.floor_plan_url;
    fpWidth.value = data.floor_plan_width;
    fpHeight.value = data.floor_plan_height;
    fpMpp.value = data.floor_meters_per_pixel;
    if (data.floor_plan_width && data.floor_plan_height) {
      canvasW.value = data.floor_plan_width;
      canvasH.value = data.floor_plan_height;
    }
  } catch {
    // Not configured yet — not an error.
  }
}

async function loadRooms() {
  try {
    rooms.value = await household.getRooms();
  } catch (e) {
    notify(e.message, "error");
  }
}

// ── Upload ────────────────────────────────────────────────────────────────
async function uploadFloorPlan() {
  uploading.value = true;
  try {
    const fd = new FormData();
    if (uploadFile.value) fd.append("file", uploadFile.value[0] ?? uploadFile.value);
    if (uploadWidth.value) fd.append("floor_plan_width", String(uploadWidth.value));
    if (uploadHeight.value) fd.append("floor_plan_height", String(uploadHeight.value));
    if (uploadMpp.value) fd.append("floor_meters_per_pixel", String(uploadMpp.value));
    const data = await household.postFloorPlan(fd);
    floorPlanUrl.value = data.floor_plan_url;
    fpWidth.value = data.floor_plan_width;
    fpHeight.value = data.floor_plan_height;
    fpMpp.value = data.floor_meters_per_pixel;
    if (data.floor_plan_width && data.floor_plan_height) {
      canvasW.value = data.floor_plan_width;
      canvasH.value = data.floor_plan_height;
    }
    notify("Floor plan saved");
    uploadFile.value = null;
  } catch (e) {
    notify(e.message, "error");
  } finally {
    uploading.value = false;
  }
}

// ── Edit rooms ────────────────────────────────────────────────────────────
function selectRoom(room) {
  editingRoom.value = room;
  editPolygon.value = room.floor_polygon ? JSON.parse(JSON.stringify(room.floor_polygon)) : [];
}

async function saveRoomPolygon() {
  if (!editingRoom.value || editPolygon.value.length < 3) return;
  savingRoom.value = true;
  try {
    const updated = await household.putRoom(editingRoom.value.id, {
      ...editingRoom.value,
      floor_polygon: editPolygon.value,
    });
    const idx = rooms.value.findIndex((r) => r.id === updated.id);
    if (idx >= 0) rooms.value[idx] = updated;
    editingRoom.value = updated;
    notify("Room polygon saved");
  } catch (e) {
    notify(e.message, "error");
  } finally {
    savingRoom.value = false;
  }
}

// ── Live frame handler ────────────────────────────────────────────────────
function onLiveFrame(frame) {
  if (paused.value) return;

  const detections = frame.detections || [];
  const identities = frame.identities || {};
  const now = Date.now();

  const trails = { ...identityTrails.value };

  // Expire stale trails.
  for (const id of Object.keys(trails)) {
    if (now - (trails[id].lastSeen ?? 0) > TRAIL_MAX_AGE_MS) {
      delete trails[id];
    }
  }

  for (const det of detections) {
    const gtId = det.global_track_id;
    const identityInfo = identities[gtId];
    if (!identityInfo) continue;

    const identityId = identityInfo[0] || gtId;

    // Prefer homography-mapped floor coords if available.
    let fx, fy;
    if (det.floor_x != null && det.floor_y != null && fpMpp.value && fpWidth.value && fpHeight.value) {
      fx = (det.floor_x / (fpWidth.value * fpMpp.value)) * canvasW.value;
      fy = (det.floor_y / (fpHeight.value * fpMpp.value)) * canvasH.value;
    } else {
      const bbox = det.bbox;
      const frameW = frame.frame_width || 640;
      const frameH = frame.frame_height || 480;
      fx = bbox ? ((bbox.x_min + bbox.x_max) / 2) / frameW * canvasW.value : 0;
      fy = bbox ? bbox.y_max / frameH * canvasH.value : 0;
    }

    let trail = trails[identityId];
    if (!trail) {
      trail = { points: [], current: null, color: identityColor(identityId), displayName: identityId, lastSeen: now };
      trails[identityId] = trail;
    }
    trail.lastSeen = now;
    trail.displayName = identityInfo[1] || identityId;
    trail.points.push({ x: fx, y: fy, ts: now });
    if (trail.points.length > MAX_TRAIL_POINTS) trail.points = trail.points.slice(-MAX_TRAIL_POINTS);
    trail.current = { x: fx, y: fy };
  }

  identityTrails.value = trails;
}

onMounted(() => {
  loadFloorPlan();
  loadRooms();
  // WS lifecycle is handled inside useCtsWebSocket (connects on call, disconnects on unmount).
});
</script>

<style scoped>
.floor-plan-canvas {
  background: var(--cc-surface-2);
  border: 1px solid var(--cc-divider-strong);
  border-radius: 8px;
  overflow: hidden;
  min-height: 480px;
}

.floor-plan-svg {
  width: 100%;
  height: 100%;
  min-height: 480px;
}

.floor-plan-preview {
  display: block;
  max-width: 100%;
  max-height: 400px;
  border-radius: 4px;
  object-fit: contain;
}

.room-poly {
  fill: rgba(99, 102, 241, 0.12);
  stroke: var(--cc-brand);
  stroke-width: 1.5;
  stroke-dasharray: 6 4;
}

.room-label {
  fill: var(--cc-brand);
  font-size: 11px;
  font-weight: 600;
  text-anchor: middle;
  dominant-baseline: central;
  pointer-events: none;
}

.identity-label {
  pointer-events: none;
}
</style>
