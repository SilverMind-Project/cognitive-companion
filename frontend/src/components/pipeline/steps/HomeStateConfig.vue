<!-- Backend: backend/steps/builtin/home_state.py -->
<template>
  <v-form ref="form" v-model="formValid">
    <v-combobox
      :model-value="modelValue.person_id"
      :items="availablePersons"
      label="Person"
      hint="Person whose home-state to derive. Supports {{template}} syntax."
      persistent-hint
      variant="outlined"
      density="compact"
      hide-details="auto"
      rounded="lg"
      clearable
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, person_id: $event })"
    />

    <v-text-field
      :model-value="modelValue.output_key"
      label="Output Key"
      :rules="[v => /^[a-z][a-z0-9_]*$/.test(v) || 'Lowercase letters, digits, underscores only; must start with a letter.']"
      hint="pipeline_data key prefix. Emits <key>_at_home, <key>_asleep, <key>_away, <key>_state_unknown. Default: home."
      persistent-hint
      variant="outlined"
      density="compact"
      hide-details="auto"
      rounded="lg"
      @update:model-value="emit('update:modelValue', { ...modelValue, output_key: $event })"
    />
  </v-form>
</template>

<script>
export const stepDefaults = { person_id: "", output_key: "home" };
export const stepTabs = [];
</script>

<script setup>
import { ref } from "vue";

defineProps({
  modelValue: { type: Object, required: true },
  availablePersons: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:modelValue"]);

const formValid = ref(true);
const form = ref(null);

defineExpose({ form, formValid });
</script>
