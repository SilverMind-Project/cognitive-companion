<template>
  <div>
    <div class="d-flex align-center flex-wrap ga-3 mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Knowledge Documents</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Manage documents used for knowledge queries, quizzes, and info cards.
        </div>
      </div>
      <v-spacer />
      <v-text-field
        v-model="filters.q"
        label="Search documents"
        prepend-inner-icon="mdi-magnify"
        variant="outlined"
        density="compact"
        hide-details
        clearable
        style="max-width: 240px"
        @update:model-value="debouncedFetch"
      />
      <v-select
        v-model="filters.status"
        :items="statusOptions"
        label="Status"
        variant="outlined"
        density="compact"
        hide-details
        clearable
        style="max-width: 160px"
        @update:model-value="page = 1; fetchDocuments()"
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
        @update:model-value="page = 1; fetchDocuments()"
      />
      <v-btn color="primary" variant="flat" prepend-icon="mdi-plus" @click="showCreateDialog = true">
        New Document
      </v-btn>
    </div>

    <v-card class="glass-card">
      <v-data-table
        :headers="headers"
        :items="documents"
        :loading="loading"
        :items-length="totalItems"
        :items-per-page="itemsPerPage"
        :page="page"
        @update:options="onPageOptions"
      >
      <template #[`item.title`]="{ item }">
        {{ truncate(item.title, 60) }}
      </template>

      <template #[`item.tags`]="{ item }">
        <v-chip
          v-for="tag in (item.tags || [])"
          :key="tag"
          size="x-small"
          class="mr-1"
        >
          {{ tag }}
        </v-chip>
        <span v-if="!item.tags || item.tags.length === 0" class="text-caption text-grey">—</span>
      </template>

      <template #[`item.image_count`]="{ item }">
        {{ item.image_count ?? item.images?.length ?? 0 }}
      </template>

      <template #[`item.status`]="{ item }">
        <v-chip :color="statusColor(item.status)" size="small">
          {{ item.status }}
        </v-chip>
      </template>

      <template #[`item.created_at`]="{ item }">
        {{ formatDateTime(item.created_at) }}
      </template>

      <template #[`item.actions`]="{ item }">
        <v-btn
          icon="mdi-pencil"
          size="small"
          variant="text"
          color="primary"
          :to="`/admin/knowledge/documents/${item.id}`"
        />
        <v-btn
          v-if="item.status === 'uploaded' || item.status === 'chunked'"
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
        <DialogHeader
          icon="mdi-file-document-outline"
          label="Create New"
          title="Knowledge Document"
          @close="closeCreateDialog"
        />
        <v-card-text>
          <v-form ref="createForm">
            <v-text-field
              v-model="createFormData.title"
              label="Title"
              :rules="[r => !!r || 'Title is required']"
              required
            />
            <v-textarea
              v-model="createFormData.source_text"
              label="Source Text"
              rows="6"
            />
            <v-combobox
              v-model="createFormData.tags"
              label="Tags"
              multiple
              chips
              deletable-chips
            />
            <v-file-input
              v-model="createFormData.images"
              label="Images"
              multiple
              accept="image/*"
              prepend-icon="mdi-camera"
              show-size
            />
          </v-form>
        </v-card-text>
        <DialogFooter
          hint="Upload images and provide source text for content generation."
          confirm-label="Create"
          :confirm-loading="creating"
          @cancel="closeCreateDialog"
          @confirm="submitCreate"
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
import { formatDateTime, DATETIME_COLUMN_WIDTH } from "@/services/timezone.js";
import DialogHeader from "@/components/common/DialogHeader.vue";
import DialogFooter from "@/components/common/DialogFooter.vue";

const { notify } = useNotify();
const { confirmDialog, confirmTitle, confirmText, confirmLabel, cancelLabel, confirmColor, require: confirmRequire, onConfirm, onCancel } = useConfirm();

const documents = ref([]);
const loading = ref(false);
const totalItems = ref(0);
const itemsPerPage = ref(20);
const page = ref(1);
const creating = ref(false);
const showCreateDialog = ref(false);
const deleteDialog = ref(false);
const deleteTarget = ref(null);

const headers = [
  { title: "Title", key: "title", sortable: true },
  { title: "Tags", key: "tags", sortable: false },
  { title: "Images", key: "image_count", sortable: false, width: 80 },
  { title: "Status", key: "status", sortable: true, width: 100 },
  { title: "Created", key: "created_at", sortable: true, width: DATETIME_COLUMN_WIDTH },
  { title: "Actions", key: "actions", sortable: false, width: 200 },
];

const statusOptions = ["uploaded", "chunked", "approved", "archived"];

const filters = reactive({
  q: "",
  status: null,
  tags: [],
});

const createFormData = reactive({
  title: "",
  source_text: "",
  tags: [],
  images: [],
});

let debounceTimer = null;
function debouncedFetch() {
  clearTimeout(debounceTimer);
  page.value = 1;
  debounceTimer = setTimeout(fetchDocuments, 300);
}

function onPageOptions({ page: newPage, itemsPerPage: newPerPage }) {
  if (newPerPage !== itemsPerPage.value) {
    itemsPerPage.value = newPerPage;
    page.value = 1;
  } else {
    page.value = newPage;
  }
  fetchDocuments();
}

async function fetchDocuments() {
  loading.value = true;
  try {
    const params = { limit: itemsPerPage.value, offset: (page.value - 1) * itemsPerPage.value };
    if (filters.q) params.q = filters.q;
    if (filters.status) params.status = filters.status;
    if (filters.tags && filters.tags.length > 0) params.tags = filters.tags.join(",");
    const res = await api.getKnowledgeDocuments(params);
    documents.value = res.items ?? [];
    totalItems.value = res.total ?? 0;
  } catch (err) {
    notify.error("Failed to load documents: " + (err.message || err));
  } finally {
    loading.value = false;
  }
}

function statusColor(status) {
  const map = {
    uploaded: "blue",
    chunked: "orange",
    approved: "green",
    archived: "grey",
  };
  return map[status] || "default";
}

function truncate(text, len) {
  if (!text) return "";
  return text.length > len ? text.slice(0, len) + "..." : text;
}

async function submitCreate() {
  creating.value = true;
  try {
    const fd = new FormData();
    fd.append("title", createFormData.title);
    fd.append("source_text", createFormData.source_text || "");
    for (const tag of createFormData.tags) {
      fd.append("tags", tag);
    }
    for (const img of createFormData.images) {
      fd.append("images", img);
    }
    await api.createKnowledgeDocument(fd);
    notify.success("Document created.");
    closeCreateDialog();
    await fetchDocuments();
  } catch (err) {
    notify.error("Failed to create document: " + (err.message || err));
  } finally {
    creating.value = false;
  }
}

function closeCreateDialog() {
  showCreateDialog.value = false;
  createFormData.title = "";
  createFormData.source_text = "";
  createFormData.tags = [];
  createFormData.images = [];
}

async function approve(item) {
  try {
    await api.approveKnowledgeDocument(item.id);
    notify.success("Document approved.");
    await fetchDocuments();
  } catch (err) {
    notify.error("Failed to approve: " + (err.message || err));
  }
}

async function archive(item) {
  try {
    await api.archiveKnowledgeDocument(item.id);
    notify.success("Document archived.");
    await fetchDocuments();
  } catch (err) {
    notify.error("Failed to archive: " + (err.message || err));
  }
}

async function restore(item) {
  try {
    await api.restoreKnowledgeDocument(item.id);
    notify.success("Document restored.");
    await fetchDocuments();
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
    await api.deleteKnowledgeDocument(item.id);
    notify.success("Document deleted.");
    await fetchDocuments();
  } catch (err) {
    notify.error("Failed to delete: " + (err.message || err));
  }
}

onMounted(fetchDocuments);
</script>
