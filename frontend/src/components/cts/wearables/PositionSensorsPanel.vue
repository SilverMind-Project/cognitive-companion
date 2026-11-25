<template>
  <div data-test="position-sensors-panel">
    <v-alert
      v-if="!floorPlanReady"
      type="info"
      variant="tonal"
      class="mb-4"
      data-test="position-sensors-no-floor-plan"
    >
      Upload the household floor plan and set its measured scale before registering position
      sensors. Their tracks are positions on that plan.
    </v-alert>

    <v-card class="glass-card">
      <v-card-title class="d-flex align-center">
        <span>Position sensors</span>
        <v-spacer />
        <v-btn
          color="primary"
          prepend-icon="mdi-plus"
          :disabled="!floorPlanReady"
          data-test="add-position-sensor"
          @click="openAdd"
        >
          Register sensor
        </v-btn>
      </v-card-title>
      <v-card-subtitle class="pb-2">
        Radars and room LiDARs report where people are, never who. Tracks from a sensor that is not
        registered and active here are ignored.
      </v-card-subtitle>
      <v-table density="comfortable">
        <thead>
          <tr>
            <th>Label</th>
            <th>Sensor ID</th>
            <th>Kind</th>
            <th>Room</th>
            <th>Position (m)</th>
            <th>Yaw</th>
            <th>Calibration residual</th>
            <th>Active</th>
            <th />
          </tr>
        </thead>
        <tbody>
          <tr v-if="sensors.length === 0">
            <td colspan="9" class="text-medium-emphasis" data-test="position-sensors-empty">
              No position sensors registered.
            </td>
          </tr>
          <tr v-for="sensor in sensors" :key="sensor.id" data-test="position-sensor-row">
            <td>{{ sensor.label }}</td>
            <td>
              <code>{{ sensor.sensor_id }}</code>
            </td>
            <td>{{ modalityLabel(sensor.modality) }}</td>
            <td>{{ sensor.room_name ?? "No room" }}</td>
            <td>{{ formatPosition(sensor) }}</td>
            <td>{{ sensor.yaw_deg === null ? "Floor frame" : `${sensor.yaw_deg} deg` }}</td>
            <td>{{ sensor.calibration_residual_m.toFixed(2) }} m</td>
            <td>
              <v-switch
                :model-value="sensor.is_active"
                hide-details
                density="compact"
                :disabled="saving"
                :data-test="`position-sensor-active-${sensor.sensor_id}`"
                @update:model-value="emit('update-sensor', sensor.id, { is_active: !!$event })"
              />
            </td>
            <td class="text-right">
              <v-btn
                icon="mdi-pencil-outline"
                variant="text"
                size="small"
                :aria-label="`Edit ${sensor.label}`"
                :data-test="`position-sensor-edit-${sensor.sensor_id}`"
                @click="openEdit(sensor)"
              />
              <v-btn
                icon="mdi-delete-outline"
                variant="text"
                size="small"
                :aria-label="`Remove ${sensor.label}`"
                :data-test="`position-sensor-delete-${sensor.sensor_id}`"
                @click="emit('delete-sensor', sensor.id)"
              />
            </td>
          </tr>
        </tbody>
      </v-table>
    </v-card>

    <AppDialog
      v-model="showDialog"
      size="md"
      persistent
      icon="mdi-radar"
      label="Wearables"
      :title="isEditing ? 'Edit position sensor' : 'Register position sensor'"
      :confirm-label="isEditing ? 'Save' : 'Register'"
      :confirm-loading="saving"
      :confirm-disabled="!canSubmit"
      @confirm="submitForm"
    >
      <div class="px-6 py-5">
        <v-row dense class="mb-2">
          <v-col cols="6">
            <v-text-field
              v-model="draft.label"
              label="Label"
              placeholder="Bathroom radar"
              data-test="new-sensor-label"
            />
          </v-col>
          <v-col cols="6">
            <v-text-field
              v-model="draft.sensor_id"
              label="Sensor ID"
              placeholder="radar-bathroom-1"
              :disabled="isEditing"
              hint="The ID the sensor's gateway publishes under: lowercase letters, digits, . _ -"
              persistent-hint
              :error-messages="sensorIdError"
              data-test="new-sensor-id"
            />
          </v-col>
        </v-row>
        <v-row dense class="mb-2">
          <v-col cols="6">
            <v-select
              v-model="draft.modality"
              label="Kind"
              :items="modalityOptions"
              item-title="title"
              item-value="value"
              data-test="new-sensor-modality"
            />
          </v-col>
          <v-col cols="6">
            <v-select
              v-model="draft.room_id"
              label="Room it covers"
              :items="rooms"
              item-title="name"
              item-value="id"
              data-test="new-sensor-room"
            />
          </v-col>
        </v-row>
        <v-row dense class="mb-2">
          <v-col cols="4">
            <v-text-field
              v-model.number="draft.x_m"
              type="number"
              label="X (m)"
              :hint="
                floorWidthM ? `0 to ${floorWidthM.toFixed(2)} m from the plan's left edge` : ''
              "
              persistent-hint
              data-test="new-sensor-x"
            />
          </v-col>
          <v-col cols="4">
            <v-text-field
              v-model.number="draft.y_m"
              type="number"
              label="Y (m)"
              :hint="
                floorHeightM ? `0 to ${floorHeightM.toFixed(2)} m from the plan's top edge` : ''
              "
              persistent-hint
              data-test="new-sensor-y"
            />
          </v-col>
          <v-col cols="4">
            <v-text-field
              v-model="draft.yaw_deg"
              type="number"
              label="Yaw (deg, optional)"
              hint="Only for a gateway that reports in the sensor's own frame"
              persistent-hint
              :error-messages="yawError"
              data-test="new-sensor-yaw"
            />
          </v-col>
        </v-row>
        <v-text-field
          v-model.number="draft.calibration_residual_m"
          type="number"
          label="Calibration residual (m)"
          hint="How far off the sensor's floor positions can be after mounting; tracking never trusts it more"
          persistent-hint
          class="mt-2"
          data-test="new-sensor-residual"
        />
      </div>
    </AppDialog>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import AppDialog from "@/components/common/AppDialog.vue";
import type { RoomOut } from "@/services/modules/rooms";
import type {
  PositionSensorCreate,
  PositionSensorOut,
  PositionSensorUpdate,
} from "@/services/modules/wearables";

type Modality = PositionSensorCreate["modality"];

const props = defineProps<{
  sensors: PositionSensorOut[];
  rooms: RoomOut[];
  floorPlanReady: boolean;
  floorWidthM: number | null;
  floorHeightM: number | null;
  saving: boolean;
}>();

const emit = defineEmits<{
  "create-sensor": [body: PositionSensorCreate];
  "update-sensor": [sensorUuid: string, body: PositionSensorUpdate];
  "delete-sensor": [sensorUuid: string];
}>();

// Mirrors cts_contracts.SENSOR_ID_PATTERN; the backend validates it again.
const SENSOR_ID_RE = /^[a-z0-9][a-z0-9_.-]{0,63}$/;

const modalityOptions: { title: string; value: Modality }[] = [
  { title: "mmWave radar", value: "mmwave_radar" },
  { title: "LiDAR", value: "lidar" },
  { title: "Other", value: "other" },
];

function modalityLabel(value: Modality): string {
  return modalityOptions.find((o) => o.value === value)?.title ?? value;
}

function formatPosition(sensor: PositionSensorOut): string {
  if (sensor.x_m === null || sensor.x_m === undefined) return "No scale";
  return `${sensor.x_m.toFixed(2)}, ${(sensor.y_m ?? 0).toFixed(2)}`;
}

const showDialog = ref(false);
const editingSensorId = ref<string | null>(null);
const isEditing = computed(() => editingSensorId.value !== null);
const draft = reactive({
  label: "",
  sensor_id: "",
  modality: "mmwave_radar" as Modality,
  room_id: null as number | null,
  x_m: 0,
  y_m: 0,
  yaw_deg: "" as string | number,
  calibration_residual_m: 0.1,
});

const sensorIdError = computed(() =>
  isEditing.value || draft.sensor_id === "" || SENSOR_ID_RE.test(draft.sensor_id)
    ? []
    : ["Use 1 to 64 lowercase letters, digits, or . _ - (no spaces or colons)"],
);

const parsedYaw = computed<number | null>(() => {
  const raw = String(draft.yaw_deg ?? "").trim();
  return raw === "" ? null : Number(raw);
});

const yawValid = computed(
  () =>
    parsedYaw.value === null ||
    (Number.isFinite(parsedYaw.value) && parsedYaw.value >= -180 && parsedYaw.value < 180),
);

const yawError = computed(() =>
  yawValid.value ? [] : ["Enter -180 to < 180 deg, or leave blank for floor frame"],
);

function inRange(value: number, max: number | null): boolean {
  return (
    typeof value === "number" &&
    Number.isFinite(value) &&
    value >= 0 &&
    (max === null || value <= max)
  );
}

const canSubmit = computed(
  () =>
    props.floorPlanReady &&
    draft.label.trim().length > 0 &&
    (isEditing.value || SENSOR_ID_RE.test(draft.sensor_id)) &&
    draft.room_id !== null &&
    inRange(draft.x_m, props.floorWidthM) &&
    inRange(draft.y_m, props.floorHeightM) &&
    typeof draft.calibration_residual_m === "number" &&
    Number.isFinite(draft.calibration_residual_m) &&
    draft.calibration_residual_m > 0 &&
    draft.calibration_residual_m <= 1 &&
    yawValid.value,
);

function openAdd() {
  editingSensorId.value = null;
  Object.assign(draft, {
    label: "",
    sensor_id: "",
    modality: "mmwave_radar",
    room_id: null,
    x_m: 0,
    y_m: 0,
    yaw_deg: "",
    calibration_residual_m: 0.1,
  });
  showDialog.value = true;
}

function openEdit(sensor: PositionSensorOut) {
  editingSensorId.value = sensor.id;
  Object.assign(draft, {
    label: sensor.label,
    sensor_id: sensor.sensor_id,
    modality: sensor.modality,
    room_id: sensor.room_id,
    x_m: sensor.x_m ?? 0,
    y_m: sensor.y_m ?? 0,
    yaw_deg: sensor.yaw_deg === null || sensor.yaw_deg === undefined ? "" : sensor.yaw_deg,
    calibration_residual_m: sensor.calibration_residual_m,
  });
  showDialog.value = true;
}

function submitForm() {
  if (!canSubmit.value || draft.room_id === null) return;
  const widthM = props.floorWidthM ?? 1;
  const heightM = props.floorHeightM ?? 1;
  const xNorm = Math.min(1, draft.x_m / widthM);
  const yNorm = Math.min(1, draft.y_m / heightM);
  if (editingSensorId.value !== null) {
    emit("update-sensor", editingSensorId.value, {
      label: draft.label.trim(),
      modality: draft.modality,
      room_id: draft.room_id,
      x_norm: xNorm,
      y_norm: yNorm,
      yaw_deg: parsedYaw.value,
      calibration_residual_m: draft.calibration_residual_m,
    });
  } else {
    emit("create-sensor", {
      sensor_id: draft.sensor_id,
      label: draft.label.trim(),
      modality: draft.modality,
      room_id: draft.room_id,
      x_norm: xNorm,
      y_norm: yNorm,
      yaw_deg: parsedYaw.value,
      calibration_residual_m: draft.calibration_residual_m,
      is_active: true,
    });
  }
  showDialog.value = false;
}
</script>
