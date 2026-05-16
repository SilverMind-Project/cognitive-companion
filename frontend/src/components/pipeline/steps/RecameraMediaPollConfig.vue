<!-- Backend: backend/steps/builtin/recamera_media_poll.py -->
<template>
  <!-- General tab: timing and caps -->
  <div v-if="tab === 'general'">
    <v-alert type="info" variant="tonal" density="compact" class="mb-4">
      Snapshot semantics: reads what is currently in the MediaCache and
      returns immediately. To wait for new reCamera events to accumulate
      first, place a <strong>Wait</strong> step before this one.
    </v-alert>

    <v-row dense class="mb-1">
      <v-col cols="12" md="6">
        <v-text-field
          :model-value="modelValue.since_minutes"
          label="Lookback (minutes)"
          type="number"
          :min="0.5"
          :max="60"
          :step="0.5"
          variant="outlined"
          density="compact"
          hide-details="auto"
          rounded="lg"
          hint="Return images captured within the last N minutes (0.5 – 60)"
          persistent-hint
          class="mb-4"
          @update:model-value="emit('update:modelValue', { ...modelValue, since_minutes: clamp(Number($event), 0.5, 60) })"
        />
      </v-col>
      <v-col cols="12" md="6">
        <v-text-field
          :model-value="modelValue.max_images"
          label="Max images (total)"
          type="number"
          :min="1"
          :max="50"
          variant="outlined"
          density="compact"
          hide-details="auto"
          rounded="lg"
          hint="Hard cap across all sensors (1 – 50)"
          persistent-hint
          class="mb-4"
          @update:model-value="emit('update:modelValue', { ...modelValue, max_images: clamp(Math.round(Number($event)), 1, 50) })"
        />
      </v-col>
    </v-row>

    <v-checkbox
      :model-value="modelValue.chronological"
      label="Chronological order (oldest first)"
      hint="When enabled, images within each sensor are sorted oldest-first, which is better for temporal reasoning by a vision model."
      persistent-hint
      hide-details="auto"
      class="mb-1"
      @update:model-value="emit('update:modelValue', { ...modelValue, chronological: $event })"
    />
  </div>

  <!-- Cameras tab: sensor and room selection -->
  <div v-else-if="tab === 'cameras'">
    <div class="text-overline text-medium-emphasis mb-2">Sensor Selection</div>

    <v-combobox
      :model-value="modelValue.sensor_ids"
      :items="cameraSensorItems"
      label="Sensor IDs (optional)"
      hint="Specific reCamera sensor IDs to pull images from. Leave empty to include all sensors (subject to room filter below)."
      persistent-hint
      multiple
      chips
      closable-chips
      variant="outlined"
      density="compact"
      hide-details="auto"
      rounded="lg"
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, sensor_ids: $event || [] })"
    />

    <v-combobox
      :model-value="modelValue.room_names"
      :items="availableRooms"
      label="Rooms (optional)"
      hint="Pull from all cameras in these rooms. Combined with sensor_ids, only sensors in these rooms are returned."
      persistent-hint
      multiple
      chips
      closable-chips
      variant="outlined"
      density="compact"
      hide-details="auto"
      rounded="lg"
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, room_names: $event || [] })"
    />

    <v-divider class="mb-4" />
    <div class="text-overline text-medium-emphasis mb-2">Per-Sensor Limits</div>
    <div class="text-caption text-medium-emphasis mb-3">
      Applies when sensor IDs are specified. Ignored when only room names are
      used.
    </div>

    <v-text-field
      :model-value="modelValue.images_per_sensor"
      label="Images per sensor (default)"
      type="number"
      :min="1"
      :max="20"
      variant="outlined"
      density="compact"
      hide-details="auto"
      rounded="lg"
      hint="Default maximum images per sensor (1 – 20)"
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, images_per_sensor: clamp(Math.round(Number($event)), 1, 20) })"
    />

    <template v-if="modelValue.sensor_ids && modelValue.sensor_ids.length > 0">
      <div class="text-subtitle-2 mb-2">Per-sensor overrides</div>
      <div
        v-for="sid in modelValue.sensor_ids"
        :key="sid"
        class="d-flex align-center mb-2"
      >
        <div class="text-body-2 flex-grow-1 mr-3">{{ sid }}</div>
        <v-text-field
          :model-value="modelValue.sensor_frame_limits[sid] ?? modelValue.images_per_sensor"
          type="number"
          :min="1"
          :max="20"
          density="compact"
          hide-details
          variant="outlined"
          style="max-width: 120px"
          @update:model-value="updateSensorLimit(sid, Number($event))"
        />
      </div>
    </template>
  </div>
</template>

<script>
export const stepDefaults = {
  sensor_ids: [],
  room_names: [],
  since_minutes: 5,
  images_per_sensor: 3,
  sensor_frame_limits: {},
  max_images: 10,
  chronological: true,
};

export const stepTabs = [
  { key: "cameras", label: "Cameras", icon: "mdi-camera-wireless-outline" },
];
</script>

<script setup>
function clamp(val, min, max) {
  if (isNaN(val)) return min;
  return Math.min(Math.max(val, min), max);
}

const props = defineProps({
  modelValue: { type: Object, required: true },
  tab: { type: String, default: "general" },
  cameraSensorItems: { type: Array, default: () => [] },
  availableRooms: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:modelValue"]);

function updateSensorLimit(sensorId, value) {
  const defaultLimit = props.modelValue.images_per_sensor ?? 3;
  const limits = { ...(props.modelValue.sensor_frame_limits || {}) };
  if (!value || value <= 0 || value === defaultLimit) {
    delete limits[sensorId];
  } else {
    limits[sensorId] = value;
  }
  emit("update:modelValue", { ...props.modelValue, sensor_frame_limits: limits });
}
</script>
