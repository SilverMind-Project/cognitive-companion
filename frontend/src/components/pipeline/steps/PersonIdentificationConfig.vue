<!-- Backend: backend/steps/builtin/person_identification.py -->
<template>
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
  <v-combobox
    :model-value="modelValue.additional_sensor_ids"
    :items="[]"
    label="Additional Sensor IDs"
    multiple
    chips
    closable-chips
    hint="Pull recent frames from these extra cameras in addition to the trigger sensor"
    persistent-hint
    class="mb-2"
    @update:model-value="emit('update:modelValue', { ...modelValue, additional_sensor_ids: $event })"
  />
</template>

<script>
export const stepDefaults = {
  target_persons: [],
  min_confidence: 0.6,
  include_annotated_image: true,
  include_motion: false,
  save_guest_images: false,
  additional_sensor_ids: [],
};
export const stepTabs = [];
</script>

<script setup>
defineProps({
  modelValue: { type: Object, required: true },
  availablePersons: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:modelValue"]);
</script>
