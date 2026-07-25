<!-- Backend: backend/steps/builtin/signal_emit.py -->
<template>
  <div v-if="tab === 'general'">
    <v-select
      :model-value="modelValue.kind"
      :items="ccLocalKinds"
      label="Signal kind"
      hint="CC-local kinds only -- rules can never emit a CTS-produced kind (e.g. fall_suspected)."
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, kind: $event })"
    />

    <TemplateInput
      :model-value="modelValue.person_id"
      label="Person ID"
      hint="Household member this signal is about. Supports {{template}} syntax."
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, person_id: $event })"
    />

    <v-row>
      <v-col cols="6">
        <v-select
          :model-value="modelValue.severity"
          :items="['info', 'warning', 'emergency']"
          label="Severity"
          @update:model-value="emit('update:modelValue', { ...modelValue, severity: $event })"
        />
      </v-col>
      <v-col cols="6">
        <v-text-field
          :model-value="modelValue.dedupe_minutes"
          type="number"
          min="0"
          label="Dedupe window (minutes)"
          hint="Skip the write if an unacknowledged signal of the same kind/person exists within this window. 0 disables dedup."
          persistent-hint
          @update:model-value="
            emit('update:modelValue', { ...modelValue, dedupe_minutes: Number($event) })
          "
        />
      </v-col>
    </v-row>

    <TemplateInput
      :model-value="String(modelValue.value ?? '')"
      label="Value"
      hint="A number, or a {{template}} resolving to one (e.g. an upstream llm_call confidence)."
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, value: $event })"
    />

    <div class="text-overline text-medium-emphasis mb-2">Context (JSON)</div>
    <TemplateInput
      :model-value="contextText"
      :multiline="true"
      :rows="4"
      hint='Freeform context merged with {rule_id, execution_id} provenance. String values support {{template}} syntax -- e.g. { "reason": "{{ steps.tea_verdict.outputs.tea_verdict.reason }}" }.'
      class="mb-4"
      @update:model-value="onContextInput"
    />

    <v-checkbox
      :model-value="modelValue.trigger_cooloff"
      label="Trigger cool-off if a signal was actually emitted"
      hide-details
      class="mb-2"
      @update:model-value="emit('update:modelValue', { ...modelValue, trigger_cooloff: $event })"
    />
  </div>
</template>

<script>
import TemplateInput from "./_shared/TemplateInput.vue";

// Mirrors backend.services.cts.signal_config.CC_LOCAL_SIGNAL_KINDS. This step's
// config_schema enum already enforces the allowlist server-side (write-time
// JSONSchema validation); this list only drives the picker and must be kept
// in sync with the backend tuple when a new CC-local kind is registered.
const CC_LOCAL_KINDS = ["inferred_dwell_exceeded", "tea_intent_suspected"];

export const stepDefaults = {
  kind: "",
  person_id: "",
  severity: "info",
  value: 1.0,
  context: {},
  dedupe_minutes: 60,
  trigger_cooloff: true,
};
export const stepTabs = [];

export function chips(cfg, { chip }) {
  const out = [];
  if (cfg.kind) out.push(chip(cfg.kind.replace(/_/g, " "), "mdi-bell-alert-outline", "orange"));
  if (cfg.severity) out.push(chip(cfg.severity, "mdi-alert-circle-outline"));
  return out;
}

// signal_emit's `context` field is a JSON object (like ha_action's `data`);
// round-trip it through a string for the textarea the same way.
export function onStepLoaded(cfg) {
  if (cfg && typeof cfg.context === "object" && cfg.context !== null) {
    cfg.context = JSON.stringify(cfg.context, null, 2);
  }
}

export function beforeSave(config) {
  if (typeof config.context === "string") {
    try {
      config.context = config.context.trim() ? JSON.parse(config.context) : {};
    } catch {
      config.context = {};
    }
  }
  return config;
}
</script>

<script setup>
import { computed } from "vue";

const props = defineProps({
  modelValue: { type: Object, required: true },
  tab: { type: String, default: "general" },
});
const emit = defineEmits(["update:modelValue"]);

const ccLocalKinds = CC_LOCAL_KINDS;

// modelValue.context may still be a live object (e.g. freshly created step
// before onStepLoaded's string normalization runs); tolerate both shapes.
const contextText = computed(() => {
  const ctx = props.modelValue.context;
  if (typeof ctx === "string") return ctx;
  if (ctx && typeof ctx === "object") return JSON.stringify(ctx, null, 2);
  return "";
});

function onContextInput(text) {
  emit("update:modelValue", { ...props.modelValue, context: text });
}
</script>
