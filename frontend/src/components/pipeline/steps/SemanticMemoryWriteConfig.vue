<!-- Backend: backend/steps/builtin/semantic_memory_write.py -->
<template>
  <v-select
    :model-value="modelValue.write_type"
    :items="['observation', 'movement']"
    label="Write Type"
    hint="What to persist in semantic memory."
    persistent-hint
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, write_type: $event })"
  />

  <!-- Observation fields -->
  <template v-if="modelValue.write_type === 'observation'">
    <v-combobox
      :model-value="modelValue.room_id"
      :items="availableRooms"
      label="Room ID"
      hint="Room where the observation occurred."
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, room_id: $event })"
    />
    <TemplateInput
      :model-value="modelValue.description"
      label="Description"
      multiline
      :rows="3"
      hint="Human-readable description of the scene. Type {{ to autocomplete pipeline variables."
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, description: $event })"
    />
    <v-combobox
      :model-value="modelValue.object_list"
      :items="[]"
      label="Objects Detected"
      multiple
      chips
      closable-chips
      hint="List of object labels. Supports {{template}} syntax."
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, object_list: $event })"
    />
    <v-combobox
      :model-value="modelValue.hazard_flags"
      :items="[]"
      label="Hazard Flags"
      multiple
      chips
      closable-chips
      hint="List of hazard flags (e.g. 'door_unsafe', 'person_on_floor')."
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, hazard_flags: $event })"
    />
    <v-text-field
      :model-value="modelValue.source"
      label="Source"
      hint="Source identifier. Default: scene_intel"
      persistent-hint
      @update:model-value="emit('update:modelValue', { ...modelValue, source: $event })"
    />
  </template>

  <!-- Movement fields -->
  <template v-if="modelValue.write_type === 'movement'">
    <v-combobox
      :model-value="modelValue.person_id"
      :items="availablePersons"
      label="Person ID"
      hint="Person who moved. Supports {{template}} syntax."
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, person_id: $event })"
    />
    <v-combobox
      :model-value="modelValue.from_room_id"
      :items="availableRooms"
      label="From Room"
      hint="Starting room. Supports {{template}} syntax."
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, from_room_id: $event })"
    />
    <v-combobox
      :model-value="modelValue.to_room_id"
      :items="availableRooms"
      label="To Room"
      hint="Destination room. Supports {{template}} syntax."
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, to_room_id: $event })"
    />
    <v-combobox
      :model-value="modelValue.direction_semantic"
      :items="['entering', 'exiting', 'approaching_exit', 'entering_depth', 'stationary', 'any']"
      label="Direction Semantic"
      hint="Type of movement."
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, direction_semantic: $event })"
    />
    <v-text-field
      :model-value="modelValue.confidence"
      label="Confidence"
      hint="Confidence score (0-1). Default: 0.8"
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, confidence: $event })"
    />
    <v-combobox
      :model-value="modelValue.observation_id"
      :items="[]"
      label="Observation ID (optional)"
      hint="Link this movement to a prior observation. Supports {{template}} syntax."
      persistent-hint
      @update:model-value="emit('update:modelValue', { ...modelValue, observation_id: $event })"
    />
  </template>
</template>

<script>
export const stepDefaults = {
  write_type: "observation",
  room_id: "",
  description: "",
  object_list: [],
  hazard_flags: [],
  source: "scene_intel",
  person_id: "",
  from_room_id: "",
  to_room_id: "",
  direction_semantic: "",
  confidence: "0.8",
  observation_id: "",
};
export const stepTabs = [];
</script>

<script setup>
import TemplateInput from "./_shared/TemplateInput.vue";

defineProps({
  modelValue: { type: Object, required: true },
  availablePersons: { type: Array, default: () => [] },
  availableRooms: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:modelValue"]);
</script>
