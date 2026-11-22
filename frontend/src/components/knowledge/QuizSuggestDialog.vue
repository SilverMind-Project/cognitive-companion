<template>
  <AppDialog
    :model-value="modelValue"
    size="md"
    persistent
    icon="mdi-auto-fix"
    label="Generate with AI"
    title="Suggest Quiz Draft"
    hint="Select a knowledge document and generation settings to draft quiz questions."
    confirm-label="Generate"
    :confirm-loading="generating"
    :confirm-disabled="!form.document_id"
    @update:model-value="$emit('update:modelValue', $event)"
    @confirm="submitSuggest"
  >
    <div class="pa-4">
      <LlmModelPicker
        v-model="form.modelId"
        :model-items="llmModelItems"
        label="LLM Model"
        hint="Model used for quiz generation"
        persistent-hint
        clearable
        class="mb-3"
      />
      <v-select
        v-model="form.document_id"
        :items="documentOptions"
        item-title="title"
        item-value="id"
        label="Knowledge Document"
        hint="Source document for generation"
        persistent-hint
        clearable
        class="mb-3"
      />
      <v-row dense align="center">
        <v-col cols="6">
          <v-text-field
            v-model="form.numQuestions"
            label="Questions"
            type="number"
            :min="1"
            :max="20"
            hide-details
          />
        </v-col>
        <v-col cols="6">
          <v-select
            v-model="form.mix"
            :items="mixOptions"
            item-title="title"
            item-value="value"
            label="Mix"
            hide-details
          />
        </v-col>
      </v-row>
    </div>
  </AppDialog>
</template>

<script setup>
import { reactive, ref, watch } from "vue";
import { api } from "@/services/api.js";
import { useNotify } from "@/composables/useNotify.js";
import AppDialog from "@/components/common/AppDialog.vue";
import LlmModelPicker from "@/components/common/LlmModelPicker.vue";

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  documentOptions: { type: Array, default: () => [] },
  llmModelItems: { type: Array, default: () => [] },
  initialDocumentId: { type: Number, default: null },
});

const emit = defineEmits(["update:modelValue", "suggested"]);
const { notify } = useNotify();

const generating = ref(false);
const mixOptions = [
  { title: "Mixed", value: "mixed" },
  { title: "Multiple Choice", value: "mc_only" },
];

const form = reactive({
  document_id: props.initialDocumentId,
  modelId: "",
  numQuestions: 5,
  mix: "mixed",
});

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      form.document_id = props.initialDocumentId;
      form.modelId = "";
      form.numQuestions = 5;
      form.mix = "mixed";
    }
  },
);

async function submitSuggest() {
  if (!form.document_id) {
    notify.warning("Select a knowledge document first.");
    return;
  }
  generating.value = true;
  try {
    const suggestion = await api.suggestQuiz(
      form.document_id,
      Number(form.numQuestions) || 5,
      form.mix,
      form.modelId || undefined,
    );
    notify.success(`Generated ${suggestion.questions?.length || 0} questions.`);
    emit("suggested", {
      document_id: form.document_id,
      suggestion,
    });
    emit("update:modelValue", false);
  } catch (err) {
    notify.error("Failed to generate quiz: " + (err.message || err));
  } finally {
    generating.value = false;
  }
}
</script>
