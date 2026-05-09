<!-- Backend: backend/steps/builtin/object_trend_analysis.py -->
<template>
  <v-combobox
    :model-value="modelValue.room_ids"
    :items="availableRooms"
    label="Room IDs"
    multiple
    chips
    closable-chips
    hint="Rooms to query. Leave empty to use the trigger room."
    persistent-hint
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, room_ids: $event })"
  />
  <v-select
    :model-value="modelValue.severity_threshold"
    :items="['ok', 'info', 'warning', 'critical']"
    label="Severity Threshold"
    hint="Anomalies below this severity are stripped from results."
    persistent-hint
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, severity_threshold: $event })"
  />
  <v-text-field
    :model-value="modelValue.include_snapshots_hours"
    label="Include Snapshots (hours)"
    type="number"
    :min="0"
    hint="If > 0, fetch raw hourly snapshots for LLM context."
    persistent-hint
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, include_snapshots_hours: Number($event) || 0 })"
  />
  <v-text-field
    :model-value="modelValue.output_key"
    label="Output Key"
    hint="pipeline_data key for the result map. Default: room_trends"
    persistent-hint
    @update:model-value="emit('update:modelValue', { ...modelValue, output_key: $event })"
  />
</template>

<script>
export const stepDefaults = {
  room_ids: [],
  include_snapshots_hours: 0,
  severity_threshold: "info",
  output_key: "room_trends",
};
export const stepTabs = [];
</script>

<script setup>
defineProps({
  modelValue: { type: Object, required: true },
  availableRooms: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:modelValue"]);
</script>
