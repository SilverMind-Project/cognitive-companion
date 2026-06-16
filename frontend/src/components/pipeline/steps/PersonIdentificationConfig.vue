<!-- Backend: backend/steps/builtin/person_identification.py -->
<template>
  <!-- General tab: person identification settings -->
  <div v-if="tab === 'general'">
    <v-combobox
      :model-value="modelValue.target_persons"
      :items="availablePersons"
      label="Target Persons"
      multiple
      chips
      closable-chips
      hint="Select persons to identify, or leave empty for all"
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, target_persons: $event })"
    />
    <v-slider
      :model-value="modelValue.min_confidence"
      label="Min Confidence"
      :min="0" :max="1" :step="0.05"
      thumb-label="always"
      color="primary"
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, min_confidence: $event })"
    />
    <v-checkbox
      :model-value="modelValue.include_annotated_image"
      label="Include annotated image"
      class="mb-1" hide-details
      @update:model-value="emit('update:modelValue', { ...modelValue, include_annotated_image: $event })"
    />
    <v-checkbox
      :model-value="modelValue.include_motion"
      label="Include motion data"
      class="mb-1" hide-details
      @update:model-value="emit('update:modelValue', { ...modelValue, include_motion: $event })"
    />
    <v-checkbox
      :model-value="modelValue.save_guest_images"
      label="Save guest images (unidentified faces)"
      class="mb-4" hide-details
      @update:model-value="emit('update:modelValue', { ...modelValue, save_guest_images: $event })"
    />
  </div>

  <!-- Images tab -->
  <div v-else-if="tab === 'images'">
    <ImageSourceSelector
      :model-value="modelValue"
      :camera-sensor-items="cameraSensorItems"
      :available-rooms="availableRooms"
      @update:model-value="emit('update:modelValue', $event)"
    />
  </div>

  <!-- Presence tab -->
  <div v-else-if="tab === 'presence'">
    <v-switch
      :model-value="modelValue.record_presence"
      label="Record presence (update location state and history)"
      color="primary"
      hide-details
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, record_presence: $event })"
    />

    <v-switch
      :model-value="modelValue.record_sightings"
      label="Record sightings (write PersonSighting rows)"
      color="primary"
      hide-details
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, record_sightings: $event })"
    />

    <v-select
      :model-value="modelValue.presence_room_source"
      :items="[
        { title: 'Trigger room', value: 'trigger' },
        { title: 'Source image room', value: 'source_image' },
        { title: 'Custom room', value: 'custom' },
      ]"
      item-title="title"
      item-value="value"
      label="Presence Room Source"
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, presence_room_source: $event })"
    />

    <v-combobox
      v-if="modelValue.presence_room_source === 'custom'"
      :model-value="modelValue.presence_room_name"
      :items="availableRooms"
      label="Presence Room Name"
      hint="Custom room name for presence recording"
      persistent-hint
      @update:model-value="emit('update:modelValue', { ...modelValue, presence_room_name: $event })"
    />
  </div>
</template>

<script>
import ImageSourceSelector from "./_shared/ImageSourceSelector.vue";

export const stepDefaults = {
  target_persons: [],
  min_confidence: 0.6,
  include_annotated_image: true,
  include_motion: false,
  save_guest_images: false,
  additional_sensor_ids: [],
  image_source: "trigger",
  pipeline_image_path: "",
  cts_frames_path: "steps.media_window_poll_1.outputs.frames",
  record_presence: true,
  record_sightings: true,
  presence_room_source: "trigger",
  presence_room_name: "",
};
export const stepTabs = [
  { key: "images", label: "Images", icon: "mdi-camera-outline" },
  { key: "presence", label: "Presence", icon: "mdi-map-marker-outline" },
];
</script>

<script setup>
defineProps({
  modelValue: { type: Object, required: true },
  tab: { type: String, default: "general" },
  availablePersons: { type: Array, default: () => [] },
  cameraSensorItems: { type: Array, default: () => [] },
  availableRooms: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:modelValue"]);
</script>
