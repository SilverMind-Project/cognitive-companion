<template>
  <div>
    <v-card class="pa-4">
      <v-row align="center" dense>
        <v-col cols="12" sm="4">
          <v-text-field
            v-model="filters.q"
            label="Search documents"
            prepend-inner-icon="mdi-magnify"
            density="compact"
            hide-details
            clearable
            @update:model-value="debouncedFetch"
          />
        </v-col>
        <v-col cols="6" sm="2">
          <v-select
            v-model="filters.status"
            :items="statusOptions"
            label="Status"
            density="compact"
            hide-details
            clearable
            @update:model-value="fetchDocuments"
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
            @update:model-value="fetchDocuments"
          />
        </v-col>
        <v-col cols="auto" class="ml-auto">
          <v-btn color="primary" prepend-icon="mdi-plus" @click="showCreateDialog = true">
            New Document
          </v-btn>
        </v-col>
      </v-row>
    </v-card>

    <v-data-table
      :headers="headers"
      :items="documents"
      :loading="loading"
      :items-per-page="20"
      class="mt-2"
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

      <template #bottom>
        <div class="pa-4 text-center" v-if="documents.length === 0 && !loading">
          <v-card flat>
            <v-card-text class="text-grey">No documents yet.</v-card-text>
          </v-card>
        </div>
      </template>
    </v-data-table>

    <!-- Create Dialog -->
    <v-dialog v-model="showCreateDialog" max-width="640" persistent>
      <v-card>
        <v-card-title>New Knowledge Document</v-card-title>
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

const documents = ref([]);
const loading = ref(false);
const creating = ref(false);
const showCreateDialog = ref(false);

const headers = [
  { title: "Title", key: "title", sortable: true },
  { title: "Tags", key: "tags", sortable: false },
  { title: "Images", key: "image_count", sortable: false, width: 80 },
  { title: "Status", key: "status", sortable: true, width: 100 },
  { title: "Created", key: "created_at", sortable: true },
  { title: "Actions", key: "actions", sortable: false, width: 160 },
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
  debounceTimer = setTimeout(fetchDocuments, 300);
}

async function fetchDocuments() {
  loading.value = true;
  try {
    const params = {};
    if (filters.q) params.q = filters.q;
    if (filters.status) params.status = filters.status;
    if (filters.tags && filters.tags.length > 0) params.tags = filters.tags.join(",");
    const res = await api.getKnowledgeDocuments(params);
    const body = res.data ?? res;
    documents.value = Array.isArray(body) ? body : (body?.items ?? []);
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
    await api.deleteKnowledgeDocument(item.id);
    notify.success("Document deleted.");
    await fetchDocuments();
  } catch (err) {
    notify.error("Failed to delete: " + (err.message || err));
  }
}

onMounted(fetchDocuments);
</script>
