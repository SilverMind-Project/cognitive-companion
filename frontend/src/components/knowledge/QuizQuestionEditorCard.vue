<template>
  <v-card :variant="cardVariant" :class="cardClass">
    <div class="d-flex align-center mb-2">
      <div v-if="showReorder" class="d-flex align-center mr-2">
        <v-btn
          icon="mdi-chevron-up"
          size="x-small"
          variant="text"
          :disabled="index === 0"
          @click="$emit('move', -1)"
        />
        <v-btn
          icon="mdi-chevron-down"
          size="x-small"
          variant="text"
          :disabled="index === total - 1"
          @click="$emit('move', 1)"
        />
      </div>
      <v-chip v-else size="x-small" color="primary" variant="tonal" class="mr-2">
        {{ index + 1 }}
      </v-chip>

      <v-radio-group
        :model-value="draft.question_type"
        inline
        density="compact"
        hide-details
        @update:model-value="updateField('question_type', $event, true)"
      >
        <v-radio label="Multiple Choice" value="multiple_choice" />
        <v-radio label="Open Ended" value="open_ended" />
      </v-radio-group>

      <v-spacer />

      <v-btn
        v-if="showRegenerate"
        icon="mdi-refresh"
        size="x-small"
        variant="text"
        color="secondary"
        :disabled="!canRegenerate"
        class="mr-1"
        @click="$emit('regenerate')"
      />
      <v-btn
        v-if="!showReorder"
        icon="mdi-close"
        size="x-small"
        variant="text"
        color="error"
        @click="$emit('delete')"
      />
    </div>

    <v-textarea
      :model-value="draft.question_text"
      label="Question"
      rows="2"
      density="compact"
      hide-details
      class="mb-2"
      @update:model-value="updateField('question_text', $event)"
      @change="emitChange"
    />

    <div v-if="draft.question_type === 'multiple_choice'" class="ml-2 mb-2">
      <div v-for="(ch, ci) in draft.choices" :key="ci" class="d-flex align-center ga-1 mb-1">
        <v-text-field
          :model-value="ch.text"
          label="Choice text"
          density="compact"
          hide-details
          style="min-width: 200px"
          @update:model-value="updateChoice(ci, 'text', $event)"
          @change="emitChange"
        />
        <v-checkbox
          :model-value="ch.is_correct"
          label="Correct"
          density="compact"
          hide-details
          @update:model-value="updateChoice(ci, 'is_correct', $event, true)"
          @change="emitChange"
        />
        <v-btn
          icon="mdi-close"
          size="x-small"
          variant="text"
          color="error"
          @click="removeChoice(ci)"
        />
      </div>
      <v-btn size="x-small" variant="text" prepend-icon="mdi-plus" @click="addChoice">
        Choice
      </v-btn>
    </div>

    <v-text-field
      v-else
      :model-value="draft.expected_answer"
      label="Expected answer"
      density="compact"
      hide-details
      class="mb-2"
      @update:model-value="updateField('expected_answer', $event)"
      @change="emitChange"
    />

    <v-textarea
      :model-value="draft.explanation"
      label="Explanation"
      rows="1"
      density="compact"
      hide-details
      @update:model-value="updateField('explanation', $event)"
      @change="emitChange"
    />

    <div v-if="showReorder" class="mt-2">
      <v-btn color="error" size="x-small" variant="text" @click="$emit('delete')">
        Delete Question
      </v-btn>
    </div>
  </v-card>
</template>

<script setup>
import { reactive, watch } from "vue";

const props = defineProps({
  question: { type: Object, required: true },
  index: { type: Number, default: 0 },
  total: { type: Number, default: 1 },
  showReorder: { type: Boolean, default: false },
  showRegenerate: { type: Boolean, default: false },
  canRegenerate: { type: Boolean, default: false },
  cardVariant: { type: String, default: "tonal" },
  cardClass: { type: String, default: "mb-3 pa-3" },
});

const emit = defineEmits(["update:question", "change", "delete", "move", "regenerate"]);

const draft = reactive({
  id: null,
  question_type: "multiple_choice",
  question_text: "",
  choices: [],
  expected_answer: "",
  explanation: "",
});

function syncFromProp(q) {
  if (!q) return;
  draft.id = q.id ?? null;
  draft.question_type = q.question_type || "multiple_choice";
  draft.question_text = q.question_text || "";
  draft.choices = (q.choices || []).map((c) => ({ ...c }));
  draft.expected_answer = q.expected_answer || "";
  draft.explanation = q.explanation || "";
}

watch(
  () => props.question,
  (q) => syncFromProp(q),
  { immediate: true, deep: true },
);

function buildSnapshot() {
  return {
    ...props.question,
    id: draft.id,
    question_type: draft.question_type,
    question_text: draft.question_text,
    choices: draft.choices.map((c) => ({ ...c })),
    expected_answer: draft.expected_answer,
    explanation: draft.explanation,
  };
}

function updateField(field, value, immediateChange = false) {
  draft[field] = value;
  const next = buildSnapshot();
  emit("update:question", next);
  if (immediateChange) {
    emit("change", next);
  }
}

function updateChoice(choiceIndex, field, value, immediateChange = false) {
  if (!draft.choices[choiceIndex]) return;
  draft.choices[choiceIndex] = {
    ...draft.choices[choiceIndex],
    [field]: value,
  };
  const next = buildSnapshot();
  emit("update:question", next);
  if (immediateChange) {
    emit("change", next);
  }
}

function addChoice() {
  draft.choices.push({ id: null, text: "", is_correct: false });
  const next = buildSnapshot();
  emit("update:question", next);
  emit("change", next);
}

function removeChoice(choiceIndex) {
  draft.choices.splice(choiceIndex, 1);
  const next = buildSnapshot();
  emit("update:question", next);
  emit("change", next);
}

function emitChange() {
  const next = buildSnapshot();
  emit("update:question", next);
  emit("change", next);
}
</script>
