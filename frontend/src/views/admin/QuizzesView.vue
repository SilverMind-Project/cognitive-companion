<template>
  <div>
    <div class="d-flex align-center flex-wrap ga-3 mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Quizzes</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Manage quizzes for senior cognitive assessment and engagement.
        </div>
      </div>
      <v-spacer />
      <v-select
        v-model="state.filters.status"
        :items="statusOptions"
        label="Status"
        variant="outlined"
        density="compact"
        hide-details
        clearable
        style="max-width: 160px"
        @update:model-value="actions.onFilterChange()"
      />
      <v-combobox
        v-model="state.filters.tags"
        label="Tags"
        variant="outlined"
        multiple
        density="compact"
        hide-details
        clearable
        style="max-width: 200px"
        @update:model-value="actions.onFilterChange()"
      />
      <v-btn
        color="secondary"
        variant="tonal"
        prepend-icon="mdi-auto-fix"
        @click="showSuggestDialog = true"
      >
        Generate with AI
      </v-btn>
      <v-btn color="primary" variant="flat" prepend-icon="mdi-plus" @click="openCreateDialog">
        New Quiz
      </v-btn>
    </div>

    <v-card class="glass-card">
      <v-data-table
        :headers="headers"
        :items="state.quizzes"
        :loading="state.loading"
        :items-length="state.totalQuizzes"
        :items-per-page="state.itemsPerPage"
        :page="state.page"
        :show-expand="true"
        item-value="id"
        @update:options="actions.onPageOptions"
        @click:row="actions.toggleExpand"
      >
        <template #[`item.question_count`]="{ item }">
          {{ item.questions?.length ?? item.question_count ?? 0 }}
        </template>

        <template #[`item.layout_id`]="{ item }">
          <v-chip size="x-small" color="primary" variant="outlined">
            {{ item.question_layout_id ?? "-" }}
          </v-chip>
        </template>

        <template #[`item.status`]="{ item }">
          <v-chip :color="statusColor(item.status)" size="small">
            {{ item.status }}
          </v-chip>
        </template>

        <template #[`item.actions`]="{ item }">
          <v-btn
            icon="mdi-pencil"
            size="small"
            variant="text"
            color="primary"
            @click.stop="openEditDialog(item)"
          />
          <v-btn
            v-if="item.status !== 'approved'"
            icon="mdi-check"
            size="small"
            variant="text"
            color="success"
            @click.stop="actions.approveQuiz(item)"
          />
          <v-btn
            v-if="item.status !== 'archived'"
            icon="mdi-archive"
            size="small"
            variant="text"
            @click.stop="actions.archiveQuiz(item)"
          />
          <v-btn
            v-if="item.status === 'archived'"
            icon="mdi-restore"
            size="small"
            variant="text"
            color="warning"
            @click.stop="actions.restoreQuiz(item)"
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
            <QuizQuestionEditorCard
              v-for="(q, idx) in state.expandedQuizzes[item.id]?.questions || []"
              :key="q.id"
              :question="q"
              :index="idx"
              :total="(state.expandedQuizzes[item.id]?.questions || []).length"
              :show-reorder="true"
              card-variant="flat"
              card-class="mb-4 pa-2"
              @change="(updated) => actions.saveQuestion(item, updated)"
              @move="(dir) => actions.moveQuestion(item, idx, dir)"
              @delete="confirmDeleteQuestion(item, q)"
            />
            <v-btn
              color="primary"
              size="small"
              variant="outlined"
              prepend-icon="mdi-plus"
              class="mt-2"
              @click="actions.addQuestion(item)"
            >
              Add Question
            </v-btn>
          </td>
        </template>

        <template #no-data>
          <div class="pa-6 text-center">
            <v-card flat>
              <v-card-text class="text-medium-emphasis text-h6">No quizzes yet</v-card-text>
              <v-card-text class="text-medium-emphasis">
                Create a quiz manually or generate one from a knowledge document.
              </v-card-text>
            </v-card>
          </div>
        </template>
      </v-data-table>
    </v-card>

    <QuizFormDialog
      ref="formDialogRef"
      v-model="showFormDialog"
      :mode="formMode"
      :quiz="editingQuiz"
      :layouts="state.layouts"
      :document-options="state.documents"
      :llm-model-items="state.llmModelItems"
      @saved="actions.fetchQuizzes()"
      @regenerate-question="onRegenerateInDialog"
    />

    <QuizSuggestDialog
      v-model="showSuggestDialog"
      :document-options="state.documents"
      :llm-model-items="state.llmModelItems"
      @suggested="onSuggestedQuiz"
    />

    <v-dialog v-model="confirmDialog" max-width="400" persistent>
      <v-card rounded="xl">
        <v-card-title v-if="confirmTitle">{{ confirmTitle }}</v-card-title>
        <v-card-text>{{ confirmText }}</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="onCancel">{{ cancelLabel }}</v-btn>
          <v-btn :color="confirmColor" variant="flat" @click="onConfirm">{{ confirmLabel }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <ArchiveOrDeleteDialog
      v-model="deleteDialog"
      noun="quiz"
      :name="deleteTarget?.title || ''"
      @archive="doArchive"
      @delete="doDelete"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { getQuiz } from "@/services/modules/quizzes";
import { useNotify } from "@/composables/useNotify.js";
import { useConfirm } from "@/composables/useConfirm.js";
import { useQuizzesAdmin } from "@/composables/useQuizzesAdmin.js";
import ArchiveOrDeleteDialog from "@/components/common/ArchiveOrDeleteDialog.vue";
import QuizQuestionEditorCard from "@/components/knowledge/QuizQuestionEditorCard.vue";
import QuizFormDialog from "@/components/knowledge/QuizFormDialog.vue";
import QuizSuggestDialog from "@/components/knowledge/QuizSuggestDialog.vue";

const { notify } = useNotify();
const {
  confirmDialog,
  confirmTitle,
  confirmText,
  confirmLabel,
  cancelLabel,
  confirmColor,
  require: confirmRequire,
  onConfirm,
  onCancel,
} = useConfirm();

const { state, actions } = useQuizzesAdmin({ notify });

const showFormDialog = ref(false);
const showSuggestDialog = ref(false);
const formMode = ref("create");
const editingQuiz = ref(null);
const formDialogRef = ref(null);
const deleteDialog = ref(false);
const deleteTarget = ref(null);

const headers = [
  { title: "Title", key: "title", sortable: true },
  { title: "Questions", key: "question_count", sortable: false, width: 90 },
  { title: "Layout", key: "layout_id", sortable: true },
  { title: "Status", key: "status", sortable: true, width: 100 },
  { title: "Version", key: "version", sortable: true, width: 80 },
  { title: "Approved By", key: "approved_by", sortable: false },
  { title: "Actions", key: "actions", sortable: false, width: 200 },
];

const statusOptions = ["draft", "approved", "archived"];

function statusColor(status) {
  const map = {
    draft: "info",
    approved: "success",
    archived: "secondary",
  };
  return map[status] || "default";
}

function openCreateDialog() {
  formMode.value = "create";
  editingQuiz.value = null;
  showFormDialog.value = true;
}

async function openEditDialog(item) {
  try {
    const detail = await getQuiz(item.id);
    formMode.value = "edit";
    editingQuiz.value = detail;
    showFormDialog.value = true;
  } catch (err) {
    notify.error("Failed to load quiz: " + (err.message || err));
  }
}

function onSuggestedQuiz(payload) {
  formMode.value = "create";
  editingQuiz.value = null;
  showFormDialog.value = true;
  formDialogRef.value?.applySuggestion(payload);
}

async function onRegenerateInDialog({ question, modelId }) {
  if (!editingQuiz.value?.id) return;
  await actions.regenerateQuestion(editingQuiz.value.id, question, modelId);
}

async function confirmDeleteQuestion(quiz, question) {
  const ok = await confirmRequire("Delete this question?");
  if (!ok) return;
  await actions.deleteQuestion(quiz, question);
}

function confirmDelete(item) {
  deleteTarget.value = item;
  deleteDialog.value = true;
}

async function doArchive() {
  deleteDialog.value = false;
  if (deleteTarget.value) await actions.archiveQuiz(deleteTarget.value);
  deleteTarget.value = null;
}

async function doDelete() {
  deleteDialog.value = false;
  const item = deleteTarget.value;
  deleteTarget.value = null;
  if (!item) return;
  await actions.deleteQuiz(item);
}

onMounted(() => {
  actions.fetchQuizzes();
  actions.fetchLayouts();
  actions.fetchDocuments();
  actions.fetchLLMModels();
});
</script>
