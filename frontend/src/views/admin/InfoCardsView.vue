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
        v-model="state.filters.status"
        :items="statusOptions"
        label="Status"
        variant="outlined"
        density="compact"
        hide-details
        clearable
        style="max-width: 160px"
        @update:model-value="actions.onFilterChange"
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
        @update:model-value="actions.onFilterChange"
      />
      <v-text-field
        v-model="state.filters.document_id"
        label="Document ID"
        variant="outlined"
        density="compact"
        hide-details
        clearable
        style="max-width: 180px"
        @update:model-value="actions.onFilterTyped"
      />
      <v-btn color="primary" variant="flat" prepend-icon="mdi-plus" @click="openCreate()">
        New Info Card
      </v-btn>
    </div>

    <v-card class="glass-card">
      <v-data-table
        :headers="headers"
        :items="state.cards"
        :loading="state.loading"
        :items-length="state.totalCards"
        :items-per-page="state.itemsPerPage"
        :page="state.page"
        @update:options="actions.onPageOptions"
      >
        <template #[`item.layout_id`]="{ item }">
          <v-chip size="x-small" color="primary" variant="outlined">
            {{ item.layout_id ?? "-" }}
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
            @click="editCard(item)"
          />
          <v-btn
            v-if="item.status !== 'approved'"
            icon="mdi-check"
            size="small"
            variant="text"
            color="success"
            @click="actions.approve(item)"
          />
          <v-btn
            v-if="item.status !== 'archived'"
            icon="mdi-archive"
            size="small"
            variant="text"
            @click="actions.archive(item)"
          />
          <v-btn
            v-if="item.status === 'archived'"
            icon="mdi-restore"
            size="small"
            variant="text"
            color="warning"
            @click="actions.restore(item)"
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

    <InfoCardFormDialog
      v-model="showForm"
      :mode="formMode"
      :card="editingCard"
      :initial-document-id="initialDocumentId"
      :layouts="state.layouts"
      :documents="state.documents"
      :llm-model-items="state.llmModelItems"
      @saved="actions.fetchCards"
    />

    <!-- Delete Confirm Dialog -->
    <ArchiveOrDeleteDialog
      v-model="deleteDialog"
      noun="info card"
      :name="deleteTarget?.title || ''"
      @archive="doArchive"
      @delete="doDelete"
    />
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { getInfoCard } from "@/services/modules/info_cards";
import { knowledgeStatusColor as statusColor } from "@/constants/knowledgeStatus.js";
import { useNotify } from "@/composables/useNotify.js";
import { useInfoCardsAdmin } from "@/composables/useInfoCardsAdmin.js";
import ArchiveOrDeleteDialog from "@/components/common/ArchiveOrDeleteDialog.vue";
import InfoCardFormDialog from "@/components/knowledge/InfoCardFormDialog.vue";

const { notify } = useNotify();
const { state, actions } = useInfoCardsAdmin({ notify });
const route = useRoute();

const showForm = ref(false);
const formMode = ref("create");
const editingCard = ref(null);
const initialDocumentId = ref(null);
const deleteDialog = ref(false);
const deleteTarget = ref(null);

const headers = [
  { title: "Title", key: "title", sortable: true },
  { title: "Layout", key: "layout_id", sortable: true },
  { title: "Status", key: "status", sortable: true, width: 100 },
  { title: "Version", key: "version", sortable: true, width: 80 },
  { title: "Approved By", key: "approved_by", sortable: false },
  { title: "Actions", key: "actions", sortable: false, width: 200 },
];

const statusOptions = ["draft", "approved", "archived"];

function openCreate(documentId = null) {
  formMode.value = "create";
  editingCard.value = null;
  initialDocumentId.value = documentId;
  showForm.value = true;
}

async function editCard(item) {
  // The dialog is given the full card. List rows carry no body_text or voice_instruction,
  // so a form filled from the row opened blank, and saving it erased the card's text.
  let full;
  try {
    full = await getInfoCard(item.id);
  } catch (err) {
    notify.error("Failed to load the card: " + (err.message || err));
    return;
  }
  formMode.value = "edit";
  editingCard.value = full;
  showForm.value = true;
}

function confirmDelete(item) {
  deleteTarget.value = item;
  deleteDialog.value = true;
}

async function doArchive() {
  deleteDialog.value = false;
  if (deleteTarget.value) await actions.archive(deleteTarget.value);
  deleteTarget.value = null;
}

async function doDelete() {
  deleteDialog.value = false;
  const item = deleteTarget.value;
  deleteTarget.value = null;
  if (item) await actions.remove(item);
}

onMounted(() => {
  actions.fetchCards();
  actions.fetchLayouts();
  actions.fetchDocuments();
  actions.fetchLLMModels();
  // Set by the document page's "Create info card" action (?suggest_doc_id=<id>).
  const docId = Number(route.query.suggest_doc_id);
  if (Number.isInteger(docId) && docId > 0) openCreate(docId);
});
</script>
