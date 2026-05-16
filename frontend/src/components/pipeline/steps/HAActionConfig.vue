<!-- Backend: backend/steps/builtin/ha_action.py -->
<template>
  <v-row>
    <v-col cols="6">
      <v-text-field
        :model-value="modelValue.domain"
        label="Domain"
        placeholder="e.g. light, switch, script"
        @update:model-value="emit('update:modelValue', { ...modelValue, domain: $event })"
      />
    </v-col>
    <v-col cols="6">
      <v-text-field
        :model-value="modelValue.service"
        label="Service"
        placeholder="e.g. turn_on, toggle"
        @update:model-value="emit('update:modelValue', { ...modelValue, service: $event })"
      />
    </v-col>
  </v-row>
  <v-combobox
    :model-value="modelValue.entity_id"
    :items="haEntityItems"
    :item-title="(item) => item.name ? `${item.name} (${item.entity_id})` : (item.entity_id || item)"
    :item-value="(item) => item.entity_id || item"
    label="Entity ID"
    placeholder="e.g. light.living_room"
    hint="Select from discovered entities or type an entity ID. Supports {{template}} syntax."
    persistent-hint
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, entity_id: $event })"
  />
  <div class="text-overline text-medium-emphasis mb-2">Service Data (JSON)</div>
  <TemplateInput
    :model-value="modelValue.data"
    :multiline="true"
    :rows="4"
    hint='JSON service data. String values support {{template}} syntax — e.g. { "brightness": 255, "message": "It is {{system.local_day_of_week}}" }. Type {{ for variable autocomplete.'
    @update:model-value="emit('update:modelValue', { ...modelValue, data: $event })"
  />
</template>

<script>
import TemplateInput from "./_shared/TemplateInput.vue";

export const stepDefaults = {
  domain: "",
  service: "",
  entity_id: "",
  data: "",
  trigger_cooloff: true,
};
export const stepTabs = [];
</script>

<script setup>
defineProps({
  modelValue: { type: Object, required: true },
  haEntityItems: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:modelValue"]);
</script>
