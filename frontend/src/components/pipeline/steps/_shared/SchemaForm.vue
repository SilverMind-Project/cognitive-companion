<template>
  <div>
    <template v-for="field in visibleFields" :key="field.name">
      <!-- template-textarea (with CodeMirror autocomplete) -->
      <TemplateInput
        v-if="field.widget === 'template-textarea'"
        :model-value="localConfig[field.name]"
        :label="field.label"
        :multiline="true"
        :rule-context="ruleContext"
        @update:model-value="setField(field.name, $event)"
      />

      <!-- template-text (with CodeMirror autocomplete) -->
      <TemplateInput
        v-else-if="field.widget === 'template-text'"
        :model-value="localConfig[field.name]"
        :label="field.label"
        :multiline="false"
        :rule-context="ruleContext"
        @update:model-value="setField(field.name, $event)"
      />

      <!-- text -->
      <v-text-field
        v-else-if="field.widget === 'text'"
        :model-value="localConfig[field.name]"
        :label="field.label"
        variant="outlined"
        density="comfortable"
        :hint="field.description"
        persistent-hint
        @update:model-value="setField(field.name, $event)"
      />

      <!-- textarea -->
      <v-textarea
        v-else-if="field.widget === 'textarea'"
        :model-value="localConfig[field.name]"
        :label="field.label"
        :rows="field.rows || 3"
        variant="outlined"
        density="comfortable"
        :hint="field.description"
        persistent-hint
        @update:model-value="setField(field.name, $event)"
      />

      <!-- number -->
      <v-text-field
        v-else-if="field.widget === 'number'"
        :model-value="localConfig[field.name]"
        :label="field.label"
        type="number"
        variant="outlined"
        density="comfortable"
        :min="field.min"
        :max="field.max"
        :hint="field.description"
        persistent-hint
        @update:model-value="setField(field.name, Number($event))"
      />

      <!-- slider -->
      <div v-else-if="field.widget === 'slider'" class="mb-4">
        <v-label class="text-caption mb-1">{{ field.label }}</v-label>
        <v-slider
          :model-value="localConfig[field.name]"
          :min="field.min || 0"
          :max="field.max || 100"
          :label="field.label"
          thumb-label
          @update:model-value="setField(field.name, $event)"
        />
      </div>

      <!-- checkbox -->
      <v-checkbox
        v-else-if="field.widget === 'checkbox'"
        :model-value="localConfig[field.name]"
        :label="field.label"
        density="comfortable"
        :hint="field.description"
        persistent-hint
        @update:model-value="setField(field.name, $event)"
      />

      <!-- select -->
      <v-select
        v-else-if="field.widget === 'select'"
        :model-value="localConfig[field.name]"
        :label="field.label"
        :items="field.options || []"
        variant="outlined"
        density="comfortable"
        :hint="field.description"
        persistent-hint
        @update:model-value="setField(field.name, $event)"
      />

      <!-- chips / combobox -->
      <v-combobox
        v-else-if="field.widget === 'chips'"
        :model-value="localConfig[field.name] || []"
        :label="field.label"
        multiple
        chips
        closable-chips
        variant="outlined"
        density="comfortable"
        :hint="field.description"
        persistent-hint
        @update:model-value="setField(field.name, $event)"
      />

      <!-- code-json -->
      <v-textarea
        v-else-if="field.widget === 'code-json'"
        :model-value="jsonTexts[field.name]"
        :label="field.label"
        rows="6"
        variant="outlined"
        density="comfortable"
        class="font-monospace"
        :hint="field.description"
        persistent-hint
        @update:model-value="onJsonFieldChange(field.name, $event)"
      />

      <!-- time-of-day -->
      <v-text-field
        v-else-if="field.widget === 'time-of-day'"
        :model-value="localConfig[field.name]"
        :label="field.label"
        type="time"
        variant="outlined"
        density="comfortable"
        :hint="field.description"
        persistent-hint
        @update:model-value="setField(field.name, $event)"
      />

      <!-- cron -->
      <CronBuilder
        v-else-if="field.widget === 'cron'"
        :model-value="localConfig[field.name]"
        @update:model-value="setField(field.name, $event)"
      />

      <!-- Fallback: text field for unknown widgets -->
      <v-text-field
        v-else
        :model-value="localConfig[field.name]"
        :label="`${field.label} (${field.widget})`"
        variant="outlined"
        density="comfortable"
        :hint="field.description"
        persistent-hint
        @update:model-value="setField(field.name, $event)"
      />
    </template>

    <v-divider v-if="visibleFields.length === 0" class="my-2" />
    <p v-if="visibleFields.length === 0" class="text-caption text-medium-emphasis">
      No configurable fields for this step type.
    </p>
  </div>
</template>

<script setup>
import { reactive, watch, computed, defineAsyncComponent } from "vue";
import CronBuilder from "../../CronBuilder.vue";

const TemplateInput = defineAsyncComponent(() => import("./TemplateInput.vue"));

const props = defineProps({
  modelValue: { type: Object, required: true },
  schema: { type: Object, default: () => ({}) },
  stepLabel: { type: String, default: "" },
  allSteps: { type: Array, default: () => [] },
});

const emit = defineEmits(["update:modelValue"]);

const localConfig = reactive({ ...props.modelValue });
const jsonTexts = reactive({});

const ruleContext = computed(() => {
  const labels = (props.allSteps || []).map((s) => s.label);
  return { labels };
});

// Initialize JSON text fields from config
for (const [key, propSchema] of Object.entries(props.schema.properties || {})) {
  const ui = propSchema["x-ui"] || {};
  if (ui.widget === "code-json") {
    jsonTexts[key] = JSON.stringify(props.modelValue[key] || {}, null, 2);
  }
}

// UI fields derived from schema
const visibleFields = computed(() => {
  const fields = [];
  const props_schema = props.schema.properties || {};
  for (const [name, prop] of Object.entries(props_schema)) {
    const ui = prop["x-ui"] || {};
    fields.push({
      name,
      label: ui.label || name,
      widget: ui.widget || "text",
      description: prop.description || "",
      rows: ui.rows || undefined,
      min: ui.min,
      max: ui.max,
      options: ui.options || [],
    });
  }
  return fields;
});

function setField(name, value) {
  localConfig[name] = value;
  emit("update:modelValue", { ...localConfig });
}

function onJsonFieldChange(name, text) {
  jsonTexts[name] = text;
  try {
    const parsed = JSON.parse(text);
    localConfig[name] = parsed;
    emit("update:modelValue", { ...localConfig });
  } catch {
    // Let user finish typing
  }
}

// Sync external changes inward
watch(
  () => props.modelValue,
  (newVal) => {
    for (const key of Object.keys(newVal || {})) {
      localConfig[key] = newVal[key];
    }
  },
  { deep: true },
);
</script>
