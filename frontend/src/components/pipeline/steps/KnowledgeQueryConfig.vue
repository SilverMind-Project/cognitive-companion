<!-- Backend: backend/steps/builtin/knowledge_query.py -->
<template>
  <div>
    <TemplateInput
      :model-value="modelValue.query_text"
      label="Question"
      :multiline="true"
      :rows="2"
      hint="What to ask the approved knowledge documents. Type {{ to insert pipeline values, e.g. {{steps.where.outputs.room}}."
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, query_text: $event })"
    />

    <v-combobox
      :model-value="modelValue.tags || []"
      label="Only documents tagged (optional)"
      multiple
      chips
      closable-chips
      hint="Searches only documents carrying any of these tags. Blank searches every approved document."
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, tags: $event })"
    />

    <div class="text-overline text-medium-emphasis mb-2">Retrieval (optional overrides)</div>
    <v-row dense class="mb-2">
      <v-col cols="12" sm="6">
        <v-text-field
          :model-value="modelValue.top_k ?? ''"
          label="Passages to retrieve"
          type="number"
          :min="1"
          :max="20"
          placeholder="Household default"
          hint="Blank matches the voice companion (knowledge.retrieval_top_k)."
          persistent-hint
          @update:model-value="emitNumber('top_k', $event, 1, 20, parseInt)"
        />
      </v-col>
      <v-col cols="12" sm="6">
        <v-text-field
          :model-value="modelValue.min_similarity ?? ''"
          label="Minimum match strength (0 to 1)"
          type="number"
          :min="0"
          :max="1"
          :step="0.05"
          placeholder="Household default"
          hint="Blank matches the voice companion (knowledge.min_similarity). Lower admits weaker matches."
          persistent-hint
          @update:model-value="emitNumber('min_similarity', $event, 0, 1, parseFloat)"
        />
      </v-col>
    </v-row>

    <v-switch
      :model-value="modelValue.log_interaction"
      label="Record in the Senior Knowledge Queries history"
      hint="Off by default: an automated rule asking questions is not the senior asking them."
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, log_interaction: $event })"
    />

    <v-alert type="info" variant="tonal" density="compact">
      Later steps can use <code>answer_text</code>, <code>has_answer</code> (false when the
      documents do not answer the question), and <code>chunks</code> (the retrieved passages), e.g.
      <code v-pre>{{steps.&lt;label&gt;.outputs.answer_text}}</code>.
    </v-alert>
  </div>
</template>

<script>
import TemplateInput from "./_shared/TemplateInput.vue";

export const stepDefaults = {
  query_text: "",
  tags: [],
  log_interaction: false,
};
export const stepTabs = [];

export function chips(cfg, { chip, truncate }) {
  const out = [];
  if (cfg.query_text) out.push(chip(truncate(cfg.query_text, 40), "mdi-help-circle-outline"));
  if (cfg.tags?.length) out.push(chip(`tags: ${cfg.tags.join(", ")}`, "mdi-tag-outline"));
  if (cfg.top_k) out.push(chip(`top ${cfg.top_k}`, "mdi-format-list-numbered"));
  if (cfg.log_interaction) out.push(chip("logged", "mdi-history"));
  return out;
}
</script>

<script setup>
const props = defineProps({
  modelValue: { type: Object, required: true },
});
const emit = defineEmits(["update:modelValue"]);

// A blank field means "use the household default", stored as null so the backend inherits
// knowledge.retrieval_top_k / knowledge.min_similarity rather than a copy that can drift.
function emitNumber(key, raw, min, max, parse) {
  const parsed = raw === "" || raw === null ? null : parse(raw);
  const value =
    parsed === null || Number.isNaN(parsed) ? null : Math.min(max, Math.max(min, parsed));
  emit("update:modelValue", { ...props.modelValue, [key]: value });
}
</script>
