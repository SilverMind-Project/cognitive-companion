<!-- Backend: backend/steps/builtin/gate_verdict.py -->
<template>
  <div v-if="tab === 'general'">
    <TemplateInput
      :model-value="modelValue.complete_if"
      label="Complete if (expression)"
      multiline
      :rows="3"
      hint="Truthy means the step is complete. Wrap in {{ }}. Reuses the condition grammar (dotted paths, and/or/not, JMESPath pipes)."
      class="mb-4 gate-verdict-expression-input"
      @update:model-value="emit('update:modelValue', { ...modelValue, complete_if: $event })"
    />

    <v-alert type="info" variant="tonal" density="compact" class="mb-4 text-body-2">
      This is the single verdict sink of the gate graph. The expression usually reads a model
      output, e.g.
      <code>steps.llm_call_1.outputs.vision_response.complete</code>. If the verdict is never
      reached, or the expression is unparseable, or confidence is below the threshold, the gate
      fails closed (complete = false).
    </v-alert>

    <v-text-field
      :model-value="modelValue.confidence_path"
      label="Confidence path"
      density="compact"
      hide-details
      class="mb-3"
      placeholder="steps.llm_call_1.outputs.vision_response.confidence"
      @update:model-value="emit('update:modelValue', { ...modelValue, confidence_path: $event })"
    />

    <v-text-field
      :model-value="modelValue.reason_path"
      label="Reason path"
      density="compact"
      hide-details
      class="mb-3"
      placeholder="steps.llm_call_1.outputs.vision_response.reason"
      @update:model-value="emit('update:modelValue', { ...modelValue, reason_path: $event })"
    />

    <v-text-field
      :model-value="modelValue.min_confidence ?? ''"
      label="Minimum confidence"
      type="number"
      step="0.05"
      min="0"
      max="1"
      density="compact"
      clearable
      placeholder="Inherit from the step's vision profile"
      persistent-placeholder
      hint="If complete is true but confidence is below this, the verdict is forced to false. Leave empty to use the confirm or watch profile's threshold."
      persistent-hint
      style="max-width: 360px"
      data-test="gate-verdict-min-confidence"
      @update:model-value="updateMinConfidence"
    />
  </div>
</template>

<script>
export const stepDefaults = {
  complete_if: "",
  confidence_path: "",
  reason_path: "",
};
export const stepTabs = [];
</script>

<script setup>
import TemplateInput from "./_shared/TemplateInput.vue";

const props = defineProps({
  modelValue: { type: Object, required: true },
  tab: { type: String, default: "general" },
});
const emit = defineEmits(["update:modelValue"]);

// Empty means inherit: the key is removed rather than stored, because any
// stored value would override the step profile's threshold for good.
function updateMinConfidence(raw) {
  const { min_confidence: _dropped, ...rest } = props.modelValue;
  const value = raw === "" || raw === null || raw === undefined ? NaN : Number(raw);
  emit(
    "update:modelValue",
    Number.isFinite(value) ? { ...rest, min_confidence: Math.min(1, Math.max(0, value)) } : rest,
  );
}
</script>

<style scoped>
.gate-verdict-expression-input :deep(.cm-content) {
  font-family: var(--cc-font-mono);
  font-size: 13px;
  line-height: 1.6;
}
</style>
