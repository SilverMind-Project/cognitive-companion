<template>
  <AppDialog
    v-model:section="activeSection"
    :model-value="modelValue"
    size="lg"
    persistent
    icon="mdi-help-box-outline"
    :label="mode === 'edit' ? 'Edit' : 'Create New'"
    title="Quiz"
    :sections="sections"
    :hint="
      mode === 'edit'
        ? 'Modify quiz metadata and edit individual questions.'
        : 'Generate questions from a knowledge document, or add them manually.'
    "
    :confirm-label="mode === 'edit' ? 'Save' : 'Create Quiz'"
    :confirm-loading="submitting"
    @update:model-value="$emit('update:modelValue', $event)"
    @cancel="onCancel"
    @confirm="onSubmit"
  >
    <template v-if="mode === 'create'" #section-generate>
      <LlmModelPicker
        v-model="generateModelId"
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
        <v-col cols="6" sm="3">
          <v-text-field
            v-model="generateNumQuestions"
            label="Questions"
            type="number"
            :min="1"
            :max="20"
            hide-details
          />
        </v-col>
        <v-col cols="6" sm="4">
          <v-select
            v-model="generateMix"
            :items="[
              { title: 'Mixed', value: 'mixed' },
              { title: 'Multiple Choice', value: 'mc_only' },
            ]"
            item-title="title"
            item-value="value"
            label="Mix"
            hide-details
          />
        </v-col>
        <v-col cols="12" sm="5">
          <v-btn
            color="secondary"
            variant="tonal"
            prepend-icon="mdi-auto-fix"
            :loading="generating"
            :disabled="!form.document_id"
            block
            @click="generateQuiz"
          >
            Generate
          </v-btn>
        </v-col>
      </v-row>
    </template>

    <template #section-details>
      <v-row dense>
        <v-col cols="12" sm="6">
          <v-text-field
            v-model="form.title"
            label="Title"
            :rules="[(r) => !!r || 'Title is required']"
          />
        </v-col>
        <v-col cols="12" sm="6">
          <v-select
            v-model="form.question_layout_id"
            :items="layouts"
            item-title="display_name"
            item-value="id"
            label="Question Layout"
            :rules="[(r) => !!r || 'Layout is required']"
          />
        </v-col>
      </v-row>
      <v-textarea
        v-model="form.intro_voice_template"
        label="Intro Voice Template"
        rows="3"
        class="mb-3"
      />
      <VoiceInstructionField
        v-model="form.voice_instruction"
        resource-type="quiz"
        :document-id="form.document_id"
        class="mb-3"
      />
      <v-combobox v-model="form.tags" label="Tags" multiple chips closable-chips />
    </template>

    <template #section-questions>
      <v-row v-if="mode === 'edit'" dense align="center" class="mb-2">
        <v-col cols="12" sm="8">
          <LlmModelPicker
            v-model="editLlmModelId"
            :model-items="llmModelItems"
            label="LLM Model"
            hint="Model used when regenerating individual questions"
            persistent-hint
            clearable
          />
        </v-col>
        <v-col cols="12" sm="4" class="text-sm-right">
          <v-btn size="small" variant="tonal" prepend-icon="mdi-plus" @click="addQuestion">
            Add Question
          </v-btn>
        </v-col>
      </v-row>
      <div v-else class="d-flex align-center mb-3">
        <span class="text-subtitle-2">Questions ({{ form.questions.length }})</span>
        <v-spacer />
        <v-btn size="small" variant="tonal" prepend-icon="mdi-plus" @click="addQuestion">
          Add Question
        </v-btn>
      </div>

      <div v-if="mode === 'edit'" class="text-subtitle-2 mb-2">
        Questions ({{ form.questions.length }})
      </div>
      <div v-if="!form.questions.length" class="text-body-2 text-medium-emphasis">
        No questions yet.
      </div>

      <QuizQuestionEditorCard
        v-for="(q, idx) in form.questions"
        :key="q._key"
        :question="q"
        :index="idx"
        :total="form.questions.length"
        :show-reorder="true"
        :show-regenerate="mode === 'edit'"
        :can-regenerate="Boolean(q.id)"
        @update:question="form.questions[idx] = { ...$event, _key: q._key }"
        @move="(dir) => moveQuestion(idx, dir)"
        @delete="removeQuestion(idx)"
        @regenerate="
          $emit('regenerate-question', { index: idx, question: q, modelId: editLlmModelId })
        "
      />
    </template>
  </AppDialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue";
import { useNotify } from "@/composables/useNotify.js";
import AppDialog from "@/components/common/AppDialog.vue";
import LlmModelPicker from "@/components/common/LlmModelPicker.vue";
import QuizQuestionEditorCard from "@/components/knowledge/QuizQuestionEditorCard.vue";
import { normalizeChoices, questionPayload } from "@/components/knowledge/quizChoices.js";
import VoiceInstructionField from "@/components/knowledge/VoiceInstructionField.vue";
import { createQuiz, suggestQuiz, updateQuiz } from "@/services/modules/quizzes";

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  mode: { type: String, default: "create" },
  quiz: { type: Object, default: null },
  layouts: { type: Array, default: () => [] },
  documentOptions: { type: Array, default: () => [] },
  llmModelItems: { type: Array, default: () => [] },
});

const emit = defineEmits(["update:modelValue", "saved", "regenerate-question"]);
const { notify } = useNotify();

const activeSection = ref(props.mode === "edit" ? "details" : "generate");
const detailsError = ref(false);
const submitting = ref(false);
const generating = ref(false);
const generateModelId = ref("");
const generateNumQuestions = ref(5);
const generateMix = ref("mixed");
const editLlmModelId = ref("");

const form = reactive({
  title: "",
  question_layout_id: null,
  intro_voice_template: "",
  voice_instruction: "",
  tags: [],
  document_id: null,
  questions: [],
});

// Stable identity for a question card while it is edited and reordered; a new question has
// no id yet, and keying by position mixed up cards when the order changed.
let keySeq = 0;
function withKey(q) {
  keySeq += 1;
  return { ...q, _key: `q${keySeq}` };
}

const sections = computed(() => {
  const base = [
    {
      key: "details",
      label: "Details",
      icon: "mdi-text-box-outline",
      error: detailsError.value,
    },
    {
      key: "questions",
      label: `Questions (${form.questions.length})`,
      icon: "mdi-help-circle-outline",
    },
  ];
  if (props.mode === "create") {
    return [
      {
        key: "generate",
        label: "Generate",
        icon: "mdi-auto-fix",
        description: "Draft the quiz from a knowledge document, then review the questions.",
      },
      ...base,
    ];
  }
  return base;
});

function blankQuestion() {
  return withKey({
    id: null,
    question_type: "multiple_choice",
    question_text: "",
    choices: normalizeChoices([{ text: "" }, { text: "" }]),
    expected_answer: "",
    explanation: "",
  });
}

function fromSaved(q) {
  return withKey({
    id: q.id ?? null,
    question_type: q.question_type || "multiple_choice",
    question_text: q.question_text || "",
    choices: normalizeChoices(q.choices),
    expected_answer: q.expected_answer || "",
    explanation: q.explanation || "",
  });
}

function resetForm() {
  if (props.mode === "edit" && props.quiz) {
    form.title = props.quiz.title || "";
    form.question_layout_id = props.quiz.question_layout_id || null;
    form.intro_voice_template = props.quiz.intro_voice_template || "";
    form.voice_instruction = props.quiz.voice_instruction || "";
    form.tags = [...(props.quiz.tags || [])];
    form.document_id = props.quiz.document_id || null;
    form.questions = [...(props.quiz.questions || [])].sort((a, b) => a.ord - b.ord).map(fromSaved);
    activeSection.value = "details";
  } else {
    form.title = "";
    form.question_layout_id = null;
    form.intro_voice_template = "";
    form.voice_instruction = "";
    form.tags = [];
    form.document_id = null;
    form.questions = [];
    activeSection.value = "generate";
  }
  detailsError.value = false;
  generateModelId.value = "";
  generateNumQuestions.value = 5;
  generateMix.value = "mixed";
  editLlmModelId.value = "";
}

watch(
  () => [props.modelValue, props.quiz, props.mode],
  ([open]) => {
    if (open) resetForm();
  },
  { immediate: true },
);

watch(
  () => [form.title, form.question_layout_id],
  ([title, layout]) => {
    if (title && layout) detailsError.value = false;
  },
);

function applySuggestion({ document_id: docId, suggestion }) {
  if (docId) form.document_id = docId;
  if (suggestion.title) form.title = suggestion.title;
  if (suggestion.intro_voice_template) {
    form.intro_voice_template = suggestion.intro_voice_template;
  }
  if (suggestion.voice_instruction && !form.voice_instruction) {
    form.voice_instruction = suggestion.voice_instruction;
  }
  if (suggestion.questions && suggestion.questions.length > 0) {
    form.questions = suggestion.questions.map((q) => fromSaved({ ...q, id: null }));
  }
  activeSection.value = "questions";
}

/** Replace the question at ``index`` with a regenerated draft (still unsaved). */
function applyRegenerated(index, suggestion) {
  const current = form.questions[index];
  if (!current || !suggestion) return;
  form.questions[index] = {
    ...fromSaved({ ...current, ...suggestion, id: current.id }),
    _key: current._key,
  };
}

defineExpose({ applySuggestion, applyRegenerated });

async function generateQuiz() {
  if (!form.document_id) {
    notify.warning("Select a knowledge document first.");
    return;
  }
  generating.value = true;
  try {
    const suggestion = await suggestQuiz(
      form.document_id,
      Number(generateNumQuestions.value) || 5,
      generateMix.value,
      generateModelId.value || undefined,
    );
    applySuggestion({ document_id: form.document_id, suggestion });
    notify.success(`Generated ${suggestion.questions?.length || 0} questions.`);
  } catch (err) {
    notify.error("Failed to generate quiz: " + (err.message || err));
  } finally {
    generating.value = false;
  }
}

function addQuestion() {
  form.questions.push(blankQuestion());
}

function removeQuestion(idx) {
  form.questions.splice(idx, 1);
}

function moveQuestion(idx, direction) {
  const target = idx + direction;
  if (target < 0 || target >= form.questions.length) return;
  const [moved] = form.questions.splice(idx, 1);
  form.questions.splice(target, 0, moved);
}

function onCancel() {
  resetForm();
  emit("update:modelValue", false);
}

function metadata() {
  return {
    title: form.title,
    question_layout_id: form.question_layout_id,
    intro_voice_template: form.intro_voice_template,
    voice_instruction: form.voice_instruction,
    tags: form.tags,
  };
}

async function onSubmit() {
  if (props.mode === "create" && (!form.title || !form.question_layout_id)) {
    detailsError.value = true;
    activeSection.value = "details";
    notify.warning("Title and Layout are required.");
    return;
  }
  submitting.value = true;
  try {
    if (props.mode === "edit" && props.quiz?.id) {
      // One transaction for the details and the whole list: added, edited, removed, and
      // reordered questions are saved with the title and tags, or nothing changes.
      await updateQuiz(props.quiz.id, {
        ...metadata(),
        questions: form.questions.map((q) => ({
          ...(q.id ? { id: q.id } : {}),
          ...questionPayload(q),
        })),
      });
      notify.success("Quiz updated.");
    } else {
      await createQuiz({
        ...metadata(),
        document_id: form.document_id || undefined,
        questions: form.questions.map(questionPayload),
      });
      notify.success(`Quiz created with ${form.questions.length} question(s).`);
    }
    emit("saved");
    emit("update:modelValue", false);
  } catch (err) {
    notify.error(
      `Failed to ${props.mode === "edit" ? "update" : "create"} quiz: ` + (err.message || err),
    );
  } finally {
    submitting.value = false;
  }
}
</script>
