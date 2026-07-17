<template>
  <div>
    <div class="text-subtitle-2 mb-2">Additional Cameras</div>
    <v-text-field
      :model-value="imagesPerSensor"
      type="number"
      :min="1"
      label="Default frames per camera"
      hint="Per-camera default; individual cameras can override below"
      persistent-hint
      density="compact"
      class="mb-4"
      @update:model-value="updateImagesPerSensor"
    />

    <v-data-table
      :headers="[
        { title: 'Camera Sensor', key: 'sensor_id' },
        { title: 'Frames', key: 'frames', width: 120 },
        { title: '', key: 'actions', width: 60, sortable: false },
      ]"
      :items="cameraRows"
      item-key="sensor_id"
      show-select
      hide-default-footer
      class="mb-4"
    >
      <template #item.frames="{ item }">
        <v-text-field
          :model-value="item.frames"
          type="number"
          :min="1"
          density="compact"
          hide-details
          class="v-text-field--flush-label"
          :class="item.isOverride ? '' : 'text-grey'"
          @update:model-value="emitSensorFrameLimit(item.sensor_id, Number($event))"
        />
      </template>
      <template #item.actions="{ item }">
        <v-btn icon size="x-small" variant="text" @click="removeCamera(item.sensor_id)">
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </template>
    </v-data-table>

    <v-combobox
      v-model="newCameraId"
      :items="availableCameraItems"
      label="Add Camera"
      clearable
      hide-details
      class="mb-4"
      @update:model-value="addCamera"
    />

    <v-checkbox
      v-model="showRooms"
      label="Pull from rooms (all cameras in these rooms)"
      hide-details
      class="mb-2"
    />
    <v-combobox
      v-if="showRooms"
      :model-value="roomNames"
      :items="availableRooms"
      label="Rooms"
      multiple
      chips
      closable-chips
      hide-details
      class="mb-4"
      @update:model-value="emitRoomNames"
    />
  </div>
</template>

<script setup>
import { ref, computed } from "vue";

const props = defineProps({
  modelValue: { type: Object, required: true },
  fieldPrefix: { type: String, default: "" },
  cameraSensorItems: { type: Array, default: () => [] },
  availableRooms: { type: Array, default: () => [] },
});

const emit = defineEmits(["update:modelValue"]);

const p = props.fieldPrefix;

const newCameraId = ref(null);
const showRooms = ref(false);

const sensorIds = computed(() => props.modelValue[`${p}additional_sensor_ids`] || []);
const sensorLimits = computed(() => props.modelValue[`${p}sensor_frame_limits`] || {});
const imagesPerSensor = computed(() => props.modelValue[`${p}images_per_sensor`] ?? 3);
const roomNames = computed(() => props.modelValue[`${p}additional_room_names`] || []);

const availableCameraItems = computed(() =>
  props.cameraSensorItems.filter((id) => !sensorIds.value.includes(id)),
);

const cameraRows = computed(() => {
  const defaultLimit = imagesPerSensor.value;
  return sensorIds.value.map((id) => ({
    sensor_id: id,
    frames: sensorLimits.value[id] ?? defaultLimit,
    isOverride: id in sensorLimits.value,
  }));
});

function emitUpdate(patch) {
  emit("update:modelValue", { ...props.modelValue, ...patch });
}

function emitSensorFrameLimit(sensorId, value) {
  const defaultLimit = imagesPerSensor.value;
  const limits = { ...(props.modelValue[`${p}sensor_frame_limits`] || {}) };
  if (value <= 0 || value === defaultLimit) {
    delete limits[sensorId];
  } else {
    limits[sensorId] = value;
  }
  emitUpdate({ [`${p}sensor_frame_limits`]: limits });
}

function updateImagesPerSensor(val) {
  emitUpdate({ [`${p}images_per_sensor`]: Number(val) || 1 });
}

function addCamera(id) {
  if (!id) return;
  const ids = [...sensorIds.value];
  if (!ids.includes(id)) {
    ids.push(id);
    emitUpdate({ [`${p}additional_sensor_ids`]: ids });
  }
  newCameraId.value = null;
}

function removeCamera(sensorId) {
  const ids = sensorIds.value.filter((id) => id !== sensorId);
  const limits = { ...sensorLimits.value };
  delete limits[sensorId];
  emitUpdate({
    [`${p}additional_sensor_ids`]: ids,
    [`${p}sensor_frame_limits`]: limits,
  });
}

function emitRoomNames(val) {
  emitUpdate({ [`${p}additional_room_names`]: val });
}
</script>
