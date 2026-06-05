<template>
  <div>
    <v-alert v-if="!floorPlanUrl" type="warning" variant="tonal" class="mb-4">
      Upload a floor plan before configuring door zones.
    </v-alert>
    <v-alert v-else-if="!scaleReady" type="warning" variant="tonal" class="mb-4">
      <div class="d-flex align-center flex-wrap ga-2">
        <span>Set the floor-plan scale first. Zones cannot detect crossings without it.</span>
        <v-btn size="small" variant="text" @click="$emit('set-scale')">Floor Plan</v-btn>
      </div>
    </v-alert>

    <v-row>
      <v-col cols="12" md="8">
        <CcSpatialEditor
          class="marauders-no-paint"
          :model-value="polygonShapes"
          :image-url="floorPlanUrl"
          image-class="cc-floor-plan-background-image marauders-no-paint"
          mode="polygon"
          coord-space="normalized"
          :natural-width="canvasW"
          :natural-height="canvasH"
          :readonly="!canEditPolygon"
          :max-shapes="1"
          :min-points="3"
          :show-footer="false"
          :show-zoom="true"
          @update:model-value="onPolygonUpdate"
          @select="activeTool = 'polygon'"
        >
          <template #overlay="{ toCanvas, contentRect }">
            <g class="door-zone-context">
              <template v-for="room in drawableRooms" :key="`room-${room.id}`">
                <MaraudersInkPolygon
                  v-if="maraudersState.enabled"
                  :points="room.floor_polygon"
                  :canvas-w="contentRect.width"
                  :canvas-h="contentRect.height"
                  :seed-key="`dzroom-${room.id}`"
                />
                <polygon
                  v-else
                  :points="pointsString(room.floor_polygon, toCanvas)"
                  class="door-zone-room"
                />
              </template>

              <g
                v-for="zone in zones"
                :key="`zone-${zone.id}`"
                class="door-zone-existing"
                @click.stop="loadZone(zone)"
              >
                <MaraudersInkPolygon
                  v-if="maraudersState.enabled && zone.polygon?.length >= 3"
                  :points="zone.polygon"
                  :canvas-w="contentRect.width"
                  :canvas-h="contentRect.height"
                  :seed-key="`dzzone-${zone.id}`"
                  :label="zone.name"
                />
                <template v-else-if="zone.polygon?.length >= 3">
                  <polygon
                    :points="pointsString(zone.polygon, toCanvas)"
                    class="door-zone-existing__polygon"
                  />
                  <text
                    v-bind="mapLabelAttrs"
                    :x="toCanvas(centroid(zone.polygon)).x"
                    :y="toCanvas(centroid(zone.polygon)).y"
                    class="door-zone-label"
                  >{{ zone.name }}</text>
                </template>
                <line
                  v-if="zone.direction_vec"
                  v-bind="zoneArrowAttrs(zone, toCanvas)"
                  class="door-zone-existing__arrow"
                  marker-end="url(#door-zone-arrow)"
                />
              </g>

            </g>
            <defs>
              <marker
                id="door-zone-arrow"
                markerWidth="10"
                markerHeight="10"
                refX="8"
                refY="5"
                orient="auto"
                markerUnits="strokeWidth"
              >
                <path d="M0,0 L10,5 L0,10 Z" class="door-zone-arrow-head" />
              </marker>
            </defs>
          </template>
          <template #overlay-top="{ toCanvas, contentRect }">
            <line
              v-if="directionLine"
              v-bind="directionLineAttrs(toCanvas)"
              class="door-zone-direction"
              marker-end="url(#door-zone-arrow)"
            />
            <circle
              v-if="directionStart"
              :cx="toCanvas(directionStart).x"
              :cy="toCanvas(directionStart).y"
              r="5"
              class="door-zone-direction__point"
            />
            <circle
              v-if="directionEnd"
              :cx="toCanvas(directionEnd).x"
              :cy="toCanvas(directionEnd).y"
              r="5"
              class="door-zone-direction__point"
            />
            <rect
              v-if="activeTool === 'direction' && scaleReady"
              class="door-zone-direction-hit"
              x="0"
              y="0"
              :width="contentRect.width"
              :height="contentRect.height"
              @click.stop="onDirectionClick"
            />
          </template>
        </CcSpatialEditor>
      </v-col>

      <v-col cols="12" md="4">
        <v-card variant="tonal" class="pa-3 mb-4">
          <div class="d-flex align-center mb-3">
            <span class="text-subtitle-2">{{ editingZone ? "Edit Zone" : "New Zone" }}</span>
            <v-spacer />
            <v-btn v-if="editingZone" size="small" variant="text" @click="resetForm">
              New
            </v-btn>
          </div>

          <v-text-field
            v-model="form.name"
            label="Name"
            variant="outlined"
            density="compact"
            class="mb-3"
          />
          <v-select
            v-model="form.kind"
            :items="kindItems"
            item-title="title"
            item-value="value"
            label="Type"
            variant="outlined"
            density="compact"
            class="mb-3"
          />
          <v-select
            v-model="form.inside_room_id"
            :items="rooms"
            item-title="name"
            item-value="id"
            label="Inside Room"
            variant="outlined"
            density="compact"
            class="mb-3"
          />
          <v-select
            v-model="form.outside_room_id"
            :items="rooms"
            item-title="name"
            item-value="id"
            label="Outside Room"
            variant="outlined"
            density="compact"
            class="mb-3"
          />

          <div class="d-flex ga-2 mb-3">
            <v-btn
              size="small"
              :variant="activeTool === 'polygon' ? 'flat' : 'tonal'"
              color="primary"
              @click="activeTool = 'polygon'"
            >
              Polygon
            </v-btn>
            <v-btn
              size="small"
              :variant="activeTool === 'direction' ? 'flat' : 'tonal'"
              color="primary"
              :disabled="!scaleReady"
              @click="startDirectionTool"
            >
              Direction
            </v-btn>
            <v-btn
              size="small"
              variant="tonal"
              :disabled="!scaleReady"
              @click="useRectangle"
            >
              Rectangle
            </v-btn>
          </div>

          <div class="text-caption text-medium-emphasis mb-3">
            {{ polygon.length }} vertices · {{ directionVec ? "direction set" : "direction needed" }}
          </div>

          <div class="d-flex ga-2">
            <v-btn variant="text" @click="resetForm">Cancel</v-btn>
            <v-spacer />
            <v-btn
              color="primary"
              variant="flat"
              :loading="saving"
              :disabled="!canSave"
              @click="saveZone"
            >
              {{ editingZone ? "Save" : "Create" }}
            </v-btn>
          </div>
        </v-card>

        <v-card variant="tonal" class="pa-3">
          <div class="text-subtitle-2 mb-2">Existing Zones</div>
          <div v-if="loading" class="text-caption text-medium-emphasis">Loading...</div>
          <div v-else-if="!zones.length" class="text-body-2 text-medium-emphasis">
            No door zones configured.
          </div>
          <v-list v-else density="compact">
            <v-list-item
              v-for="zone in zones"
              :key="zone.id"
              class="rounded-lg"
              @click="loadZone(zone)"
            >
              <template #prepend>
                <v-icon size="18" color="primary">mdi-door-open</v-icon>
              </template>
              <v-list-item-title>{{ zone.name }}</v-list-item-title>
              <v-list-item-subtitle>
                {{ roomName(zone.inside_room_id) }} / {{ roomName(zone.outside_room_id) }}
              </v-list-item-subtitle>
              <template #append>
                <v-btn
                  icon="mdi-delete"
                  size="small"
                  variant="text"
                  color="error"
                  @click.stop="deleteZone(zone)"
                />
              </template>
            </v-list-item>
          </v-list>
        </v-card>
      </v-col>
    </v-row>

    <v-dialog v-model="confirmDialog" max-width="400" persistent>
      <v-card rounded="xl">
        <v-card-title>{{ confirmTitle }}</v-card-title>
        <v-card-text>{{ confirmText }}</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="onCancel">{{ cancelLabel }}</v-btn>
          <v-btn :color="confirmColor" variant="flat" @click="onConfirm">{{ confirmLabel }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { MAP_LABEL } from "@/composables/useAnnotationStyle.js";
import { useConfirm } from "@/composables/useConfirm.js";
import { useNotify } from "@/composables/useNotify.js";
import { useMaraudersMode } from "@/composables/useMaraudersMode.js";
import MaraudersInkPolygon from "@/components/marauders/MaraudersInkPolygon.vue";
import { cts } from "@/services/cts.js";
import CcSpatialEditor from "@/components/common/CcSpatialEditor.vue";

const props = defineProps({
  rooms: { type: Array, default: () => [] },
  zones: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  floorPlanUrl: { type: String, default: null },
  canvasW: { type: Number, required: true },
  canvasH: { type: Number, required: true },
  fpMpp: { type: Number, default: null },
});

const emit = defineEmits(["saved", "deleted", "set-scale"]);

const { notify } = useNotify();
const {
  confirmDialog,
  confirmTitle,
  confirmText,
  confirmLabel,
  cancelLabel,
  confirmColor,
  showConfirm,
  onConfirm,
  onCancel,
} = useConfirm();

const kindItems = [
  { title: "Door", value: "door" },
  { title: "Threshold", value: "threshold" },
];
const mapLabelAttrs = MAP_LABEL.attrs();
const { state: maraudersState } = useMaraudersMode();
const form = reactive({
  name: "",
  kind: "door",
  inside_room_id: null,
  outside_room_id: null,
});
const polygon = ref([]);
const directionStart = ref(null);
const directionEnd = ref(null);
const activeTool = ref("polygon");
const editingZone = ref(null);
const saving = ref(false);

const scaleReady = computed(() => Boolean(props.floorPlanUrl && props.canvasW > 0 && props.canvasH > 0 && props.fpMpp));
const canEditPolygon = computed(() => scaleReady.value && activeTool.value !== "direction");
const drawableRooms = computed(() => props.rooms.filter((room) => room.floor_polygon?.length >= 3));
const polygonShapes = computed(() => {
  if (!polygon.value.length) return [];
  return [{ id: "door-zone-polygon", type: "polygon", points: polygon.value }];
});
const directionVec = computed(() => {
  if (!directionStart.value || !directionEnd.value) return null;
  return normalizedDirection(directionStart.value, directionEnd.value);
});
const directionLine = computed(() => directionStart.value && directionEnd.value);
const canSave = computed(() =>
  scaleReady.value
  && form.name.trim().length > 0
  && form.inside_room_id != null
  && form.outside_room_id != null
  && form.inside_room_id !== form.outside_room_id
  && polygon.value.length >= 3
  && directionVec.value != null
);

function round4(value) {
  return Number(value.toFixed(4));
}

function roundPoint(point) {
  return [round4(Math.max(0, Math.min(1, point[0]))), round4(Math.max(0, Math.min(1, point[1])))];
}

function normalizedDirection(start, end) {
  const dx = end[0] - start[0];
  const dy = end[1] - start[1];
  const len = Math.hypot(dx, dy);
  if (len <= 0.0001) return null;
  return [round4(dx / len), round4(dy / len)];
}

function centroid(points) {
  if (!points?.length) return [0.5, 0.5];
  return [
    points.reduce((sum, [x]) => sum + x, 0) / points.length,
    points.reduce((sum, [, y]) => sum + y, 0) / points.length,
  ];
}

function pointsString(points, toCanvas) {
  return points.map((point) => {
    const canvas = toCanvas(point);
    return `${canvas.x},${canvas.y}`;
  }).join(" ");
}

function roomName(roomId) {
  return props.rooms.find((room) => room.id === roomId)?.name ?? `room ${roomId}`;
}

function onPolygonUpdate(shapes) {
  polygon.value = (shapes[0]?.points ?? []).map(roundPoint);
}

function startDirectionTool() {
  activeTool.value = "direction";
  directionStart.value = null;
  directionEnd.value = null;
}

function onDirectionClick(event) {
  if (!scaleReady.value) return;
  const rect = event.currentTarget.getBoundingClientRect();
  const point = roundPoint([
    (event.clientX - rect.left) / rect.width,
    (event.clientY - rect.top) / rect.height,
  ]);
  if (!directionStart.value || directionEnd.value) {
    directionStart.value = point;
    directionEnd.value = null;
    return;
  }
  directionEnd.value = point;
  activeTool.value = "polygon";
}

function useRectangle() {
  polygon.value = [
    [0.42, 0.42],
    [0.58, 0.42],
    [0.58, 0.58],
    [0.42, 0.58],
  ];
  activeTool.value = "polygon";
}

function directionLineAttrs(toCanvas) {
  const start = toCanvas(directionStart.value);
  const end = toCanvas(directionEnd.value);
  return { x1: start.x, y1: start.y, x2: end.x, y2: end.y };
}

function zoneArrowAttrs(zone, toCanvas) {
  const center = centroid(zone.polygon);
  const [dx, dy] = zone.direction_vec;
  const start = toCanvas([center[0] - dx * 0.06, center[1] - dy * 0.06]);
  const end = toCanvas([center[0] + dx * 0.06, center[1] + dy * 0.06]);
  return { x1: start.x, y1: start.y, x2: end.x, y2: end.y };
}

function directionEndpointsFromVector(points, vec) {
  if (!points?.length || !vec) return [null, null];
  const center = centroid(points);
  return [
    roundPoint([center[0] - vec[0] * 0.06, center[1] - vec[1] * 0.06]),
    roundPoint([center[0] + vec[0] * 0.06, center[1] + vec[1] * 0.06]),
  ];
}

function loadZone(zone) {
  editingZone.value = zone;
  form.name = zone.name ?? "";
  form.kind = zone.kind ?? "door";
  form.inside_room_id = zone.inside_room_id;
  form.outside_room_id = zone.outside_room_id;
  polygon.value = (zone.polygon ?? []).map(roundPoint);
  const [start, end] = directionEndpointsFromVector(polygon.value, zone.direction_vec);
  directionStart.value = start;
  directionEnd.value = end;
  activeTool.value = "polygon";
}

function resetForm() {
  editingZone.value = null;
  form.name = "";
  form.kind = "door";
  form.inside_room_id = null;
  form.outside_room_id = null;
  polygon.value = [];
  directionStart.value = null;
  directionEnd.value = null;
  activeTool.value = "polygon";
}

function bodyFromForm() {
  return {
    name: form.name.trim(),
    kind: form.kind,
    polygon: polygon.value.map(roundPoint),
    inside_room_id: form.inside_room_id,
    outside_room_id: form.outside_room_id,
    direction_vec: directionVec.value,
  };
}

async function saveZone() {
  if (!canSave.value) return;
  saving.value = true;
  try {
    if (editingZone.value) {
      await cts.updateTransitZone(editingZone.value.id, bodyFromForm());
      notify.success("Door zone updated");
    } else {
      await cts.createTransitZone(bodyFromForm());
      notify.success("Door zone created");
    }
    resetForm();
    emit("saved");
  } catch (error) {
    notify.error(error.message || "Failed to save door zone");
  } finally {
    saving.value = false;
  }
}

async function deleteZone(zone) {
  const ok = await showConfirm(
    "Delete Door Zone",
    `Delete "${zone.name}"? Transit detection for this doorway will stop.`
  );
  if (!ok) return;
  try {
    await cts.deleteTransitZone(zone.id);
    notify.success("Door zone deleted");
    if (editingZone.value?.id === zone.id) resetForm();
    emit("deleted");
  } catch (error) {
    notify.error(error.message || "Failed to delete door zone");
  }
}

defineExpose({
  form,
  polygon,
  directionStart,
  directionEnd,
  activeTool,
  canSave,
  saveZone,
  loadZone,
  deleteZone,
  resetForm,
});
</script>

<style scoped>
.door-zone-room {
  fill: color-mix(in srgb, var(--cc-brand) 6%, transparent);
  stroke: color-mix(in srgb, var(--cc-brand) 34%, transparent);
  stroke-width: 1.5;
  pointer-events: none;
}

.door-zone-existing__polygon {
  fill: color-mix(in srgb, var(--cc-warning) 16%, transparent);
  stroke: var(--cc-warning);
  stroke-width: 2;
  cursor: pointer;
}

.door-zone-existing__arrow,
.door-zone-direction {
  stroke: var(--cc-error);
  stroke-width: 3;
  pointer-events: none;
}

.door-zone-direction__point,
.door-zone-arrow-head {
  fill: var(--cc-error);
}

.door-zone-label {
  font-size: 12px;
  font-weight: 500;
  text-anchor: middle;
  pointer-events: none;
}

.door-zone-direction-hit {
  fill: transparent;
  pointer-events: all;
  cursor: crosshair;
}
</style>
