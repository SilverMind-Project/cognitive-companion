<!-- Backend: backend/steps/builtin/cts_window_poll.py -->
<template>
  <!-- General tab: timing and sampling -->
  <div v-if="tab === 'general'">
    <v-alert
      v-if="modelValue.partial === true"
      type="warning"
      variant="tonal"
      density="compact"
      class="mb-4"
    >
      The CTS event bucketizer is not yet wired (Phase 3). This step will
      return an empty window with <code>partial=true</code> until that phase is
      complete.
    </v-alert>

    <div class="text-overline text-medium-emphasis mb-2">Timing</div>

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
          @update:model-value="emit('update:modelValue', { ...modelValue, lookback_s: clamp(Number($event), 0, 30) })"
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
          @update:model-value="emit('update:modelValue', { ...modelValue, lookahead_s: clamp(Number($event), 0, 30) })"
        />
      </v-col>
    </v-row>

    <div class="text-overline text-medium-emphasis mb-2">Sampling</div>

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
          @update:model-value="emit('update:modelValue', { ...modelValue, sample_period_s: clamp(Number($event), 0.2, 30) })"
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
          @update:model-value="emit('update:modelValue', { ...modelValue, max_frames: clamp(Math.round(Number($event)), 1, 200) })"
        />
      </v-col>
    </v-row>

    <v-divider class="mb-4" />
    <div class="text-overline text-medium-emphasis mb-2">Enrichment</div>

    <v-checkbox
      :model-value="modelValue.include_scene"
      label="Run scene analysis on sampled frames"
      hint="Calls SceneAnalysisService for each sampled frame. Adds per-frame latency."
      persistent-hint
      hide-details="auto"
      class="mb-3"
      @update:model-value="emit('update:modelValue', { ...modelValue, include_scene: $event })"
    />

    <v-checkbox
      :model-value="modelValue.include_pose"
      label="Include pose keypoints"
      hint="Requires TD-005 (pose estimator) to be wired. Currently not available."
      persistent-hint
      hide-details="auto"
      disabled
      class="mb-1"
      @update:model-value="emit('update:modelValue', { ...modelValue, include_pose: $event })"
    />
    <div class="text-caption text-medium-emphasis ml-8 mb-3">
      Pose keypoints are not yet wired (TD-005). This option is shown for
      configuration completeness and will be enabled in a future release.
    </div>
  </div>

  <!-- Cameras tab: camera ID and room filters -->
  <div v-else-if="tab === 'cameras'">
    <v-alert type="info" variant="tonal" density="compact" class="mb-4">
      CTS camera IDs are distinct from reCamera sensor IDs. Enter the exact
      camera IDs configured in the CTS admin UI (e.g. <code>cam1</code>,
      <code>cam2</code>). Leave both fields empty to include all cameras and
      rooms.
    </v-alert>

    <v-combobox
      :model-value="modelValue.cameras"
      label="CTS Camera IDs (optional)"
      hint="Restrict to these CTS camera IDs. Leave empty to include all cameras."
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
      label="Rooms (optional)"
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
  </div>
</template>

<script>
export const stepDefaults = {
  duration_s: 10,
  sample_period_s: 1.0,
  lookback_s: 5,
  lookahead_s: 5,
  cameras: [],
  rooms: [],
  include_scene: false,
  include_pose: false,
  max_frames: 30,
};

export const stepTabs = [
  { key: "cameras", label: "Cameras", icon: "mdi-cctv" },
];
</script>

<script setup>
function clamp(val, min, max) {
  if (isNaN(val)) return min;
  return Math.min(Math.max(val, min), max);
}

defineProps({
  modelValue: { type: Object, required: true },
  tab: { type: String, default: "general" },
  availableRooms: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:modelValue"]);
</script>
