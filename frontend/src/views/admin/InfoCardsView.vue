<template>
  <div>
    <v-card class="pa-4">
      <v-row align="center" dense>
        <v-col cols="6" sm="2">
          <v-select
            v-model="filters.status"
            :items="statusOptions"
            label="Status"
            density="compact"
            hide-details
            clearable
            @update:model-value="fetchCards"
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
            @update:model-value="fetchCards"
          />
        </v-col>
        <v-col cols="6" sm="3">
          <v-text-field
            v-model="filters.document_id"
            label="Document ID"
            density="compact"
            hide-details
            clearable
            @update:model-value="debouncedFetch"
          />
        </v-col>
        <v-col cols="auto" class="ml-auto">
          <v-btn color="primary" prepend-icon="mdi-plus" @click="showCreateDialog = true">
            New Info Card
          </v-btn>
        </v-col>
      </v-row>
    </v-card>

    <v-data-table
      :headers="headers"
      :items="cards"
      :loading="loading"
      :items-per-page="20"
      class="mt-2"
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

      <template #bottom>
        <div class="pa-4 text-center" v-if="cards.length === 0 && !loading">
          <v-card flat>
            <v-card-text class="text-grey">No info cards yet.</v-card-text>
          </v-card>
        </div>
      </template>
    </v-data-table>

    <!-- Create Dialog -->
    <v-dialog v-model="showCreateDialog" max-width="600" persistent>
      <v-card>
        <v-card-title>New Info Card</v-card-title>
        <v-card-text>
          <v-text-field v-model="createForm.title" label="Title" :rules="[r => !!r || 'Title is required']" />
          <v-textarea v-model="createForm.body_text" label="Body Text" rows="6" />
          <v-select
            v-model="createForm.layout_id"
            :items="layouts"
            item-title="title"
            item-value="id"
            label="Layout"
            :rules="[r => !!r || 'Layout is required']"
          />
          <v-select
            v-model="createForm.document_id"
            :items="documentOptions"
            item-title="title"
            item-value="id"
            label="Document (optional)"
            clearable
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
    <v-dialog v-model="showEditDialog" max-width="600" persistent>
      <v-card>
        <v-card-title>Edit Info Card</v-card-title>
        <v-card-text>
          <v-text-field v-model="editForm.title" label="Title" />
          <v-textarea v-model="editForm.body_text" label="Body Text" rows="6" />
          <v-select
            v-model="editForm.layout_id"
            :items="layouts"
            item-title="title"
            item-value="id"
            label="Layout"
          />
          <v-select
            v-model="editForm.document_id"
            :items="documentOptions"
            item-title="title"
            item-value="id"
            label="Document (optional)"
            clearable
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

const cards = ref([]);
const layouts = ref([]);
const documentOptions = ref([]);
const loading = ref(false);
const creating = ref(false);
const saving = ref(false);
const showCreateDialog = ref(false);
const showEditDialog = ref(false);
const editingItem = ref(null);

const headers = [
  { title: "Title", key: "title", sortable: true },
  { title: "Layout", key: "layout_id", sortable: true },
  { title: "Status", key: "status", sortable: true, width: 100 },
  { title: "Version", key: "version", sortable: true, width: 80 },
  { title: "Approved By", key: "approved_by", sortable: false },
  { title: "Actions", key: "actions", sortable: false, width: 160 },
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
  debounceTimer = setTimeout(fetchCards, 300);
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
    const params = {};
    if (filters.status) params.status = filters.status;
    if (filters.tags && filters.tags.length > 0) params.tags = filters.tags.join(",");
    if (filters.document_id) params.document_id = filters.document_id;
    const res = await api.getInfoCards(params);
    cards.value = res.data ?? res ?? [];
  } catch (err) {
    notify.error("Failed to load info cards: " + (err.message || err));
  } finally {
    loading.value = false;
  }
}

async function fetchLayouts() {
  try {
    const res = await api.getKnowledgeLayouts("info_card");
    layouts.value = res.data ?? res ?? [];
  } catch (err) {
    notify.error("Failed to load layouts: " + (err.message || err));
  }
}

async function fetchDocuments() {
  try {
    const res = await api.getKnowledgeDocuments({ per_page: 200 });
    documentOptions.value = res.data ?? res ?? [];
  } catch (_) {
    // non-critical
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
}

function editCard(item) {
  editingItem.value = item;
  editForm.title = item.title ?? "";
  editForm.body_text = item.body_text ?? "";
  editForm.layout_id = item.layout_id ?? null;
  editForm.document_id = item.document_id ?? null;
  editForm.tags = item.tags ?? [];
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
});
</script>
