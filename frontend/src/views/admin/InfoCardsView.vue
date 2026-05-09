<template>
  <div>
    <div class="d-flex align-center flex-wrap ga-3 mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Info Cards</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Manage info cards for scheduled delivery to seniors.
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
        @update:model-value="page = 1; fetchCards()"
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
        @update:model-value="page = 1; fetchCards()"
      />
      <v-text-field
        v-model="filters.document_id"
        label="Document ID"
        variant="outlined"
        density="compact"
        hide-details
        clearable
        style="max-width: 180px"
        @update:model-value="debouncedFetch"
      />
      <v-btn color="primary" variant="flat" prepend-icon="mdi-plus" @click="showCreateDialog = true">
        New Info Card
      </v-btn>
    </div>

    <v-card class="glass-card">
      <v-data-table
        :headers="headers"
        :items="cards"
        :loading="loading"
        :items-length="totalItems"
        :items-per-page="itemsPerPage"
        :page="page"
        @update:options="onPageOptions"
      >
      <template #[`item.layout_id`]="{ item }">
        <v-chip size="x-small" color="primary" variant="outlined">
          {{ item.layout_id ?? "—" }}
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
          @click="editCard(item)"
        />
        <v-btn
          v-if="item.status !== 'approved'"
          icon="mdi-check"
          size="small"
          variant="text"
          color="success"
          @click="approve(item)"
        />
        <v-btn
          v-if="item.status !== 'archived'"
          icon="mdi-archive"
          size="small"
          variant="text"
          @click="archive(item)"
        />
        <v-btn
          v-if="item.status === 'archived'"
          icon="mdi-restore"
          size="small"
          variant="text"
          color="warning"
          @click="restore(item)"
        />
        <v-btn
          icon="mdi-delete"
          size="small"
          variant="text"
          color="error"
          @click="confirmDelete(item)"
        />
      </template>

      </v-data-table>
    </v-card>

    <!-- Create Dialog -->
    <v-dialog v-model="showCreateDialog" max-width="640" persistent>
      <v-card>
        <v-card-title>New Info Card</v-card-title>
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
                  hint="Model used when generating from a document"
                  persistent-hint
                  clearable
                />
              </v-col>
              <v-col cols="12" sm="8">
                <v-select
                  v-model="createForm.document_id"
                  :items="documentOptions"
                  item-title="title"
                  item-value="id"
                  label="Knowledge Document"
                  hint="Source document for content generation"
                  persistent-hint
                  clearable
                />
              </v-col>
              <v-col cols="12" sm="4" class="d-flex align-center">
                <v-btn
                  color="secondary"
                  variant="tonal"
                  :loading="generating"
                  :disabled="!createForm.document_id"
                  block
                  class="mt-2"
                  @click="generateFromDocument"
                >
                  Generate
                </v-btn>
              </v-col>
            </v-row>
          </v-card>

          <v-text-field v-model="createForm.title" label="Title" :rules="[r => !!r || 'Title is required']" />
          <v-textarea v-model="createForm.body_text" label="Body Text" rows="6" />
          <v-select
            v-model="createForm.layout_id"
            :items="layouts"
            item-title="display_name"
            item-value="id"
            label="Layout"
            :rules="[r => !!r || 'Layout is required']"
          />
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

    <!-- Edit / Expand Dialog -->
    <v-dialog v-model="showEditDialog" max-width="640" persistent>
      <v-card>
        <v-card-title>Edit Info Card</v-card-title>
        <v-card-text>
          <!-- LLM Generation Section -->
          <v-card variant="tonal" class="mb-4 pa-3">
            <div class="text-subtitle-2 mb-2">Regenerate from Knowledge Document</div>
            <v-row dense>
              <v-col cols="12">
                <LlmModelPicker
                  v-model="editGenerateModelId"
                  :model-items="llmModelItems"
                  label="LLM Model"
                  hint="Model used for regeneration"
                  persistent-hint
                  clearable
                />
              </v-col>
              <v-col cols="12" sm="8">
                <v-select
                  v-model="editForm.document_id"
                  :items="documentOptions"
                  item-title="title"
                  item-value="id"
                  label="Knowledge Document"
                  hint="Source document for content regeneration"
                  persistent-hint
                  clearable
                />
              </v-col>
              <v-col cols="12" sm="4" class="d-flex align-center">
                <v-btn
                  color="secondary"
                  variant="tonal"
                  :loading="editGenerating"
                  :disabled="!editForm.document_id"
                  block
                  class="mt-2"
                  @click="generateEditFromDocument"
                >
                  Regenerate
                </v-btn>
              </v-col>
            </v-row>
          </v-card>

          <v-text-field v-model="editForm.title" label="Title" class="mb-3" />
          <v-textarea v-model="editForm.body_text" label="Body Text" rows="6" class="mb-3" />
          <v-select
            v-model="editForm.layout_id"
            :items="layouts"
            item-title="display_name"
            item-value="id"
            label="Layout"
            class="mb-3"
          />
          <v-combobox
            v-model="editForm.tags"
            label="Tags"
            multiple
            chips
            deletable-chips
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="showEditDialog = false">Cancel</v-btn>
          <v-btn color="primary" :loading="saving" @click="submitEdit">Save</v-btn>
        </v-card-actions>
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

const { notify } = useNotify();
const { confirmDialog, confirmTitle, confirmText, confirmLabel, cancelLabel, confirmColor, require: confirmRequire, onConfirm, onCancel } = useConfirm();

const cards = ref([]);
const layouts = ref([]);
const documentOptions = ref([]);
const llmModelItems = ref([]);
const loading = ref(false);
const totalItems = ref(0);
const itemsPerPage = ref(20);
const page = ref(1);
const creating = ref(false);
const saving = ref(false);
const generating = ref(false);
const generateModelId = ref("");
const editGenerating = ref(false);
const editGenerateModelId = ref("");
const showCreateDialog = ref(false);
const showEditDialog = ref(false);
const deleteDialog = ref(false);
const deleteTarget = ref(null);
const editingItem = ref(null);

const headers = [
  { title: "Title", key: "title", sortable: true },
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
  document_id: "",
});

const createForm = reactive({
  title: "",
  body_text: "",
  layout_id: null,
  document_id: null,
  tags: [],
});

const editForm = reactive({
  title: "",
  body_text: "",
  layout_id: null,
  document_id: null,
  tags: [],
});

let debounceTimer = null;
function debouncedFetch() {
  clearTimeout(debounceTimer);
  page.value = 1;
  debounceTimer = setTimeout(fetchCards, 300);
}

function onPageOptions({ page: newPage, itemsPerPage: newPerPage }) {
  if (newPerPage !== itemsPerPage.value) {
    itemsPerPage.value = newPerPage;
    page.value = 1;
  } else {
    page.value = newPage;
  }
  fetchCards();
}

function statusColor(status) {
  const map = {
    draft: "blue",
    approved: "green",
    archived: "grey",
  };
  return map[status] || "default";
}

async function fetchCards() {
  loading.value = true;
  try {
    const params = { limit: itemsPerPage.value, offset: (page.value - 1) * itemsPerPage.value };
    if (filters.status) params.status = filters.status;
    if (filters.tags && filters.tags.length > 0) params.tags = filters.tags.join(",");
    if (filters.document_id) params.document_id = filters.document_id;
    const res = await api.getInfoCards(params);
    cards.value = res.items ?? [];
    totalItems.value = res.total ?? 0;
  } catch (err) {
    notify.error("Failed to load info cards: " + (err.message || err));
  } finally {
    loading.value = false;
  }
}

async function fetchLayouts() {
  try {
    const res = await api.getKnowledgeLayouts("info_card");
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

async function generateFromDocument() {
  if (!createForm.document_id) {
    notify.warning("Select a knowledge document first.");
    return;
  }
  generating.value = true;
  try {
    const suggestion = await api.suggestInfoCard(createForm.document_id, generateModelId.value || undefined);
    if (suggestion.title) createForm.title = suggestion.title;
    if (suggestion.body_text) createForm.body_text = suggestion.body_text;
    notify.success("Info card draft generated from document.");
  } catch (err) {
    notify.error("Failed to generate: " + (err.message || err));
  } finally {
    generating.value = false;
  }
}

async function generateEditFromDocument() {
  if (!editForm.document_id) {
    notify.warning("Select a knowledge document first.");
    return;
  }
  editGenerating.value = true;
  try {
    const suggestion = await api.suggestInfoCard(editForm.document_id, editGenerateModelId.value || undefined);
    if (suggestion.title) editForm.title = suggestion.title;
    if (suggestion.body_text) editForm.body_text = suggestion.body_text;
    notify.success("Info card content regenerated.");
  } catch (err) {
    notify.error("Failed to regenerate: " + (err.message || err));
  } finally {
    editGenerating.value = false;
  }
}

async function submitCreate() {
  if (!createForm.title || !createForm.layout_id) {
    notify.warning("Title and Layout are required.");
    return;
  }
  creating.value = true;
  try {
    await api.createInfoCard({
      title: createForm.title,
      body_text: createForm.body_text,
      layout_id: createForm.layout_id,
      document_id: createForm.document_id || undefined,
      tags: createForm.tags,
    });
    notify.success("Info card created.");
    closeCreateDialog();
    await fetchCards();
  } catch (err) {
    notify.error("Failed to create: " + (err.message || err));
  } finally {
    creating.value = false;
  }
}

function closeCreateDialog() {
  showCreateDialog.value = false;
  createForm.title = "";
  createForm.body_text = "";
  createForm.layout_id = null;
  createForm.document_id = null;
  createForm.tags = [];
  generateModelId.value = "";
}

function editCard(item) {
  editingItem.value = item;
  editForm.title = item.title ?? "";
  editForm.body_text = item.body_text ?? "";
  editForm.layout_id = item.layout_id ?? null;
  editForm.document_id = item.document_id ?? null;
  editForm.tags = item.tags ?? [];
  editGenerateModelId.value = "";
  showEditDialog.value = true;
}

async function submitEdit() {
  if (!editingItem.value) return;
  saving.value = true;
  try {
    await api.updateInfoCard(editingItem.value.id, {
      title: editForm.title,
      body_text: editForm.body_text,
      layout_id: editForm.layout_id,
      document_id: editForm.document_id || undefined,
      tags: editForm.tags,
    });
    notify.success("Info card updated.");
    showEditDialog.value = false;
    editingItem.value = null;
    await fetchCards();
  } catch (err) {
    notify.error("Failed to update: " + (err.message || err));
  } finally {
    saving.value = false;
  }
}

async function approve(item) {
  try {
    await api.approveInfoCard(item.id);
    notify.success("Info card approved.");
    await fetchCards();
  } catch (err) {
    notify.error("Failed to approve: " + (err.message || err));
  }
}

async function archive(item) {
  try {
    await api.archiveInfoCard(item.id);
    notify.success("Info card archived.");
    await fetchCards();
  } catch (err) {
    notify.error("Failed to archive: " + (err.message || err));
  }
}

async function restore(item) {
  try {
    await api.restoreInfoCard(item.id);
    notify.success("Info card restored.");
    await fetchCards();
  } catch (err) {
    notify.error("Failed to restore: " + (err.message || err));
  }
}

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
    await api.deleteInfoCard(item.id);
    notify.success("Info card deleted.");
    await fetchCards();
  } catch (err) {
    notify.error("Failed to delete: " + (err.message || err));
  }
}

onMounted(() => {
  fetchCards();
  fetchLayouts();
  fetchDocuments();
  fetchLLMModels();
});
</script>
