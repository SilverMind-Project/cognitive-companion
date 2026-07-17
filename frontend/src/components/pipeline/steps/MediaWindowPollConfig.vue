<!-- Backend: backend/steps/builtin/media_window_poll.py -->
<template>
  <!-- General tab: source selection + per-source timing/sampling -->
  <div v-if="tab === 'general'">
    <div class="text-overline text-medium-emphasis mb-2">Source</div>

    <v-select
      :model-value="modelValue.source"
      :items="sourceItems"
      item-title="title"
      item-value="value"
      label="Aggregation source"
      variant="outlined"
      density="compact"
      hide-details="auto"
      rounded="lg"
      class="mb-3"
      @update:model-value="emit('update:modelValue', { ...modelValue, source: $event })"
    />

    <v-alert
      v-if="modelValue.source === 'auto'"
      type="info"
      variant="tonal"
      density="compact"
      class="mb-4"
    >
      Auto resolves to <strong>CTS</strong> when a live tracking buffer is available at runtime,
      otherwise <strong>reCamera</strong>. Configure both field groups below so the step works
      whichever path is selected.
    </v-alert>

    <!-- CTS timing / sampling / enrichment -->
    <template v-if="showCts">
      <v-divider v-if="modelValue.source === 'auto'" class="mb-4" />
      <div class="text-overline text-medium-emphasis mb-2">CTS Timing</div>

      <v-row dense class="mb-1">
        <v-col cols="12" md="6">
          <v-text-field
            :model-value="modelValue.lookback_s"
            label="Lookback (seconds)"
            type="number"
            :min="0"
            :max="30"
            variant="outlined"
            density="compact"
            hide-details="auto"
            rounded="lg"
            hint="Frames collected before the trigger time"
            persistent-hint
            class="mb-4"
            @update:model-value="
              emit('update:modelValue', { ...modelValue, lookback_s: clamp(Number($event), 0, 30) })
            "
          />
        </v-col>
        <v-col cols="12" md="6">
          <v-text-field
            :model-value="modelValue.lookahead_s"
            label="Lookahead (seconds)"
            type="number"
            :min="0"
            :max="30"
            variant="outlined"
            density="compact"
            hide-details="auto"
            rounded="lg"
            hint="Seconds to wait and collect after trigger"
            persistent-hint
            class="mb-4"
            @update:model-value="
              emit('update:modelValue', {
                ...modelValue,
                lookahead_s: clamp(Number($event), 0, 30),
              })
            "
          />
        </v-col>
      </v-row>

      <div class="text-overline text-medium-emphasis mb-2">CTS Sampling</div>

      <v-row dense>
        <v-col cols="12" md="6">
          <v-text-field
            :model-value="modelValue.sample_period_s"
            label="Sample period (seconds)"
            type="number"
            :min="0.2"
            :max="30"
            :step="0.1"
            variant="outlined"
            density="compact"
            hide-details="auto"
            rounded="lg"
            hint="Keep one frame per this many seconds (0.2 – 30)"
            persistent-hint
            class="mb-4"
            @update:model-value="
              emit('update:modelValue', {
                ...modelValue,
                sample_period_s: clamp(Number($event), 0.2, 30),
              })
            "
          />
        </v-col>
        <v-col cols="12" md="6">
          <v-text-field
            :model-value="modelValue.max_frames"
            label="Max frames returned"
            type="number"
            :min="1"
            :max="200"
            variant="outlined"
            density="compact"
            hide-details="auto"
            rounded="lg"
            hint="Hard cap on total frames (1 – 200)"
            persistent-hint
            class="mb-4"
            @update:model-value="
              emit('update:modelValue', {
                ...modelValue,
                max_frames: clamp(Math.round(Number($event)), 1, 200),
              })
            "
          />
        </v-col>
      </v-row>

      <v-divider class="mb-4" />
      <div class="text-overline text-medium-emphasis mb-2">CTS Enrichment</div>

      <v-checkbox
        :model-value="modelValue.include_scene"
        label="Run scene analysis on sampled frames"
        hint="Calls SceneAnalysisService for each sampled frame. Adds per-frame latency."
        persistent-hint
        hide-details="auto"
        class="mb-3"
        @update:model-value="emit('update:modelValue', { ...modelValue, include_scene: $event })"
      />
    </template>

    <!-- reCamera timing / caps -->
    <template v-if="showRecamera">
      <v-divider v-if="modelValue.source === 'auto'" class="mb-4" />
      <div class="text-overline text-medium-emphasis mb-2">reCamera Window</div>

      <v-alert type="info" variant="tonal" density="compact" class="mb-4">
        Snapshot semantics: reads what is currently in the MediaCache and returns immediately. To
        wait for new reCamera events to accumulate first, place a <strong>Wait</strong> step before
        this one.
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
            @update:model-value="
              emit('update:modelValue', {
                ...modelValue,
                since_minutes: clamp(Number($event), 0.5, 60),
              })
            "
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
            @update:model-value="
              emit('update:modelValue', {
                ...modelValue,
                max_images: clamp(Math.round(Number($event)), 1, 50),
              })
            "
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
    </template>
  </div>

  <!-- Cameras tab: per-source camera/sensor and room filters -->
  <div v-else-if="tab === 'cameras'">
    <!-- CTS cameras -->
    <template v-if="showCts">
      <v-alert type="info" variant="tonal" density="compact" class="mb-4">
        CTS camera IDs are distinct from reCamera sensor IDs. Enter the exact camera IDs configured
        in the CTS admin UI (e.g. <code>cam1</code>, <code>cam2</code>). Leave both fields empty to
        include all cameras and rooms.
      </v-alert>

      <v-combobox
        :model-value="modelValue.cameras"
        :items="ctsCameraItems"
        label="CTS Camera IDs (optional)"
        hint="Pick from the configured CTS cameras, or type an ID. Leave empty to include all cameras."
        persistent-hint
        multiple
        chips
        closable-chips
        variant="outlined"
        density="compact"
        hide-details="auto"
        rounded="lg"
        class="mb-4"
        @update:model-value="emit('update:modelValue', { ...modelValue, cameras: $event || [] })"
      />

      <v-combobox
        :model-value="modelValue.rooms"
        :items="availableRooms"
        label="CTS Rooms (optional)"
        hint="Restrict to cameras assigned to these rooms. Leave empty to include all rooms."
        persistent-hint
        multiple
        chips
        closable-chips
        variant="outlined"
        density="compact"
        hide-details="auto"
        rounded="lg"
        class="mb-4"
        @update:model-value="emit('update:modelValue', { ...modelValue, rooms: $event || [] })"
      />
    </template>

    <!-- reCamera sensors -->
    <template v-if="showRecamera">
      <v-divider v-if="modelValue.source === 'auto'" class="mb-4" />
      <div class="text-overline text-medium-emphasis mb-2">reCamera Sensors</div>

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
        label="reCamera Rooms (optional)"
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
        Applies when sensor IDs are specified. Ignored when only room names are used.
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
        @update:model-value="
          emit('update:modelValue', {
            ...modelValue,
            images_per_sensor: clamp(Math.round(Number($event)), 1, 20),
          })
        "
      />

      <template v-if="modelValue.sensor_ids && modelValue.sensor_ids.length > 0">
        <div class="text-subtitle-2 mb-2">Per-sensor overrides</div>
        <div v-for="sid in modelValue.sensor_ids" :key="sid" class="d-flex align-center mb-2">
          <div class="text-body-2 flex-grow-1 mr-3">{{ sid }}</div>
          <v-text-field
            :model-value="
              (modelValue.sensor_frame_limits || {})[sid] ?? modelValue.images_per_sensor
            "
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
    </template>
  </div>
</template>

<script>
export const stepDefaults = {
  source: "auto",
  // CTS path
  duration_s: 10,
  sample_period_s: 1.0,
  lookback_s: 5,
  lookahead_s: 5,
  cameras: [],
  rooms: [],
  include_scene: false,
  max_frames: 30,
  // reCamera path
  sensor_ids: [],
  room_names: [],
  since_minutes: 5,
  images_per_sensor: 3,
  sensor_frame_limits: {},
  max_images: 10,
  chronological: true,
};

export const stepTabs = [{ key: "cameras", label: "Cameras", icon: "mdi-cctv" }];
</script>

<script setup>
import { computed } from "vue";

function clamp(val, min, max) {
  if (isNaN(val)) return min;
  return Math.min(Math.max(val, min), max);
}

const props = defineProps({
  modelValue: { type: Object, required: true },
  tab: { type: String, default: "general" },
  availableRooms: { type: Array, default: () => [] },
  ctsCameraItems: { type: Array, default: () => [] },
  cameraSensorItems: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:modelValue"]);

const sourceItems = [
  { title: "Auto (prefer CTS when available)", value: "auto" },
  { title: "CTS live tracking", value: "cts" },
  { title: "reCamera media cache", value: "recamera" },
];

// Auto resolves to one path at runtime, so expose both field groups for it.
const showCts = computed(() => props.modelValue.source !== "recamera");
const showRecamera = computed(() => props.modelValue.source !== "cts");

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
