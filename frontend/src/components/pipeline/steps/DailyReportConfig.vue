<!-- Backend: backend/steps/builtin/daily_report.py -->
<template>
  <v-combobox
    :model-value="modelValue.person_ids"
    :items="availablePersons"
    label="Person IDs"
    multiple
    chips
    closable-chips
    hint="Leave empty to generate reports for all active household members."
    persistent-hint
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, person_ids: $event })"
  />
  <v-text-field
    :model-value="modelValue.report_date_offset_days"
    label="Report Date Offset (days)"
    type="number"
    hint="0 = today, -1 = yesterday."
    persistent-hint
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, report_date_offset_days: Number($event) || 0 })"
  />
  <v-checkbox
    :model-value="modelValue.generate_summary_text"
    label="Generate LLM prose summary"
    hide-details
    class="mb-3"
    @update:model-value="emit('update:modelValue', { ...modelValue, generate_summary_text: $event })"
  />
  <v-text-field
    v-if="modelValue.generate_summary_text"
    :model-value="modelValue.summary_model_id"
    label="Summary Model ID"
    hint="LLM model ID for summary generation."
    persistent-hint
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, summary_model_id: $event })"
  />
  <v-text-field
    :model-value="modelValue.output_key"
    label="Output Key"
    hint="pipeline_data key for the report list. Default: daily_reports"
    persistent-hint
    @update:model-value="emit('update:modelValue', { ...modelValue, output_key: $event })"
  />
</template>

<script>
export const stepDefaults = {
  person_ids: [],
  report_date_offset_days: 0,
  generate_summary_text: false,
  summary_model_id: "",
  notify_on_complete: false,
  output_key: "daily_reports",
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
