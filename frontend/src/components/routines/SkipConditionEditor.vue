<template>
  <div class="skip-condition" data-test="skip-condition-editor">
    <v-select
      :model-value="kind"
      :items="KIND_ITEMS"
      item-title="title"
      item-value="value"
      label="Skip this step when"
      density="compact"
      hide-details
      data-test="skip-kind"
      @update:model-value="setKind"
    />

    <ActivitySignalFields
      v-if="kind === 'activity_signal'"
      :model-value="modelValue"
      activity-hint="Skipped on entry when this activity was already recorded."
      class="mt-2"
      @update:model-value="emitCondition"
    />

    <ZonePicker
      v-if="kind === 'zone_presence'"
      :model-value="modelValue?.zone_id ?? null"
      :room-id="roomId"
      label="Zone (leave empty for the step's zone)"
      class="mt-2"
      data-test="skip-zone"
      @update:model-value="emitCondition({ ...modelValue, zone_id: $event ?? null })"
    />
  </div>
</template>

<script setup>
/**
 * A step's skip condition, limited to the kinds the guided runtime evaluates.
 * Caregivers never type JSON; the backend rejects any other shape.
 */
import { computed } from "vue";
import ActivitySignalFields from "./ActivitySignalFields.vue";
import ZonePicker from "./ZonePicker.vue";

const NONE = "none";
const KIND_ITEMS = [
  { title: "Never (always do this step)", value: NONE },
  { title: "She says she already did it", value: "response_says_done" },
  { title: "The activity was already recorded", value: "activity_signal" },
  { title: "She is already in the zone", value: "zone_presence" },
];

const props = defineProps({
  modelValue: { type: Object, default: null },
  roomId: { type: Number, default: null },
});
const emit = defineEmits(["update:modelValue"]);

const kind = computed(() => props.modelValue?.kind ?? NONE);

function emitCondition(value) {
  emit("update:modelValue", { ...value, kind: kind.value });
}

function setKind(next) {
  if (next === NONE) emit("update:modelValue", null);
  else if (next === "zone_presence") emit("update:modelValue", { kind: next, zone_id: null });
  else emit("update:modelValue", { kind: next });
}
</script>
