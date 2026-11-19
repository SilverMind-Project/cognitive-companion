<template>
  <div>
    <!-- Blocking empty state when floor plan or measured scale is missing -->
    <v-card v-if="!floorPlanReady" class="glass-card pa-6 text-center" data-test="no-floor-plan">
      <v-icon size="48" color="warning" class="mb-3">mdi-floor-plan</v-icon>
      <div class="text-h6 font-weight-bold mb-2">Floor plan and scale required</div>
      <div class="text-body-2 text-medium-emphasis mb-4">
        RF nodes must be placed on a floor plan with a tape-validated scale so every receiver and
        ranging anchor shares the same coordinate frame as the cameras.
      </div>
      <v-btn
        color="primary"
        variant="flat"
        prepend-icon="mdi-floor-plan"
        to="/admin/tracking?panel=live-floor"
        data-test="go-floor-plan-btn"
      >
        Upload floor plan and set scale
      </v-btn>
    </v-card>

    <v-row v-else>
      <v-col cols="12" lg="7">
        <v-card class="glass-card">
          <v-card-title class="d-flex align-center justify-space-between flex-wrap ga-2">
            <div>
              <div class="text-subtitle-1 font-weight-bold">RF Node Placement</div>
              <div class="text-caption text-medium-emphasis">
                Click the floor plan to place or reposition the active node, or drag any marker.
                Floor size: {{ floorWidthM?.toFixed(2) }} m x {{ floorHeightM?.toFixed(2) }} m.
              </div>
            </div>
            <v-btn
              size="small"
              variant="tonal"
              prepend-icon="mdi-plus"
              data-test="new-node-btn"
              @click="startNewNode"
            >
              New RF node
            </v-btn>
          </v-card-title>
          <v-divider />
          <v-card-text>
            <div ref="canvasWrapperRef" class="rf-floor-canvas" data-test="rf-floor-canvas">
              <img
                v-if="floorPlanUrl"
                :src="floorPlanUrl"
                alt="Household floor plan"
                class="rf-floor-img"
                draggable="false"
              />
              <svg
                ref="svgRef"
                class="rf-floor-svg"
                viewBox="0 0 1000 1000"
                preserveAspectRatio="none"
                data-test="rf-floor-svg"
                @click="onCanvasClick"
                @mousemove="onSvgMouseMove"
                @mouseup="onSvgMouseUp"
                @mouseleave="onSvgMouseUp"
              >
                <!-- Room polygons -->
                <polygon
                  v-for="room in roomsWithPolygons"
                  :key="room.id"
                  :points="polygonPoints(room.floor_polygon)"
                  class="rf-room-polygon"
                />

                <!-- Existing RF nodes -->
                <g
                  v-for="node in nodes"
                  :key="node.id"
                  class="rf-node-marker"
                  :class="{
                    'rf-node-marker--selected': selectedNodeId === node.id,
                    'rf-node-marker--anchor': node.node_role === 'ranging_anchor',
                  }"
                  :data-test="`rf-node-marker-${node.anchor_id}`"
                  @mousedown.stop="startDrag(node)"
                  @click.stop="selectNode(node)"
                >
                  <circle :cx="node.x_norm * 1000" :cy="node.y_norm * 1000" r="16" />
                  <text :x="node.x_norm * 1000" :y="node.y_norm * 1000 - 22" text-anchor="middle">
                    {{ node.label }}
                  </text>
                </g>

                <!-- Draft marker for a new node -->
                <g
                  v-if="!selectedNodeId"
                  class="rf-node-marker rf-node-marker--draft"
                  data-test="rf-node-draft-marker"
                >
                  <circle :cx="form.x_norm * 1000" :cy="form.y_norm * 1000" r="14" />
                </g>
              </svg>
            </div>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" lg="5">
        <v-card class="glass-card mb-4">
          <v-card-title class="text-subtitle-1 font-weight-bold">
            {{ selectedNodeId ? "Edit RF Node" : "Add RF Node" }}
          </v-card-title>
          <v-divider />
          <v-card-text>
            <v-text-field
              v-model="form.anchor_id"
              label="Node ID (anchor_id)"
              :disabled="Boolean(selectedNodeId)"
              class="mb-2"
              data-test="node-anchor-id"
            />
            <v-text-field v-model="form.label" label="Label" class="mb-2" data-test="node-label" />
            <v-text-field
              v-model="form.adapter_id"
              label="Adapter ID"
              hint="Configured rf-ingress adapter instance (for example ble-home or uwb-watch)"
              persistent-hint
              class="mb-2"
              data-test="node-adapter-id"
            />
            <v-row dense class="mb-2">
              <v-col cols="6">
                <v-select
                  v-model="form.node_role"
                  label="Role"
                  :items="roleItems"
                  item-title="title"
                  item-value="value"
                  data-test="node-role"
                />
              </v-col>
              <v-col cols="6">
                <v-select
                  v-model="form.technology"
                  label="Technology"
                  :items="technologyItems"
                  item-title="title"
                  item-value="value"
                  data-test="node-technology"
                />
              </v-col>
            </v-row>
            <v-row dense class="mb-2">
              <v-col cols="6">
                <v-select
                  v-model="form.room_id"
                  label="Room (optional)"
                  :items="rooms"
                  item-title="name"
                  item-value="id"
                  clearable
                  data-test="node-room"
                />
              </v-col>
              <v-col cols="6">
                <v-text-field
                  v-model.number="form.z_m"
                  type="number"
                  step="0.05"
                  min="0"
                  max="4"
                  label="Mount height z (m)"
                  data-test="node-z-m"
                />
              </v-col>
            </v-row>

            <div class="text-caption text-medium-emphasis mb-3" data-test="node-coords-readout">
              Normalized: ({{ form.x_norm.toFixed(4) }}, {{ form.y_norm.toFixed(4) }})
              <span v-if="floorWidthM && floorHeightM">
                | Floor: ({{ (form.x_norm * floorWidthM).toFixed(2) }} m,
                {{ (form.y_norm * floorHeightM).toFixed(2) }} m)
              </span>
            </div>

            <!-- Optional UWB FiRa parameters when technology is UWB -->
            <template v-if="form.technology === 'uwb'">
              <v-divider class="my-3" />
              <div class="text-caption font-weight-bold mb-2">UWB FiRa Session Parameters</div>
              <v-row dense class="mb-2">
                <v-col cols="4">
                  <v-text-field
                    v-model="form.uwb_address_hex"
                    label="Short addr"
                    placeholder="00:01"
                    data-test="node-uwb-addr"
                  />
                </v-col>
                <v-col cols="4">
                  <v-select
                    v-model="form.uwb_channel"
                    label="Channel"
                    :items="[5, 9]"
                    data-test="node-uwb-channel"
                  />
                </v-col>
                <v-col cols="4">
                  <v-text-field
                    v-model.number="form.uwb_preamble_index"
                    type="number"
                    min="9"
                    max="32"
                    label="Preamble"
                    data-test="node-uwb-preamble"
                  />
                </v-col>
              </v-row>
            </template>

            <div class="d-flex justify-end ga-2 mt-3">
              <v-btn
                v-if="selectedNodeId"
                color="error"
                variant="tonal"
                :loading="saving"
                data-test="delete-node-btn"
                @click="$emit('delete-node', selectedNodeId)"
              >
                Delete
              </v-btn>
              <v-btn
                color="primary"
                variant="flat"
                :loading="saving"
                :disabled="!canSaveNode"
                data-test="save-node-btn"
                @click="saveNode"
              >
                {{ selectedNodeId ? "Save changes" : "Place node" }}
              </v-btn>
            </div>
          </v-card-text>
        </v-card>

        <!-- Tape-distance survey verification -->
        <v-card class="glass-card" data-test="survey-card">
          <v-card-title class="text-subtitle-1 font-weight-bold">
            Tape-distance survey check
          </v-card-title>
          <v-divider />
          <v-card-text>
            <div class="text-caption text-medium-emphasis mb-3">
              Enter tape distances to at least two walls or placed nodes. Discrepancies above 0.20 m
              indicate a scale or placement error.
            </div>
            <v-row v-for="(m, idx) in surveyMeasurements" :key="idx" dense class="mb-2">
              <v-col cols="4">
                <v-select
                  v-model="m.reference_kind"
                  :items="surveyRefKinds"
                  item-title="title"
                  item-value="value"
                  label="Ref"
                  density="compact"
                  hide-details
                  @update:model-value="onRefKindChange(m)"
                />
              </v-col>
              <v-col cols="4">
                <v-select
                  v-model="m.reference_id"
                  :items="m.reference_kind === 'wall' ? wallOptions : nodeRefOptions"
                  item-title="title"
                  item-value="value"
                  label="Target"
                  density="compact"
                  hide-details
                />
              </v-col>
              <v-col cols="4">
                <v-text-field
                  v-model.number="m.measured_m"
                  type="number"
                  step="0.05"
                  min="0"
                  label="Tape (m)"
                  density="compact"
                  hide-details
                  :data-test="`survey-measured-${idx}`"
                />
              </v-col>
            </v-row>
            <div class="d-flex justify-end mt-2">
              <v-btn
                size="small"
                variant="tonal"
                color="primary"
                :loading="checkingSurvey"
                data-test="run-survey-btn"
                @click="submitSurvey"
              >
                Check distances
              </v-btn>
            </div>

            <v-alert
              v-if="surveyResult"
              :type="surveyResult.warning ? 'warning' : 'success'"
              variant="tonal"
              class="mt-3"
              data-test="survey-result-alert"
            >
              <div v-if="surveyResult.warning">
                Position disagrees with tape measurements by up to
                <strong>{{ surveyResult.max_discrepancy_m.toFixed(2) }} m</strong>
                (threshold {{ surveyResult.tolerance_m.toFixed(2) }} m). Re-check floor scale or
                node click position.
              </div>
              <div v-else>
                All tape measurements agree within
                <strong>{{ surveyResult.max_discrepancy_m.toFixed(2) }} m</strong>.
              </div>
            </v-alert>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { useChartTheme } from "@/composables/useChartTheme.js";
import type { RoomOut } from "@/services/modules/rooms";
import type {
  RfNodeCreate,
  RfNodeOut,
  RfNodeSurveyCheckOut,
  RfNodeSurveyCheckRequest,
  RfNodeUpdate,
} from "@/services/modules/wearables";

const props = defineProps<{
  floorPlanReady: boolean;
  floorPlanUrl: string | null;
  floorWidthM: number | null;
  floorHeightM: number | null;
  nodes: RfNodeOut[];
  rooms: RoomOut[];
  saving: boolean;
  surveyResult: RfNodeSurveyCheckOut | null;
  checkingSurvey: boolean;
}>();

const emit = defineEmits<{
  "create-node": [body: RfNodeCreate];
  "update-node": [nodeId: string, body: RfNodeUpdate];
  "delete-node": [nodeId: string];
  "run-survey": [body: RfNodeSurveyCheckRequest];
  "clear-survey": [];
}>();

// Bind into shared design-token theme bridge for bespoke floor-plan SVG rendering.
useChartTheme();

const svgRef = ref<SVGSVGElement | null>(null);
const selectedNodeId = ref<string | null>(null);
const draggingNodeId = ref<string | null>(null);

const form = reactive({
  anchor_id: "",
  label: "",
  adapter_id: "ble-home",
  node_role: "receiver" as "receiver" | "ranging_anchor",
  technology: "ble_rssi" as "ble_rssi" | "ble_channel_sounding" | "uwb",
  room_id: null as number | null,
  x_norm: 0.5,
  y_norm: 0.5,
  z_m: 1.5,
  uwb_address_hex: null as string | null,
  uwb_channel: 9 as number | null,
  uwb_preamble_index: 10 as number | null,
});

const roleItems = [
  { title: "Receiver (BLE)", value: "receiver" },
  { title: "Ranging anchor", value: "ranging_anchor" },
];

const technologyItems = [
  { title: "BLE RSSI", value: "ble_rssi" },
  { title: "BLE Channel Sounding", value: "ble_channel_sounding" },
  { title: "UWB", value: "uwb" },
];

const surveyRefKinds = [
  { title: "Wall", value: "wall" },
  { title: "Node", value: "node" },
];

const wallOptions = [
  { title: "Left wall", value: "left" },
  { title: "Right wall", value: "right" },
  { title: "Top wall", value: "top" },
  { title: "Bottom wall", value: "bottom" },
];

const nodeRefOptions = computed(() =>
  props.nodes.map((n) => ({ title: `${n.label} (${n.anchor_id})`, value: n.anchor_id })),
);

const surveyMeasurements = reactive<
  Array<{ reference_kind: "wall" | "node"; reference_id: string; measured_m: number }>
>([
  { reference_kind: "wall", reference_id: "left", measured_m: 1.0 },
  { reference_kind: "wall", reference_id: "top", measured_m: 1.0 },
]);

const roomsWithPolygons = computed(() =>
  props.rooms.filter((r) => Array.isArray(r.floor_polygon) && r.floor_polygon.length >= 3),
);

const canSaveNode = computed(
  () =>
    form.anchor_id.trim().length > 0 &&
    form.label.trim().length > 0 &&
    form.adapter_id.trim().length > 0,
);

function polygonPoints(poly: unknown): string {
  if (!Array.isArray(poly)) return "";
  return poly
    .filter((pt): pt is [number, number] => Array.isArray(pt) && pt.length >= 2)
    .map((pt) => `${(pt[0] * 1000).toFixed(1)},${(pt[1] * 1000).toFixed(1)}`)
    .join(" ");
}

function startNewNode() {
  selectedNodeId.value = null;
  form.anchor_id = "";
  form.label = "";
  form.adapter_id = "ble-home";
  form.node_role = "receiver";
  form.technology = "ble_rssi";
  form.room_id = null;
  form.x_norm = 0.5;
  form.y_norm = 0.5;
  form.z_m = 1.5;
  form.uwb_address_hex = null;
  form.uwb_channel = 9;
  form.uwb_preamble_index = 10;
  emit("clear-survey");
}

function selectNode(node: RfNodeOut) {
  selectedNodeId.value = node.id;
  form.anchor_id = node.anchor_id;
  form.label = node.label;
  form.adapter_id = node.adapter_id;
  form.node_role = node.node_role;
  form.technology = node.technology;
  form.room_id = node.room_id ?? null;
  form.x_norm = node.x_norm;
  form.y_norm = node.y_norm;
  form.z_m = node.z_m;
  form.uwb_address_hex = node.uwb_address_hex ?? null;
  form.uwb_channel = node.uwb_channel ?? 9;
  form.uwb_preamble_index = node.uwb_preamble_index ?? 10;
  emit("clear-survey");
}

function normalizedCoordsFromEvent(evt: MouseEvent): { x: number; y: number } | null {
  const svg = svgRef.value;
  if (!svg) return null;
  const rect = svg.getBoundingClientRect();
  if (!rect.width || !rect.height) return null;
  const x = Math.min(1, Math.max(0, (evt.clientX - rect.left) / rect.width));
  const y = Math.min(1, Math.max(0, (evt.clientY - rect.top) / rect.height));
  return { x: Number(x.toFixed(4)), y: Number(y.toFixed(4)) };
}

function onCanvasClick(evt: MouseEvent) {
  const pos = normalizedCoordsFromEvent(evt);
  if (!pos) return;
  form.x_norm = pos.x;
  form.y_norm = pos.y;
  emit("clear-survey");
}

function startDrag(node: RfNodeOut) {
  selectNode(node);
  draggingNodeId.value = node.id;
}

function onSvgMouseMove(evt: MouseEvent) {
  if (!draggingNodeId.value) return;
  const pos = normalizedCoordsFromEvent(evt);
  if (!pos) return;
  form.x_norm = pos.x;
  form.y_norm = pos.y;
}

function onSvgMouseUp() {
  if (!draggingNodeId.value) return;
  const nodeId = draggingNodeId.value;
  draggingNodeId.value = null;
  emit("update-node", nodeId, { x_norm: form.x_norm, y_norm: form.y_norm });
}

function saveNode() {
  if (!canSaveNode.value) return;
  const uwbFields =
    form.technology === "uwb"
      ? {
          uwb_address_hex: form.uwb_address_hex?.trim() || null,
          uwb_channel: form.uwb_channel,
          uwb_preamble_index: form.uwb_preamble_index,
        }
      : {
          uwb_address_hex: null,
          uwb_channel: null,
          uwb_preamble_index: null,
        };
  if (selectedNodeId.value) {
    emit("update-node", selectedNodeId.value, {
      label: form.label.trim(),
      adapter_id: form.adapter_id.trim(),
      node_role: form.node_role,
      technology: form.technology,
      room_id: form.room_id,
      x_norm: form.x_norm,
      y_norm: form.y_norm,
      z_m: form.z_m,
      ...uwbFields,
    });
  } else {
    emit("create-node", {
      anchor_id: form.anchor_id.trim(),
      label: form.label.trim(),
      adapter_id: form.adapter_id.trim(),
      node_role: form.node_role,
      technology: form.technology,
      room_id: form.room_id,
      x_norm: form.x_norm,
      y_norm: form.y_norm,
      z_m: form.z_m,
      is_active: true,
      ...uwbFields,
    });
  }
}

function onRefKindChange(item: { reference_kind: "wall" | "node"; reference_id: string }) {
  item.reference_id =
    item.reference_kind === "wall" ? "left" : (nodeRefOptions.value[0]?.value ?? "");
}

function submitSurvey() {
  emit("run-survey", {
    x_norm: form.x_norm,
    y_norm: form.y_norm,
    z_m: form.z_m,
    measurements: surveyMeasurements.map((m) => ({
      reference_kind: m.reference_kind,
      reference_id: m.reference_id,
      measured_m: Number(m.measured_m),
    })),
  });
}
</script>

<style scoped>
.rf-floor-canvas {
  position: relative;
  width: 100%;
  aspect-ratio: 4 / 3;
  border: 1px solid var(--cc-border);
  border-radius: var(--cc-radius-md);
  overflow: hidden;
  background: var(--cc-surface-2);
}

.rf-floor-img {
  width: 100%;
  height: 100%;
  object-fit: fill;
  display: block;
  user-select: none;
}

.rf-floor-svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  cursor: crosshair;
}

.rf-room-polygon {
  fill: var(--cc-chart-1);
  fill-opacity: 0.1;
  stroke: var(--cc-chart-1);
  stroke-width: 2;
  pointer-events: none;
}

.rf-node-marker {
  cursor: grab;
}

.rf-node-marker circle {
  fill: var(--cc-chart-2);
  stroke: var(--cc-surface-1);
  stroke-width: 3;
}

.rf-node-marker--anchor circle {
  fill: var(--cc-chart-3);
}

.rf-node-marker--selected circle {
  stroke: var(--cc-text-1);
  stroke-width: 4;
}

.rf-node-marker--draft circle {
  fill: var(--cc-chart-4);
  fill-opacity: 0.7;
  stroke-dasharray: 4 3;
}

.rf-node-marker text {
  fill: var(--cc-text-1);
  font-size: 24px;
  font-weight: 500;
  paint-order: stroke;
  stroke: var(--cc-surface-1);
  stroke-width: 4px;
}
</style>
