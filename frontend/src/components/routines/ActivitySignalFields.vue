<template>
  <v-row class="mt-0" dense>
    <v-col cols="7">
      <v-select
        :model-value="modelValue?.activity_type ?? null"
        :items="items"
        item-title="title"
        item-value="value"
        label="Activity"
        density="compact"
        :hint="activityHint"
        persistent-hint
        data-test="activity-type"
        @update:model-value="update('activity_type', $event)"
      />
    </v-col>
    <v-col cols="5">
      <v-text-field
        :model-value="modelValue?.window_minutes ?? ''"
        label="Within the last (minutes)"
        type="number"
        min="1"
        density="compact"
        :placeholder="String(DEFAULT_WINDOW_MINUTES)"
        persistent-placeholder
        hide-details="auto"
        data-test="activity-window"
        @update:model-value="update('window_minutes', toMinutes($event))"
      />
    </v-col>
  </v-row>
</template>

<script setup>
/**
 * An activity-signal condition in the one shape the backend evaluates:
 * `{ activity_type, window_minutes }`. Shared by the completion gate and the
 * skip condition so the two can never drift apart again.
 */
import { useActivityTypeOptions } from "@/composables/useActivityTypeOptions.js";

// The evaluator's own default look-back.
const DEFAULT_WINDOW_MINUTES = 10;

const props = defineProps({
  modelValue: { type: Object, default: null },
  activityHint: { type: String, default: "" },
});
const emit = defineEmits(["update:modelValue"]);

const { items } = useActivityTypeOptions();

function toMinutes(raw) {
  const value = Number(raw);
  return raw === "" || raw === null || !Number.isFinite(value) || value <= 0 ? null : value;
}

function update(key, value) {
  const next = { ...(props.modelValue ?? {}), [key]: value };
  if (next.window_minutes === null) delete next.window_minutes;
  emit("update:modelValue", next);
}
</script>
