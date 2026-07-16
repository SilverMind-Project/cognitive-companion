<!-- Backend: backend/steps/builtin/activity_session_start.py -->
<template>
  <v-combobox
    :model-value="modelValue.activity_type"
    :items="activityTypes"
    label="Activity Type"
    hint="Supports {{template}} syntax (e.g. {{logic_response.activity_type}})."
    persistent-hint
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, activity_type: $event })"
  />
  <v-combobox
    :model-value="modelValue.person_id"
    :items="availablePersons"
    label="Person ID"
    clearable
    hint="Supports {{template}} syntax (e.g. {{person_detections.0.person_id}})."
    persistent-hint
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, person_id: $event })"
  />
  <v-combobox
    :model-value="modelValue.room_name"
    :items="availableRooms"
    label="Room (optional)"
    clearable
    hint="Defaults to trigger room when empty. Supports {{template}} syntax."
    persistent-hint
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, room_name: $event })"
  />
  <v-text-field
    :model-value="modelValue.confidence"
    label="Confidence"
    hint="Fixed value (0-1) or {{template}} syntax. Default: 0.85."
    persistent-hint
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, confidence: $event })"
  />
  <v-text-field
    :model-value="modelValue.timeout_minutes"
    label="Timeout (minutes, optional)"
    hint="Max session duration before auto-close. Leave empty for activity-type default."
    persistent-hint
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, timeout_minutes: $event })"
  />
  <v-textarea
    :model-value="modelValue.metadata_extra"
    label="Extra Metadata (JSON, optional)"
    rows="3"
    hint='Optional JSON merged into session metadata. Supports {{template}} syntax.'
    persistent-hint
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, metadata_extra: $event })"
  />
  <v-text-field
    :model-value="modelValue.output_key"
    label="Output Key"
    hint="pipeline_data key for the session result. Default: session"
    persistent-hint
    @update:model-value="emit('update:modelValue', { ...modelValue, output_key: $event })"
  />
</template>

<script>
export const stepDefaults = {
  activity_type: "",
  person_id: "",
  room_name: "",
  confidence: 0.85,
  timeout_minutes: "",
  metadata_extra: "",
  output_key: "session",
};
export const stepTabs = [];

export function chips(cfg, { chip }) {
  const out = [];
  if (cfg.activity_type) out.push(chip(cfg.activity_type, "mdi-run", "indigo"));
  if (cfg.source_key) out.push(chip(`source: ${cfg.source_key}`, "mdi-link-variant", "blue-grey"));
  return out;
}
</script>

<script setup>
defineProps({
  modelValue: { type: Object, required: true },
  availablePersons: { type: Array, default: () => [] },
  availableRooms: { type: Array, default: () => [] },
  activityTypes: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:modelValue"]);
</script>
