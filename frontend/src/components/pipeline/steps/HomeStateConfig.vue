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
      :rules="[
        (v) =>
          /^[a-z][a-z0-9_]*$/.test(v) ||
          'Lowercase letters, digits, underscores only; must start with a letter.',
      ]"
      hint="pipeline_data key prefix. Emits <key>_at_home, <key>_asleep, <key>_away, <key>_state_unknown. Default: home."
      persistent-hint
      variant="outlined"
      density="compact"
      hide-details="auto"
      rounded="lg"
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, output_key: $event })"
    />

    <v-text-field
      :model-value="modelValue.entity_id"
      label="HA Entity (optional)"
      hint="e.g. media_player.living_room_tv. Also emits <key>_entity_state and <key>_entity_on, independent of person_id."
      persistent-hint
      variant="outlined"
      density="compact"
      hide-details="auto"
      rounded="lg"
      clearable
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, entity_id: $event })"
    />

    <v-combobox
      v-if="modelValue.entity_id"
      :model-value="modelValue.states_any"
      :items="[]"
      label="States counted as 'on' (any)"
      multiple
      chips
      closable-chips
      hint="e.g. playing, on"
      persistent-hint
      variant="outlined"
      density="compact"
      rounded="lg"
      @update:model-value="emit('update:modelValue', { ...modelValue, states_any: $event })"
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
