<!-- Backend: backend/steps/builtin/condition.py -->
<template>
  <div v-if="tab === 'general'">
    <v-textarea
      :model-value="modelValue.expression"
      label="Condition Expression"
      :rows="3"
      auto-grow
      hint="Evaluated at runtime — true branch continues, false branch stops or takes the alternate path."
      persistent-hint
      class="mb-4 condition-expression-textarea"
      @update:model-value="emit('update:modelValue', { ...modelValue, expression: $event })"
    />

    <v-alert type="info" variant="tonal" density="compact" class="mb-4 text-body-2">
      <strong>No <code>{{ }}</code> curly braces needed.</strong>
      Write expressions directly using dotted paths
      (<code>steps.my_step.outputs.field</code>), comparison operators, and
      <code>and</code> / <code>or</code> / <code>not</code>.
      Use <code>jq("...")</code> with JMESPath syntax to filter and count arrays,
      and <code>icontains(path, "text")</code> for case-insensitive string checks.
      Step labels in expressions must match the labels you assigned your steps.
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
</script>

<script setup>
defineProps({
  modelValue: { type: Object, required: true },
  tab: { type: String, default: "general" },
});
const emit = defineEmits(["update:modelValue"]);

const conditionExamples = [
  {
    label: "LLM flagged an alert",
    description: "True when an llm_call step set is_notification_needed to true.",
    expr: "steps.llm_call_1.outputs.llm_response.is_notification_needed == true",
  },
  {
    label: "LLM response severity is high",
    description: "Case-sensitive string comparison on a nested field.",
    expr: 'steps.llm_call_1.outputs.llm_response.alert_level == "emergency"',
  },
  {
    label: "Scene description mentions a keyword",
    description: "icontains() checks case-insensitively — no need for lower().",
    expr: 'icontains(steps.scene_analysis_1.outputs.scene_description, "kitchen")',
  },
  {
    label: "Any detection with a specific label",
    description: "jq() + JMESPath filter; icontains() inside the filter handles mixed case.",
    expr: "jq(\"length(steps.scene_analysis_1.outputs.scene_detections[?icontains(label, 'person')])\") > 0",
  },
  {
    label: "High-confidence detection of a specific object",
    description: "Backtick-quoted numbers are JMESPath JSON literals for numeric comparisons.",
    expr: "jq(\"length(steps.scene_analysis_1.outputs.scene_detections[?label == 'person' && confidence > `0.9`])\") > 0",
  },
  {
    label: "Any medium or higher hazard present",
    description: "Filter the hazards list by severity field.",
    expr: "jq(\"length(steps.scene_analysis_1.outputs.scene_hazards[?severity == 'medium' || severity == 'high'])\") > 0",
  },
  {
    label: "Exact detection count",
    description: "Compare the count of matching detections to a specific number.",
    expr: "jq(\"length(steps.scene_analysis_1.outputs.scene_detections[?icontains(label, 'person')])\") == 2",
  },
  {
    label: "Person detected AND scene keyword match",
    description: "Combine a jq() filter with an icontains() check using and.",
    expr: "jq(\"length(steps.scene_analysis_1.outputs.scene_detections[?icontains(label, 'person')])\") > 0 and icontains(steps.scene_analysis_1.outputs.scene_description, \"kitchen\")",
  },
  {
    label: "Per-image: first image describes a specific room",
    description: "Access the description of a single image by index inside scene_images[].",
    expr: "jq(\"contains(lower(steps.scene_analysis_1.outputs.scene_images[0].scene_description), 'kitchen')\")",
  },
  {
    label: "Per-image: any image has a specific detection",
    description: "[] flattens detections across all images; pipe | applies the filter on the flat list.",
    expr: "jq(\"length(steps.scene_analysis_1.outputs.scene_images[].scene_detections[] | [?label == 'person'])\") > 0",
  },
  {
    label: "Per-image: second image has hazards",
    description: "Check the hazard list on a specific image by index.",
    expr: "jq(\"length(steps.scene_analysis_1.outputs.scene_images[1].scene_hazards)\") > 0",
  },
  {
    label: "Interactive prompt escalated",
    description: "Check what the user chose in an interactive_prompt step.",
    expr: 'steps.interactive_prompt_1.outputs.interactive_response.action == "escalate"',
  },
  {
    label: "Step output key exists",
    description: "exists() returns false if the path is missing or null.",
    expr: "exists(steps.scene_analysis_1.outputs.scene_description)",
  },
];
</script>

<style scoped>
.condition-expression-textarea :deep(textarea) {
  font-family: var(--cc-font-mono);
  font-size: 13px;
  line-height: 1.6;
}

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
</style>
