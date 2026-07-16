<!-- Backend: backend/steps/builtin/condition.py -->
<template>
  <div v-if="tab === 'general'">
    <TemplateInput
      :model-value="modelValue.expression"
      label="Condition Expression"
      multiline
      :rows="3"
      hint="Wrap the expression in {{ }}. True branch continues; false branch stops or takes the alternate path."
      class="mb-4 condition-expression-input"
      @update:model-value="emit('update:modelValue', { ...modelValue, expression: $event })"
    />

    <v-alert type="info" variant="tonal" density="compact" class="mb-4 text-body-2">
      Write condition expressions inside <code>&#123;&#123; &#125;&#125;</code> curly braces.
      Use dotted paths (<code>steps.my_step.outputs.field</code>), comparison operators, and
      <code>and</code> / <code>or</code> / <code>not</code>.
      Pipe JMESPath for array operations: <code>steps.my_step.outputs.list | length(@)</code>.
      Use <code>icontains(path, "text")</code> for case-insensitive checks.
      Type <code>&#123;&#123;</code> in the expression field to see autocomplete suggestions.
    </v-alert>

    <v-expansion-panels variant="accordion" class="mb-4">
      <v-expansion-panel>
        <v-expansion-panel-title class="text-body-2 font-weight-medium">
          <v-icon size="small" class="mr-2">mdi-code-tags</v-icon>
          Examples — click any to load into the expression field
        </v-expansion-panel-title>
        <v-expansion-panel-text class="pa-0">
          <v-list density="compact" class="condition-examples-list">
            <v-list-item
              v-for="ex in conditionExamples"
              :key="ex.label"
              class="condition-example-row py-2"
              @click="emit('update:modelValue', { ...modelValue, expression: ex.expr })"
            >
              <div class="text-caption font-weight-medium mb-1">{{ ex.label }}</div>
              <div class="text-caption text-medium-emphasis mb-1">{{ ex.description }}</div>
              <code class="condition-example-code">{{ ex.expr }}</code>
            </v-list-item>
          </v-list>
        </v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>

    <v-checkbox
      :model-value="modelValue.trigger_cooloff"
      label="Trigger cool-off if condition is met"
      hide-details
      @update:model-value="emit('update:modelValue', { ...modelValue, trigger_cooloff: $event })"
    />
  </div>
</template>

<script>
export const stepDefaults = { expression: "", trigger_cooloff: false };
export const stepTabs = [];

export function chips(cfg, { chip }) {
  const out = [];
  if (cfg.trigger_cooloff) out.push(chip("cooloff on match", "mdi-timer-outline", "blue-grey"));
  return out;
}
</script>

<script setup>
import TemplateInput from "./_shared/TemplateInput.vue";

defineProps({
  modelValue: { type: Object, required: true },
  tab: { type: String, default: "general" },
});
const emit = defineEmits(["update:modelValue"]);

const conditionExamples = [
  {
    label: "LLM flagged an alert",
    description: "True when an llm_call step set is_notification_needed to true.",
    expr: "{{ steps.llm_call_1.outputs.llm_response.is_notification_needed == true }}",
  },
  {
    label: "LLM response severity is high",
    description: "Case-sensitive string comparison on a nested field.",
    expr: '{{ steps.llm_call_1.outputs.llm_response.alert_level == "emergency" }}',
  },
  {
    label: "Scene description mentions a keyword",
    description: "icontains() checks case-insensitively — no need for lower().",
    expr: '{{ icontains(steps.scene_analysis_1.outputs.scene_description, "kitchen") }}',
  },
  {
    label: "Any detection with a specific label",
    description: "Pipe JMESPath filter; icontains() handles mixed case.",
    expr: '{{ steps.scene_analysis_1.outputs.scene_detections | length([?icontains(label, \'person\')]) > 0 }}',
  },
  {
    label: "Any medium or higher hazard present",
    description: "Filter the hazards list by severity field.",
    expr: "{{ steps.scene_analysis_1.outputs.scene_hazards | length([?severity == 'medium' || severity == 'high']) > 0 }}",
  },
  {
    label: "Exact detection count",
    description: "Compare the count of matching detections to a specific number.",
    expr: '{{ steps.scene_analysis_1.outputs.scene_detections | length([?icontains(label, \'person\')]) == 2 }}',
  },
  {
    label: "Person detected AND scene keyword match",
    description: "Combine a pipe filter with an icontains() check using and.",
    expr: '{{ steps.scene_analysis_1.outputs.scene_detections | length([?icontains(label, \'person\')]) > 0 and icontains(steps.scene_analysis_1.outputs.scene_description, "kitchen") }}',
  },
  {
    label: "Interactive prompt escalated",
    description: "Check what the user chose in an interactive_prompt step.",
    expr: '{{ steps.interactive_prompt_1.outputs.interactive_response.action == "escalate" }}',
  },
  {
    label: "Step output key exists",
    description: "exists() returns false if the path is missing or null.",
    expr: "{{ exists(steps.scene_analysis_1.outputs.scene_description) }}",
  },
];
</script>

<style scoped>
.condition-examples-list {
  background: transparent;
}

.condition-example-row {
  cursor: pointer;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  transition: background-color 0.12s ease;
}

.condition-example-row:last-child {
  border-bottom: none;
}

.condition-example-row:hover {
  background-color: rgba(10, 132, 255, 0.07);
}

.condition-example-code {
  display: block;
  font-family: var(--cc-font-mono);
  font-size: 11.5px;
  color: var(--cc-brand);
  background: rgba(10, 132, 255, 0.06);
  border-radius: 4px;
  padding: 4px 8px;
  white-space: pre-wrap;
  word-break: break-all;
  margin-top: 2px;
}

.condition-expression-input :deep(.cm-content) {
  font-family: var(--cc-font-mono);
  font-size: 13px;
  line-height: 1.6;
}
</style>
