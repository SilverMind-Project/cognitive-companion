<!-- Backend: backend/steps/builtin/scene_analysis.py -->
<template>
  <!-- General tab -->
  <div v-if="tab === 'general'">
    <v-checkbox
      :model-value="modelValue.run_detect"
      label="Run YOLO object detection"
      hide-details class="mb-1"
      @update:model-value="emit('update:modelValue', { ...modelValue, run_detect: $event })"
    />
    <v-checkbox
      :model-value="modelValue.run_describe"
      label="Run Florence-2 scene description"
      hide-details class="mb-1"
      @update:model-value="emit('update:modelValue', { ...modelValue, run_describe: $event })"
    />
    <v-checkbox
      :model-value="modelValue.run_hazards"
      label="Evaluate hazard rules on detections"
      hide-details class="mb-1"
      @update:model-value="emit('update:modelValue', { ...modelValue, run_hazards: $event })"
    />
    <v-checkbox
      :model-value="modelValue.run_embed"
      label="Run CLIP embedding (slow)"
      hide-details class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, run_embed: $event })"
    />
    <v-checkbox
      :model-value="modelValue.write_to_memory"
      label="Write result to semantic memory"
      hide-details class="mb-2"
      @update:model-value="emit('update:modelValue', { ...modelValue, write_to_memory: $event })"
    />
  </div>

  <!-- Images tab -->
  <div v-else-if="tab === 'images'">
    <v-select
      :model-value="modelValue.image_source"
      :items="[
        { title: 'Trigger frames', value: 'trigger' },
        { title: 'Selected cameras', value: 'additional' },
        { title: 'Trigger + selected cameras', value: 'both' },
      ]"
      item-title="title"
      item-value="value"
      label="Image Source"
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, image_source: $event })"
    />

    <v-text-field
      :model-value="modelValue.max_images"
      label="Max Images (total)"
      type="number"
      :min="1"
      hint="Hard cap on total images analysed"
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, max_images: Number($event) || 1 })"
    />

    <template v-if="modelValue.image_source === 'trigger' || modelValue.image_source === 'both'">
      <v-card variant="tonal" class="mb-4 pa-4">
        <div class="text-subtitle-2">Trigger Camera</div>
        <v-text-field
          :model-value="modelValue.trigger_images_count"
          label="Max frames"
          type="number"
          :min="0"
          hint="0 = include all available trigger frames"
          persistent-hint
          density="compact"
          class="mt-2"
          @update:model-value="emit('update:modelValue', { ...modelValue, trigger_images_count: Number($event) || 0 })"
        />
      </v-card>
    </template>

    <template v-if="modelValue.image_source === 'additional' || modelValue.image_source === 'both'">
      <CameraSelector
        :model-value="modelValue"
        :camera-sensor-items="cameraSensorItems"
        :available-rooms="availableRooms"
        @update:model-value="emit('update:modelValue', $event)"
      />
    </template>

    <TimeFilterCard
      :model-value="modelValue.image_time_filter || {}"
      @update:model-value="emit('update:modelValue', { ...modelValue, image_time_filter: $event })"
    />
  </div>
</template>

<script>
import CameraSelector from "./_shared/CameraSelector.vue";
import TimeFilterCard from "./_shared/TimeFilterCard.vue";

export const stepDefaults = {
  run_detect: true,
  run_describe: true,
  run_embed: false,
  run_hazards: true,
  write_to_memory: false,
  image_source: "trigger",
  max_images: 1,
  trigger_images_count: 0,
  additional_sensor_ids: [],
  additional_room_names: [],
  images_per_sensor: 1,
  sensor_frame_limits: {},
  image_time_filter: {},
};
export const stepTabs = [
  { key: "images", label: "Images", icon: "mdi-camera-outline" },
];

export function onStepLoaded(cfg) {
  // No special normalization needed
}
</script>

<script setup>
defineProps({
  modelValue: { type: Object, required: true },
  tab: { type: String, default: "general" },
  cameraSensorItems: { type: Array, default: () => [] },
  availableRooms: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:modelValue"]);
</script>
