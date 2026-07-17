<template>
  <div>
    <v-select
      :model-value="modelValue"
      :items="modelItems"
      :item-title="(m) => m.name || m.id"
      :item-value="(m) => m.id"
      :label="label"
      :hint="hint || 'Select an LLM model'"
      :persistent-hint="!!hint || persistentHint"
      :clearable="clearable"
      :disabled="disabled"
      variant="outlined"
      density="compact"
      hide-details
      @update:model-value="$emit('update:modelValue', $event)"
    >
      <template #item="{ item, props: itemProps }">
        <v-list-item v-bind="itemProps">
          <template #append>
            <div class="d-flex ga-1 ml-2">
              <v-chip
                v-for="cap in item.raw.capabilities || []"
                :key="cap"
                size="x-small"
                :color="capabilityColor(cap)"
                variant="tonal"
                >{{ cap }}</v-chip
              >
            </div>
          </template>
        </v-list-item>
      </template>
    </v-select>

    <div v-if="selectedModel && showDetails" class="d-flex ga-1 mt-2 flex-wrap">
      <v-chip
        v-for="cap in selectedModel.capabilities"
        :key="cap"
        size="x-small"
        :color="capabilityColor(cap)"
        variant="tonal"
        >{{ cap }}</v-chip
      >
      <v-chip size="x-small" variant="outlined">{{ selectedModel.api_type }}</v-chip>
      <v-chip v-if="selectedModel.guided_decoding" size="x-small" color="success" variant="tonal"
        >guided decoding</v-chip
      >
      <v-chip
        v-if="selectedModel.supports_thinking"
        size="x-small"
        color="secondary"
        variant="tonal"
        >thinking</v-chip
      >
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  modelValue: { type: String, default: "" },
  modelItems: { type: Array, default: () => [] },
  label: { type: String, default: "Model" },
  hint: { type: String, default: "" },
  persistentHint: { type: Boolean, default: false },
  clearable: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  showDetails: { type: Boolean, default: true },
});

defineEmits(["update:modelValue"]);

const selectedModel = computed(
  () => props.modelItems.find((m) => m.id === props.modelValue) || null,
);

function capabilityColor(cap) {
  return { text: "primary", vision: "indigo", translation: "teal" }[cap] || "grey";
}
</script>
