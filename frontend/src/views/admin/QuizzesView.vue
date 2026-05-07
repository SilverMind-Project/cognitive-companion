<template>
  <div>
    <v-card class="pa-4">
      <v-row align="center" dense>
        <v-col cols="6" sm="3">
          <v-select
            v-model="filters.status"
            :items="statusOptions"
            label="Status"
            density="compact"
            hide-details
            clearable
            @update:model-value="fetchQuizzes"
          />
        </v-col>
        <v-col cols="6" sm="3">
          <v-combobox
            v-model="filters.tags"
            label="Tags"
            multiple
            density="compact"
            hide-details
            clearable
            @update:model-value="fetchQuizzes"
          />
        </v-col>
        <v-col cols="auto" class="ml-auto">
          <v-btn color="primary" prepend-icon="mdi-plus" @click="showCreateDialog = true">
            New Quiz
          </v-btn>
        </v-col>
      </v-row>
    </v-card>

    <v-data-table
      :headers="headers"
      :items="quizzes"
      :loading="loading"
      :items-per-page="20"
      :show-expand="true"
      item-value="id"
      class="mt-2"
      @click:row="toggleExpand"
    >
      <template #[`item.question_count`]="{ item }">
        {{ item.questions?.length ?? item.question_count ?? 0 }}
      </template>

      <template #[`item.layout_id`]="{ item }">
        <v-chip size="x-small" color="primary" variant="outlined">
          {{ item.question_layout_id ?? "—" }}
        </v-chip>
      </template>

      <template #[`item.status`]="{ item }">
        <v-chip :color="statusColor(item.status)" size="small">
          {{ item.status }}
        </v-chip>
      </template>

      <template #[`item.actions`]="{ item }">
        <v-btn
          v-if="item.status !== 'approved'"
          icon="mdi-check"
          size="small"
          variant="text"
          color="success"
          @click.stop="approve(item)"
        />
        <v-btn
          v-if="item.status !== 'archived'"
          icon="mdi-archive"
          size="small"
          variant="text"
          @click.stop="archive(item)"
        />
        <v-btn
          v-if="item.status === 'archived'"
          icon="mdi-restore"
          size="small"
          variant="text"
          color="warning"
          @click.stop="restore(item)"
        />
        <v-btn
          icon="mdi-delete"
          size="small"
          variant="text"
          color="error"
          @click.stop="confirmDelete(item)"
        />
      </template>

      <template #expanded-row="{ item }">
        <td :colspan="headers.length" class="pa-4">
          <v-divider class="mb-2" />
          <div v-for="(q, idx) in item.questions || []" :key="q.id" class="mb-4">
            <v-row dense>
              <v-col cols="auto">
                <v-btn
                  icon="mdi-chevron-up"
                  size="x-small"
                  variant="text"
                  :disabled="idx === 0"
                  @click="moveQuestion(item, idx, -1)"
                />
                <v-btn
                  icon="mdi-chevron-down"
                  size="x-small"
                  variant="text"
                  :disabled="idx === (item.questions?.length || 0) - 1"
                  @click="moveQuestion(item, idx, 1)"
                />
              </v-col>
              <v-col>
                <v-radio-group v-model="q.question_type" inline density="compact" hide-details>
                  <v-radio label="Multiple Choice" value="multiple_choice" />
                  <v-radio label="Open Ended" value="open_ended" />
                </v-radio-group>
                <v-textarea
                  v-model="q.question_text"
                  label="Question"
                  rows="2"
                  density="compact"
                  class="mt-1"
                  hide-details
                  @change="updateQuestion(item, q)"
                />
                <!-- Multiple choice choices -->
                <div v-if="q.question_type === 'multiple_choice'" class="ml-4 mt-1">
                  <div v-for="(ch, ci) in q.choices" :key="ci" class="d-flex align-center ga-1 mb-1">
                    <v-text-field
                      v-model="ch.text"
                      label="Choice text"
                      density="compact"
                      hide-details
                      style="min-width: 200px"
                      @change="updateQuestion(item, q)"
                    />
                    <v-checkbox
                      v-model="ch.is_correct"
                      label="Correct"
                      density="compact"
                      hide-details
                      @change="updateQuestion(item, q)"
                    />
                    <v-btn
                      icon="mdi-close"
                      size="x-small"
                      variant="text"
                      color="error"
                      @click="removeChoice(q, ci)"
                    />
                  </div>
                  <v-btn size="x-small" variant="text" prepend-icon="mdi-plus" @click="addChoice(q)">
                    Choice
                  </v-btn>
                </div>
                <v-text-field
                  v-else
                  v-model="q.expected_answer"
                  label="Expected answer"
                  density="compact"
                  hide-details
                  class="mt-1"
                  @change="updateQuestion(item, q)"
                />
                <v-textarea
                  v-model="q.explanation"
                  label="Explanation"
                  rows="1"
                  density="compact"
                  hide-details
                  class="mt-1"
                  @change="updateQuestion(item, q)"
                />
                <v-btn
                  color="error"
                  size="x-small"
                  variant="text"
                  class="mt-1"
                  @click="confirmDeleteQuestion(item, q)"
                >
                  Delete Question
                </v-btn>
              </v-col>
            </v-row>
            <v-divider v-if="idx < (item.questions?.length || 0) - 1" class="mt-2" />
          </div>
          <v-btn
            color="primary"
            size="small"
            variant="outlined"
            prepend-icon="mdi-plus"
            class="mt-2"
            @click="addQuestion(item)"
          >
            Add Question
          </v-btn>
        </td>
      </template>

      <template #bottom>
        <div class="pa-4 text-center" v-if="quizzes.length === 0 && !loading">
          <v-card flat>
            <v-card-text class="text-grey">No quizzes yet.</v-card-text>
          </v-card>
        </div>
      </template>
    </v-data-table>

    <!-- Create Dialog -->
    <v-dialog v-model="showCreateDialog" max-width="600" persistent>
      <v-card>
        <v-card-title>New Quiz</v-card-title>
        <v-card-text>
          <v-text-field v-model="createForm.title" label="Title" :rules="[r => !!r || 'Title is required']" />
          <v-select
            v-model="createForm.question_layout_id"
            :items="layouts"
            item-title="title"
            item-value="id"
            label="Question Layout"
            :rules="[r => !!r || 'Layout is required']"
          />
          <v-textarea v-model="createForm.intro_voice_template" label="Intro Voice Template" rows="3" />
          <v-combobox
            v-model="createForm.tags"
            label="Tags"
            multiple
            chips
            deletable-chips
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="closeCreateDialog">Cancel</v-btn>
          <v-btn color="primary" :loading="creating" @click="submitCreate">Create</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from "vue";
import { api } from "@/services/api.js";
import { useNotify } from "@/composables/useNotify.js";
import { useConfirm } from "@/composables/useConfirm.js";
import { formatDateTime } from "@/services/timezone.js";

const notify = useNotify();
const confirm = useConfirm();

const quizzes = ref([]);
const layouts = ref([]);
const loading = ref(false);
const creating = ref(false);
const showCreateDialog = ref(false);
const expandedRows = ref(new Set());

const headers = [
  { title: "Title", key: "title", sortable: true },
  { title: "Questions", key: "question_count", sortable: false, width: 90 },
  { title: "Layout", key: "layout_id", sortable: true },
  { title: "Status", key: "status", sortable: true, width: 100 },
  { title: "Version", key: "version", sortable: true, width: 80 },
  { title: "Approved By", key: "approved_by", sortable: false },
  { title: "Actions", key: "actions", sortable: false, width: 150 },
];

const statusOptions = ["draft", "approved", "archived"];

const filters = reactive({
  status: null,
  tags: [],
});

const createForm = reactive({
  title: "",
  question_layout_id: null,
  intro_voice_template: "",
  tags: [],
});

function statusColor(status) {
  const map = {
    draft: "blue",
    approved: "green",
    archived: "grey",
  };
  return map[status] || "default";
}

async function fetchQuizzes() {
  loading.value = true;
  try {
    const params = {};
    if (filters.status) params.status = filters.status;
    if (filters.tags && filters.tags.length > 0) params.tags = filters.tags.join(",");
    const res = await api.getQuizzes(params);
    quizzes.value = res.data ?? res ?? [];
  } catch (err) {
    notify.error("Failed to load quizzes: " + (err.message || err));
  } finally {
    loading.value = false;
  }
}

async function fetchLayouts() {
  try {
    const res = await api.getKnowledgeLayouts("quiz_question");
    layouts.value = res.data ?? res ?? [];
  } catch (err) {
    notify.error("Failed to load layouts: " + (err.message || err));
  }
}

function toggleExpand(event, { item }) {
  if (expandedRows.value.has(item.id)) {
    expandedRows.value.delete(item.id);
  } else {
    expandedRows.value.add(item.id);
  }
  // Force reactivity
  expandedRows.value = new Set(expandedRows.value);
}

async function submitCreate() {
  if (!createForm.title || !createForm.question_layout_id) {
    notify.warning("Title and Layout are required.");
    return;
  }
  creating.value = true;
  try {
    await api.createQuiz({
      title: createForm.title,
      question_layout_id: createForm.question_layout_id,
      intro_voice_template: createForm.intro_voice_template,
      tags: createForm.tags,
    });
    notify.success("Quiz created.");
    closeCreateDialog();
    await fetchQuizzes();
  } catch (err) {
    notify.error("Failed to create quiz: " + (err.message || err));
  } finally {
    creating.value = false;
  }
}

function closeCreateDialog() {
  showCreateDialog.value = false;
  createForm.title = "";
  createForm.question_layout_id = null;
  createForm.intro_voice_template = "";
  createForm.tags = [];
}

async function addQuestion(quiz) {
  try {
    await api.createQuizQuestion(quiz.id, {
      question_text: "",
      question_type: "multiple_choice",
      choices: [],
      expected_answer: "",
      explanation: "",
    });
    notify.success("Question added.");
    await fetchQuizzes();
  } catch (err) {
    notify.error("Failed to add question: " + (err.message || err));
  }
}

async function updateQuestion(quiz, question) {
  try {
    await api.updateQuizQuestion(question.id, {
      question_text: question.question_text,
      question_type: question.question_type,
      choices: question.choices,
      expected_answer: question.expected_answer,
      explanation: question.explanation,
    });
  } catch (err) {
    notify.error("Failed to update question: " + (err.message || err));
  }
}

async function confirmDeleteQuestion(quiz, question) {
  const ok = await confirm.require("Delete this question?");
  if (!ok) return;
  try {
    await api.deleteQuizQuestion(question.id);
    notify.success("Question deleted.");
    await fetchQuizzes();
  } catch (err) {
    notify.error("Failed to delete question: " + (err.message || err));
  }
}

async function moveQuestion(quiz, question, direction) {
  try {
    await api.reorderQuizQuestions(quiz.id, {
      question_id: question.id,
      direction,
    });
    await fetchQuizzes();
  } catch (err) {
    notify.error("Failed to reorder: " + (err.message || err));
  }
}

function addChoice(question) {
  if (!question.choices) question.choices = [];
  question.choices.push({ id: null, text: "", is_correct: false });
}

function removeChoice(question, index) {
  if (question.choices) {
    question.choices.splice(index, 1);
  }
}

async function approve(item) {
  try {
    await api.approveQuiz(item.id);
    notify.success("Quiz approved.");
    await fetchQuizzes();
  } catch (err) {
    notify.error("Failed to approve: " + (err.message || err));
  }
}

async function archive(item) {
  try {
    await api.archiveQuiz(item.id);
    notify.success("Quiz archived.");
    await fetchQuizzes();
  } catch (err) {
    notify.error("Failed to archive: " + (err.message || err));
  }
}

async function restore(item) {
  try {
    await api.restoreQuiz(item.id);
    notify.success("Quiz restored.");
    await fetchQuizzes();
  } catch (err) {
    notify.error("Failed to restore: " + (err.message || err));
  }
}

async function confirmDelete(item) {
  const archiveFirst = await confirm.require(
    "Archive this item instead?",
    { confirmText: "Archive", cancelText: "Delete permanently" }
  );
  if (archiveFirst) {
    await archive(item);
    return;
  }
  const reallyDelete = await confirm.require(
    "Delete permanently? This cannot be undone.",
    { confirmText: "Delete", color: "error" }
  );
  if (!reallyDelete) return;
  try {
    await api.deleteQuiz(item.id);
    notify.success("Quiz deleted.");
    await fetchQuizzes();
  } catch (err) {
    notify.error("Failed to delete: " + (err.message || err));
  }
}

onMounted(() => {
  fetchQuizzes();
  fetchLayouts();
});
</script>
