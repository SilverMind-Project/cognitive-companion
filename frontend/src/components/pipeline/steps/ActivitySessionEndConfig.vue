<!-- Backend: backend/steps/builtin/activity_session_end.py -->
<template>
  <v-combobox
    :model-value="modelValue.activity_type"
    :items="activityTypes"
    label="Activity Type"
    hint="Activity session to close. Supports {{template}} syntax."
    persistent-hint
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, activity_type: $event })"
  />
  <v-combobox
    :model-value="modelValue.person_id"
    :items="availablePersons"
    label="Person ID"
    clearable
    hint="Person whose session to close. Supports {{template}} syntax."
    persistent-hint
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, person_id: $event })"
  />
  <v-checkbox
    :model-value="modelValue.write_activity_record"
    label="Write PersonActivity record with duration"
    hint="Records a PersonActivity entry with duration_minutes populated."
    persistent-hint
    class="mb-4"
    @update:model-value="
      emit('update:modelValue', { ...modelValue, write_activity_record: $event })
    "
  />
  <v-text-field
    :model-value="modelValue.output_key"
    label="Output Key"
    hint="pipeline_data key for the closed session result. Default: closed_session"
    persistent-hint
    @update:model-value="emit('update:modelValue', { ...modelValue, output_key: $event })"
  />
</template>

<script>
export const stepDefaults = {
  activity_type: "",
  person_id: "",
  write_activity_record: true,
  output_key: "closed_session",
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
  activityTypes: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:modelValue"]);
</script>
