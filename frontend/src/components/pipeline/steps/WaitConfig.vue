<!-- Backend: backend/steps/builtin/wait.py -->
<template>
  <v-text-field
    :model-value="modelValue.minutes"
    label="Wait Duration (minutes)"
    type="number"
    :min="0"
    @update:model-value="emit('update:modelValue', { ...modelValue, minutes: Number($event) || 0 })"
  />
</template>

<script>
export const stepDefaults = { minutes: 5 };
export const stepTabs = [];

export function chips(cfg, { chip }) {
  const mins = cfg.minutes ?? 5;
  return [chip(`${mins} min`, "mdi-timer-sand", "amber")];
}
</script>

<script setup>
defineProps({ modelValue: { type: Object, required: true } });
const emit = defineEmits(["update:modelValue"]);
</script>
