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
        v-model="filters.status"
        :items="statusOptions"
        label="Status"
        variant="outlined"
        density="compact"
        hide-details
        clearable
        style="max-width: 160px"
        @update:model-value="page = 1; fetchQuizzes()"
      />
      <v-combobox
        v-model="filters.tags"
        label="Tags"
        variant="outlined"
        multiple
        density="compact"
        hide-details
        clearable
        style="max-width: 200px"
        @update:model-value="page = 1; fetchQuizzes()"
      />
      <v-btn color="primary" variant="flat" prepend-icon="mdi-plus" @click="showCreateDialog = true">
        New Quiz
      </v-btn>
    </div>

    <v-card class="glass-card">
      <v-data-table
        :headers="headers"
        :items="quizzes"
        :loading="loading"
        :items-length="totalItems"
        :items-per-page="itemsPerPage"
        :page="page"
        @update:options="onPageOptions"
        :show-expand="true"
        item-value="id"
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
          icon="mdi-pencil"
          size="small"
          variant="text"
          color="primary"
          @click.stop="editQuiz(item)"
        />
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
          <div v-for="(q, idx) in (expandedQuizzes[item.id]?.questions || [])" :key="q.id" class="mb-4">
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
                  :disabled="idx === (expandedQuizzes[item.id]?.questions?.length || 0) - 1"
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

      </v-data-table>
    </v-card>

    <!-- Create Dialog -->
    <v-dialog v-model="showCreateDialog" max-width="800" persistent>
      <v-card>
        <DialogHeader
          icon="mdi-help-box-outline"
          label="Create New"
          title="Quiz"
          @close="closeCreateDialog"
        >
          <template #actions>
            <v-btn
              v-if="createForm.questions.length > 0"
              size="small"
              variant="tonal"
              prepend-icon="mdi-plus"
              class="mr-2"
              @click="addCreateQuestion"
            >
              Add Question
            </v-btn>
          </template>
        </DialogHeader>
        <v-card-text>
          <!-- LLM Generation Section -->
          <v-card variant="tonal" class="mb-4 pa-3">
            <div class="text-subtitle-2 mb-2">Generate from Knowledge Document</div>
            <v-row dense>
              <v-col cols="12">
                <LlmModelPicker
                  v-model="generateModelId"
                  :model-items="llmModelItems"
                  label="LLM Model"
                  hint="Model used for quiz generation"
                  persistent-hint
                  clearable
                />
              </v-col>
              <v-col cols="12" sm="5">
                <v-select
                  v-model="createForm.document_id"
                  :items="documentOptions"
                  item-title="title"
                  item-value="id"
                  label="Knowledge Document"
                  hint="Source document for generation"
                  clearable
                />
              </v-col>
              <v-col cols="6" sm="2">
                <v-text-field
                  v-model="generateNumQuestions"
                  label="Questions"
                  type="number"
                  :min="1"
                  :max="20"
                  hide-details
                />
              </v-col>
              <v-col cols="6" sm="2">
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
              <v-col cols="12" sm="3" class="d-flex align-end">
                <v-btn
                  color="secondary"
                  variant="tonal"
                  :loading="generating"
                  :disabled="!createForm.document_id"
                  block
                  @click="generateQuiz"
                >
                  Generate
                </v-btn>
              </v-col>
            </v-row>
          </v-card>

          <!-- Quiz Metadata -->
          <v-text-field v-model="createForm.title" label="Title" :rules="[r => !!r || 'Title is required']" class="mb-3" />
          <v-select
            v-model="createForm.question_layout_id"
            :items="layouts"
            item-title="display_name"
            item-value="id"
            label="Question Layout"
            :rules="[r => !!r || 'Layout is required']"
            class="mb-3"
          />
          <v-textarea v-model="createForm.intro_voice_template" label="Intro Voice Template" rows="2" class="mb-3" />
          <v-combobox
            v-model="createForm.tags"
            label="Tags"
            multiple
            chips
            deletable-chips
            class="mb-4"
          />

          <!-- Questions Preview / Editor -->
          <v-divider v-if="createForm.questions.length > 0" class="mb-3" />
          <div v-if="createForm.questions.length > 0">
            <div class="d-flex align-center mb-2">
              <v-icon size="small" class="mr-1">mdi-help-circle-outline</v-icon>
              <span class="text-subtitle-2">Questions ({{ createForm.questions.length }})</span>
            </div>
            <v-card
              v-for="(q, idx) in createForm.questions"
              :key="idx"
              variant="tonal"
              class="mb-3 pa-3"
            >
              <div class="d-flex align-center mb-2">
                <v-chip size="x-small" color="primary" variant="tonal" class="mr-2">
                  {{ idx + 1 }}
                </v-chip>
                <v-radio-group v-model="q.question_type" inline density="compact" hide-details>
                  <v-radio label="Multiple Choice" value="multiple_choice" />
                  <v-radio label="Open Ended" value="open_ended" />
                </v-radio-group>
                <v-spacer />
                <v-btn
                  icon="mdi-close"
                  size="x-small"
                  variant="text"
                  color="error"
                  @click="removeCreateQuestion(idx)"
                />
              </div>
              <v-textarea
                v-model="q.question_text"
                label="Question"
                rows="2"
                density="compact"
                hide-details
                class="mb-2"
              />
              <!-- Multiple choice choices -->
              <div v-if="q.question_type === 'multiple_choice'" class="ml-2 mb-2">
                <div v-for="(ch, ci) in q.choices" :key="ci" class="d-flex align-center ga-1 mb-1">
                  <v-text-field
                    v-model="ch.text"
                    label="Choice text"
                    density="compact"
                    hide-details
                    style="min-width: 200px"
                  />
                  <v-checkbox
                    v-model="ch.is_correct"
                    label="Correct"
                    density="compact"
                    hide-details
                  />
                  <v-btn
                    icon="mdi-close"
                    size="x-small"
                    variant="text"
                    color="error"
                    @click="removeCreateChoice(q, ci)"
                  />
                </div>
                <v-btn size="x-small" variant="text" prepend-icon="mdi-plus" @click="addCreateChoice(q)">
                  Choice
                </v-btn>
              </div>
              <template v-else>
                <v-text-field
                  v-model="q.expected_answer"
                  label="Expected answer"
                  density="compact"
                  hide-details
                  class="mb-2"
                />
              </template>
              <v-textarea
                v-model="q.explanation"
                label="Explanation"
                rows="1"
                density="compact"
                hide-details
              />
            </v-card>
          </div>
        </v-card-text>
        <DialogFooter
          hint="Generate questions from a knowledge document, or add them manually."
          confirm-label="Create Quiz"
          :confirm-loading="creating"
          @cancel="closeCreateDialog"
          @confirm="submitCreate"
        />
      </v-card>
    </v-dialog>

    <!-- Edit Dialog -->
    <v-dialog v-model="showEditDialog" max-width="800" persistent>
      <v-card>
        <DialogHeader
          icon="mdi-help-box-outline"
          label="Edit"
          title="Quiz"
          @close="showEditDialog = false"
        >
          <template #actions>
            <v-btn
              size="small"
              variant="tonal"
              prepend-icon="mdi-plus"
              class="mr-2"
              @click="addEditQuestion"
            >
              Add Question
            </v-btn>
          </template>
        </DialogHeader>
        <v-card-text>
          <!-- LLM Regeneration -->
          <v-card variant="tonal" class="mb-4 pa-3">
            <div class="text-subtitle-2 mb-2">LLM Regeneration</div>
            <LlmModelPicker
              v-model="editLlmModelId"
              :model-items="llmModelItems"
              label="LLM Model"
              hint="Model used when regenerating individual questions"
              persistent-hint
              clearable
            />
          </v-card>

          <v-text-field v-model="editForm.title" label="Title" class="mb-3" />
          <v-select
            v-model="editForm.question_layout_id"
            :items="layouts"
            item-title="display_name"
            item-value="id"
            label="Question Layout"
            class="mb-3"
          />
          <v-textarea v-model="editForm.intro_voice_template" label="Intro Voice Template" rows="2" class="mb-3" />
          <v-combobox
            v-model="editForm.tags"
            label="Tags"
            multiple
            chips
            deletable-chips
            class="mb-4"
          />

          <v-divider v-if="editForm.questions.length > 0" class="mb-3" />
          <div v-if="editForm.questions.length > 0">
            <div class="d-flex align-center mb-2">
              <v-icon size="small" class="mr-1">mdi-help-circle-outline</v-icon>
              <span class="text-subtitle-2">Questions ({{ editForm.questions.length }})</span>
            </div>
            <v-card
              v-for="(q, idx) in editForm.questions"
              :key="idx"
              variant="tonal"
              class="mb-3 pa-3"
            >
              <div class="d-flex align-center mb-2">
                <v-chip size="x-small" color="primary" variant="tonal" class="mr-2">
                  {{ idx + 1 }}
                </v-chip>
                <v-radio-group v-model="q.question_type" inline density="compact" hide-details>
                  <v-radio label="Multiple Choice" value="multiple_choice" />
                  <v-radio label="Open Ended" value="open_ended" />
                </v-radio-group>
                <v-spacer />
                <v-btn
                  icon="mdi-refresh"
                  size="x-small"
                  variant="text"
                  color="secondary"
                  :disabled="!editLlmModelId"
                  class="mr-1"
                  @click="regenerateEditQuestion(idx)"
                />
                <v-btn
                  icon="mdi-close"
                  size="x-small"
                  variant="text"
                  color="error"
                  @click="removeEditQuestion(idx)"
                />
              </div>
              <v-textarea
                v-model="q.question_text"
                label="Question"
                rows="2"
                density="compact"
                hide-details
                class="mb-2"
              />
              <div v-if="q.question_type === 'multiple_choice'" class="ml-2 mb-2">
                <div v-for="(ch, ci) in q.choices" :key="ci" class="d-flex align-center ga-1 mb-1">
                  <v-text-field
                    v-model="ch.text"
                    label="Choice text"
                    density="compact"
                    hide-details
                    style="min-width: 200px"
                  />
                  <v-checkbox
                    v-model="ch.is_correct"
                    label="Correct"
                    density="compact"
                    hide-details
                  />
                  <v-btn
                    icon="mdi-close"
                    size="x-small"
                    variant="text"
                    color="error"
                    @click="removeEditChoice(q, ci)"
                  />
                </div>
                <v-btn size="x-small" variant="text" prepend-icon="mdi-plus" @click="addEditChoice(q)">
                  Choice
                </v-btn>
              </div>
              <template v-else>
                <v-text-field
                  v-model="q.expected_answer"
                  label="Expected answer"
                  density="compact"
                  hide-details
                  class="mb-2"
                />
              </template>
              <v-textarea
                v-model="q.explanation"
                label="Explanation"
                rows="1"
                density="compact"
                hide-details
              />
            </v-card>
          </div>
        </v-card-text>
        <DialogFooter
          hint="Modify quiz metadata and edit individual questions."
          :confirm-loading="saving"
          @cancel="showEditDialog = false"
          @confirm="submitEdit"
        />
      </v-card>
    </v-dialog>

    <!-- Confirm Dialog -->
    <v-dialog v-model="confirmDialog" max-width="400">
      <v-card rounded="xl">
        <v-card-title v-if="confirmTitle">{{ confirmTitle }}</v-card-title>
        <v-card-text>{{ confirmText }}</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="onCancel">{{ cancelLabel }}</v-btn>
          <v-btn :color="confirmColor" @click="onConfirm">{{ confirmLabel }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete Confirm Dialog -->
    <v-dialog v-model="deleteDialog" max-width="400">
      <v-card rounded="xl">
        <v-card-text class="pt-4">Archive this item instead?</v-card-text>
        <v-card-actions>
          <v-btn variant="text" @click="deleteDialog = false">Cancel</v-btn>
          <v-spacer />
          <v-btn color="warning" @click="doArchive">Archive</v-btn>
          <v-btn color="error" @click="doDelete">Delete</v-btn>
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
import LlmModelPicker from "@/components/common/LlmModelPicker.vue";
import DialogHeader from "@/components/common/DialogHeader.vue";
import DialogFooter from "@/components/common/DialogFooter.vue";

const { notify } = useNotify();
const { confirmDialog, confirmTitle, confirmText, confirmLabel, cancelLabel, confirmColor, require: confirmRequire, onConfirm, onCancel } = useConfirm();

const quizzes = ref([]);
const layouts = ref([]);
const documentOptions = ref([]);
const llmModelItems = ref([]);
const loading = ref(false);
const totalItems = ref(0);
const itemsPerPage = ref(20);
const page = ref(1);
const creating = ref(false);
const generating = ref(false);
const generateModelId = ref("");
const generateNumQuestions = ref(5);
const generateMix = ref("mixed");
const showCreateDialog = ref(false);
const showEditDialog = ref(false);
const deleteDialog = ref(false);
const expandedRows = ref(new Set());
const expandedQuizzes = ref({});
const saving = ref(false);
const editingQuizId = ref(null);
const editLlmModelId = ref("");

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

const filters = reactive({
  status: null,
  tags: [],
});

const createForm = reactive({
  title: "",
  question_layout_id: null,
  intro_voice_template: "",
  tags: [],
  document_id: null,
  questions: [],
});

const editForm = reactive({
  title: "",
  question_layout_id: null,
  intro_voice_template: "",
  tags: [],
  questions: [],
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
    const params = { limit: itemsPerPage.value, offset: (page.value - 1) * itemsPerPage.value };
    if (filters.status) params.status = filters.status;
    if (filters.tags && filters.tags.length > 0) params.tags = filters.tags.join(",");
    const res = await api.getQuizzes(params);
    quizzes.value = res.items ?? [];
    totalItems.value = res.total ?? 0;
  } catch (err) {
    notify.error("Failed to load quizzes: " + (err.message || err));
  } finally {
    loading.value = false;
  }
}

function onPageOptions({ page: newPage, itemsPerPage: newPerPage }) {
  if (newPerPage !== itemsPerPage.value) {
    itemsPerPage.value = newPerPage;
    page.value = 1;
  } else {
    page.value = newPage;
  }
  expandedRows.value = new Set();
  expandedQuizzes.value = {};
  fetchQuizzes();
}

async function fetchLayouts() {
  try {
    const res = await api.getKnowledgeLayouts("quiz_question");
    layouts.value = res.layouts ?? [];
  } catch (err) {
    notify.error("Failed to load layouts: " + (err.message || err));
  }
}

async function fetchDocuments() {
  try {
    const res = await api.getKnowledgeDocuments({ per_page: 200 });
    documentOptions.value = res.items ?? [];
  } catch (_) {
    // non-critical
  }
}

async function fetchLLMModels() {
  try {
    llmModelItems.value = await api.getLLMModels();
  } catch (_) {
    // non-critical
  }
}

async function generateQuiz() {
  if (!createForm.document_id) {
    notify.warning("Select a knowledge document first.");
    return;
  }
  generating.value = true;
  try {
    const suggestion = await api.suggestQuiz(
      createForm.document_id,
      generateNumQuestions.value,
      generateMix.value,
      generateModelId.value || undefined,
    );
    if (suggestion.title) createForm.title = suggestion.title;
    if (suggestion.intro_voice_template) createForm.intro_voice_template = suggestion.intro_voice_template;
    if (suggestion.questions && suggestion.questions.length > 0) {
      createForm.questions = suggestion.questions.map((q) => ({
        id: null,
        question_type: q.question_type || "multiple_choice",
        question_text: q.question_text || "",
        choices: q.choices || [],
        expected_answer: q.expected_answer || "",
        explanation: q.explanation || "",
      }));
    }
    notify.success(`Generated ${suggestion.questions?.length || 0} questions.`);
  } catch (err) {
    notify.error("Failed to generate quiz: " + (err.message || err));
  } finally {
    generating.value = false;
  }
}

function addCreateQuestion() {
  createForm.questions.push({
    id: null,
    question_type: "multiple_choice",
    question_text: "",
    choices: [],
    expected_answer: "",
    explanation: "",
  });
}

function removeCreateQuestion(idx) {
  createForm.questions.splice(idx, 1);
}

function addCreateChoice(q) {
  if (!q.choices) q.choices = [];
  q.choices.push({ id: null, text: "", is_correct: false });
}

function removeCreateChoice(q, ci) {
  if (q.choices) q.choices.splice(ci, 1);
}

// -- Edit dialog helpers --------------------------------------------------

async function editQuiz(item) {
  try {
    const quiz = await api.getQuiz(item.id);
    editingQuizId.value = quiz.id;
    editForm.title = quiz.title || "";
    editForm.question_layout_id = quiz.question_layout_id || null;
    editForm.intro_voice_template = quiz.intro_voice_template || "";
    editForm.tags = quiz.tags || [];
    editForm.questions = (quiz.questions || []).map((q) => ({
      id: q.id,
      question_type: q.question_type || "multiple_choice",
      question_text: q.question_text || "",
      choices: q.choices || [],
      expected_answer: q.expected_answer || "",
      explanation: q.explanation || "",
    }));
    editLlmModelId.value = "";
    showEditDialog.value = true;
  } catch (err) {
    notify.error("Failed to load quiz: " + (err.message || err));
  }
}

async function submitEdit() {
  if (!editingQuizId.value) return;
  saving.value = true;
  try {
    await api.updateQuiz(editingQuizId.value, {
      title: editForm.title,
      question_layout_id: editForm.question_layout_id,
      intro_voice_template: editForm.intro_voice_template,
      tags: editForm.tags,
    });
    // Sync questions: update existing, create new, delete removed
    const currentIds = new Set(editForm.questions.filter((q) => q.id).map((q) => q.id));
    const originalQuiz = await api.getQuiz(editingQuizId.value);
    for (const origQ of originalQuiz.questions || []) {
      if (!currentIds.has(origQ.id)) {
        await api.deleteQuizQuestion(editingQuizId.value, origQ.id);
      }
    }
    for (const q of editForm.questions) {
      if (q.id) {
        await api.updateQuizQuestion(editingQuizId.value, q.id, {
          question_text: q.question_text,
          question_type: q.question_type,
          choices: q.choices || [],
          expected_answer: q.expected_answer || "",
          explanation: q.explanation || "",
        });
      } else {
        await api.createQuizQuestion(editingQuizId.value, {
          question_text: q.question_text,
          question_type: q.question_type,
          choices: q.choices || [],
          expected_answer: q.expected_answer || "",
          explanation: q.explanation || "",
        });
      }
    }
    notify.success("Quiz updated.");
    showEditDialog.value = false;
    editingQuizId.value = null;
    await fetchQuizzes();
  } catch (err) {
    notify.error("Failed to update quiz: " + (err.message || err));
  } finally {
    saving.value = false;
  }
}

function addEditQuestion() {
  editForm.questions.push({
    id: null,
    question_type: "multiple_choice",
    question_text: "",
    choices: [],
    expected_answer: "",
    explanation: "",
  });
}

function removeEditQuestion(idx) {
  editForm.questions.splice(idx, 1);
}

function addEditChoice(q) {
  if (!q.choices) q.choices = [];
  q.choices.push({ id: null, text: "", is_correct: false });
}

function removeEditChoice(q, ci) {
  if (q.choices) q.choices.splice(ci, 1);
}

async function regenerateEditQuestion(idx) {
  const q = editForm.questions[idx];
  if (!q) return;
  if (!q.id) {
    notify.warning("Save the quiz first, then regenerate this question.");
    return;
  }
  const quiz = await api.getQuiz(editingQuizId.value);
  if (!quiz.document_id) {
    notify.warning("Quiz has no linked document for regeneration.");
    return;
  }
  try {
    const suggestion = await api.regenerateQuizQuestion(
      editingQuizId.value,
      q.id,
      editLlmModelId.value || undefined,
    );
    if (suggestion.question_text) q.question_text = suggestion.question_text;
    if (suggestion.choices) q.choices = suggestion.choices;
    if (suggestion.expected_answer) q.expected_answer = suggestion.expected_answer;
    if (suggestion.explanation) q.explanation = suggestion.explanation;
    notify.success("Question regenerated.");
  } catch (err) {
    notify.error("Failed to regenerate: " + (err.message || err));
  }
}

async function toggleExpand(event, { item }) {
  if (expandedRows.value.has(item.id)) {
    expandedRows.value.delete(item.id);
    delete expandedQuizzes.value[item.id];
  } else {
    expandedRows.value.add(item.id);
    try {
      expandedQuizzes.value[item.id] = await api.getQuiz(item.id);
    } catch (_) {
      expandedQuizzes.value[item.id] = null;
    }
  }
  // Force reactivity
  expandedRows.value = new Set(expandedRows.value);
  expandedQuizzes.value = { ...expandedQuizzes.value };
}

async function submitCreate() {
  if (!createForm.title || !createForm.question_layout_id) {
    notify.warning("Title and Layout are required.");
    return;
  }
  creating.value = true;
  try {
    const quiz = await api.createQuiz({
      title: createForm.title,
      question_layout_id: createForm.question_layout_id,
      intro_voice_template: createForm.intro_voice_template,
      tags: createForm.tags,
      document_id: createForm.document_id || undefined,
    });
    // Create questions
    for (const q of createForm.questions) {
      await api.createQuizQuestion(quiz.id, {
        question_text: q.question_text,
        question_type: q.question_type,
        choices: q.choices || [],
        expected_answer: q.expected_answer || "",
        explanation: q.explanation || "",
      });
    }
    notify.success(`Quiz created with ${createForm.questions.length} question(s).`);
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
  createForm.document_id = null;
  createForm.questions = [];
  generateModelId.value = "";
  generateNumQuestions.value = 5;
  generateMix.value = "mixed";
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
    await api.updateQuizQuestion(quiz.id, question.id, {
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
  const ok = await confirmRequire("Delete this question?");
  if (!ok) return;
  try {
    await api.deleteQuizQuestion(quiz.id, question.id);
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

const deleteTarget = ref(null);

function confirmDelete(item) {
  deleteTarget.value = item;
  deleteDialog.value = true;
}

async function doArchive() {
  deleteDialog.value = false;
  if (deleteTarget.value) await archive(deleteTarget.value);
  deleteTarget.value = null;
}

async function doDelete() {
  deleteDialog.value = false;
  const item = deleteTarget.value;
  deleteTarget.value = null;
  if (!item) return;
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
  fetchDocuments();
  fetchLLMModels();
});
</script>

