<!-- Backend: backend/steps/builtin/semantic_memory_query.py -->
<template>
  <v-combobox
    :model-value="modelValue.room_id"
    :items="availableRooms"
    label="Room ID (optional)"
    clearable
    hint="Filter by room. Supports {{template}} syntax."
    persistent-hint
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, room_id: $event })"
  />

  <v-switch
    :model-value="modelValue.use_trigger_room"
    label="Use trigger room"
    hint="When enabled, uses the trigger's room instead of the room ID above."
    persistent-hint
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, use_trigger_room: $event })"
  />

  <v-text-field
    :model-value="modelValue.since_minutes"
    label="Lookback (minutes)"
    type="number"
    :min="1"
    hint="How far back to search. Default: 60"
    persistent-hint
    class="mb-4"
    @update:model-value="
      emit('update:modelValue', { ...modelValue, since_minutes: Number($event) || 0 })
    "
  />

  <v-combobox
    :model-value="modelValue.objects_any"
    :items="[]"
    label="Objects (any)"
    multiple
    chips
    closable-chips
    hint="Only include observations containing any of these object labels. Supports {{template}} syntax."
    persistent-hint
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, objects_any: $event })"
  />

  <v-combobox
    :model-value="modelValue.hazard_flags_any"
    :items="[]"
    label="Hazard flags (any)"
    multiple
    chips
    closable-chips
    hint="Only include observations containing any of these hazard flags."
    persistent-hint
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, hazard_flags_any: $event })"
  />

  <div class="text-overline text-medium-emphasis mb-2">Text query (semantic search)</div>
  <TemplateInput
    :model-value="modelValue.query_text"
    :multiline="false"
    hint="Free-text query for semantic search. Supports {{template}} syntax. Type {{ for variable autocomplete."
    @update:model-value="emit('update:modelValue', { ...modelValue, query_text: $event })"
  />
  <div class="mb-4" />

  <v-text-field
    :model-value="modelValue.limit"
    label="Limit"
    type="number"
    :min="1"
    :max="50"
    hint="Maximum observations to return. Default: 5"
    persistent-hint
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, limit: Number($event) || 0 })"
  />

  <v-text-field
    :model-value="modelValue.output_key"
    label="Output Key"
    hint="pipeline_data key for the result. Default: memory_context"
    persistent-hint
    @update:model-value="emit('update:modelValue', { ...modelValue, output_key: $event })"
  />
</template>

<script>
import TemplateInput from "./_shared/TemplateInput.vue";

export const stepDefaults = {
  room_id: "",
  // Must match default_config in the backend step; it was false here and true
  // there, so a UI-created step queried a different room than a programmatic one.
  use_trigger_room: true,
  since_minutes: 60,
  objects_any: [],
  hazard_flags_any: [],
  query_text: "",
  limit: 5,
  output_key: "memory_context",
};
export const stepTabs = [];

export function chips(cfg, { chip }) {
  const out = [];
  if (cfg.output_key) out.push(chip(`-> ${cfg.output_key}`, "mdi-export-variant", "blue-grey"));
  // The config key is `limit`; `top_k` never existed, so this chip never rendered.
  if (cfg.limit) out.push(chip(`top ${cfg.limit}`, "mdi-format-list-numbered", undefined));
  return out;
}
</script>

<script setup>
defineProps({
  modelValue: { type: Object, required: true },
  availableRooms: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:modelValue"]);
</script>
