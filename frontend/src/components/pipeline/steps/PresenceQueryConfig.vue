<!-- Backend: backend/steps/builtin/presence_query.py -->
<template>
  <v-form ref="form" v-model="formValid">
    <v-combobox
      :model-value="modelValue.person_id"
      :items="availablePersons"
      label="Person"
      hint="Person to look up. Supports {{template}} syntax. Leave empty to use the first person found in pipeline_data.persons or pipeline_data.person_id."
      persistent-hint
      variant="outlined"
      density="compact"
      hide-details="auto"
      rounded="lg"
      clearable
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, person_id: $event })"
    />

    <v-divider class="mb-4" />

    <div class="text-overline text-medium-emphasis mb-2">
      Recent dementia signal filter (optional)
    </div>

    <v-combobox
      :model-value="modelValue.signal_kind"
      :items="knownSignalKinds"
      label="Signal Kind"
      hint="Filter by a single dementia-signal kind. Leave empty to include all kinds."
      persistent-hint
      variant="outlined"
      density="compact"
      hide-details="auto"
      rounded="lg"
      clearable
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, signal_kind: $event })"
    />

    <v-row>
      <v-col cols="12" md="6">
        <v-select
          :model-value="modelValue.signal_severity_min"
          :items="severityItems"
          item-title="label"
          item-value="value"
          label="Minimum Severity"
          variant="outlined"
          density="compact"
          hide-details="auto"
          rounded="lg"
          @update:model-value="
            emit('update:modelValue', { ...modelValue, signal_severity_min: $event })
          "
        />
      </v-col>
      <v-col cols="12" md="6">
        <v-text-field
          :model-value="modelValue.signal_window_minutes"
          label="Lookback (minutes)"
          type="number"
          :min="1"
          :max="1440"
          :rules="[
            (v) => (Number.isInteger(Number(v)) && v >= 1 && v <= 1440) || 'Must be 1..1440',
          ]"
          variant="outlined"
          density="compact"
          hide-details="auto"
          rounded="lg"
          @update:model-value="
            emit('update:modelValue', { ...modelValue, signal_window_minutes: Number($event) || 0 })
          "
        />
      </v-col>
    </v-row>

    <v-text-field
      :model-value="modelValue.output_key"
      label="Output Key"
      :rules="[
        (v) =>
          /^[a-z][a-z0-9_]*$/.test(v) ||
          'Lowercase letters, digits, underscores only; must start with a letter.',
      ]"
      hint="pipeline_data key for the result dict. Default: presence."
      persistent-hint
      variant="outlined"
      density="compact"
      hide-details="auto"
      rounded="lg"
      class="mt-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, output_key: $event })"
    />

    <v-alert type="info" variant="tonal" density="compact" class="mt-4">
      This step also writes flat keys at the top of pipeline_data: <code>presence_status</code>,
      <code>presence_room_name</code>, <code>presence_dwell_minutes</code>,
      <code>presence_at_home</code>, <code>presence_asleep</code>, <code>presence_away</code>. Use
      these directly in <code>condition</code> step expressions.
    </v-alert>
  </v-form>
</template>

<script>
export const stepDefaults = {
  person_id: "",
  signal_kind: "",
  signal_severity_min: null,
  signal_window_minutes: null,
  output_key: "presence",
};
export const stepTabs = [];
</script>

<script setup>
import { ref } from "vue";

defineProps({
  modelValue: { type: Object, required: true },
  availablePersons: { type: Array, default: () => [] },
  knownSignalKinds: { type: Array, default: () => [] },
  severityItems: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:modelValue"]);

const formValid = ref(true);
const form = ref(null);

defineExpose({ form, formValid });
</script>
