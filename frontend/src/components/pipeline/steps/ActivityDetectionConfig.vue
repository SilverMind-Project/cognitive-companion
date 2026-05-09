<!-- Backend: backend/steps/builtin/activity_detection.py -->
<template>
  <v-combobox
    :model-value="modelValue.activity_type"
    :items="activityTypes"
    label="Activity Type"
    hint="Activity to record. Supports {{template}} syntax (e.g. {{logic_response.activity_type}})."
    persistent-hint
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, activity_type: $event })"
  />
  <v-combobox
    :model-value="modelValue.person_id"
    :items="availablePersons"
    label="Person ID (optional)"
    clearable
    hint="Person to attribute this activity to. Supports {{template}} syntax. Leave empty for unknown person."
    persistent-hint
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, person_id: $event })"
  />
  <v-combobox
    :model-value="modelValue.room_name"
    :items="availableRooms"
    label="Room (optional)"
    clearable
    hint="Room where the activity occurred. Defaults to trigger room when empty."
    persistent-hint
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, room_name: $event })"
  />
  <v-text-field
    :model-value="modelValue.confidence"
    label="Confidence"
    hint="Fixed value (0-1) or {{template}} syntax. Defaults to 0.8."
    persistent-hint
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, confidence: $event })"
  />
  <v-divider class="mb-4" />
  <div class="text-overline text-medium-emphasis mb-2">Scene Description Capture</div>
  <v-checkbox
    :model-value="modelValue.capture_scene_description"
    label="Capture scene description into activity record"
    hint="Saves the upstream vision model output (e.g. vision_response) into metadata_json.scene_description for full auditability."
    persistent-hint
    hide-details
    class="mb-3"
    @update:model-value="emit('update:modelValue', { ...modelValue, capture_scene_description: $event })"
  />
  <v-combobox
    v-if="modelValue.capture_scene_description"
    :model-value="modelValue.scene_description_key"
    :items="contextKeys"
    label="Scene Description Source Key"
    hint="pipeline_data key to read as the scene description (default: vision_response)."
    persistent-hint
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, scene_description_key: $event })"
  />
  <v-textarea
    :model-value="modelValue.metadata_extra"
    label="Extra Metadata (JSON, optional)"
    rows="3"
    hint='Optional JSON merged into metadata_json. Supports {{template}} syntax, e.g. {"reasoning": "{{logic_response.reasoning}}"}'
    persistent-hint
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, metadata_extra: $event })"
  />
  <v-checkbox
    :model-value="modelValue.trigger_cooloff"
    label="Trigger cool-off upon execution"
    hide-details
    @update:model-value="emit('update:modelValue', { ...modelValue, trigger_cooloff: $event })"
  />
</template>

<script>
export const stepDefaults = {
  activity_type: "",
  person_id: "",
  confidence: "0.8",
  room_name: "",
  capture_scene_description: false,
  scene_description_key: "vision_response",
  metadata_extra: "",
  trigger_cooloff: true,
};
export const stepTabs = [];
</script>

<script setup>
defineProps({
  modelValue: { type: Object, required: true },
  availablePersons: { type: Array, default: () => [] },
  availableRooms: { type: Array, default: () => [] },
  activityTypes: { type: Array, default: () => [] },
  contextKeys: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:modelValue"]);
</script>
