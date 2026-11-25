<template>
  <div>
    <div class="d-flex align-center flex-wrap ga-3 mb-6">
      <div class="d-flex align-center ga-2">
        <v-btn variant="text" icon="mdi-arrow-left" to="/admin/knowledge/documents" />
        <div>
          <h2 class="text-h4 font-weight-bold tracking-tight">
            {{ document?.title || "Edit Document" }}
          </h2>
          <div class="text-body-2 text-medium-emphasis mt-1">
            Edit document metadata, images, and workflow status.
          </div>
        </div>
      </div>
      <v-spacer />
      <v-btn color="primary" :loading="saving" @click="save">Save</v-btn>
      <v-btn
        v-if="document?.status !== 'approved' && document?.status !== 'archived'"
        color="success"
        variant="tonal"
        @click="approve"
      >
        Approve
      </v-btn>
      <v-btn
        v-if="document?.status !== 'archived'"
        color="warning"
        variant="tonal"
        @click="archive"
      >
        Archive
      </v-btn>
      <v-btn
        v-if="document?.status === 'archived'"
        color="warning"
        variant="tonal"
        @click="restore"
      >
        Restore
      </v-btn>
      <v-btn color="error" variant="text" @click="confirmDelete"> Delete </v-btn>
      <v-btn
        variant="text"
        :loading="reembedding"
        :disabled="document?.status === 'archived'"
        data-test="reembed"
        @click="reEmbed"
      >
        Re-embed
      </v-btn>
      <v-btn
        variant="tonal"
        color="secondary"
        prepend-icon="mdi-card-text-outline"
        :disabled="!document"
        data-test="create-card"
        @click="createFromDocument('admin-info-cards')"
      >
        Create info card
      </v-btn>
      <v-btn
        variant="tonal"
        color="secondary"
        prepend-icon="mdi-help-box-outline"
        :disabled="!document"
        data-test="create-quiz"
        @click="createFromDocument('admin-quizzes')"
      >
        Create quiz
      </v-btn>
    </div>

    <v-card v-if="loading" class="pa-8 text-center">
      <v-progress-circular indeterminate />
    </v-card>

    <template v-else-if="document">
      <v-row>
        <v-col cols="12" md="8">
          <v-card class="glass-card pa-4 mb-4">
            <v-card-title class="pa-0 mb-4">Content</v-card-title>
            <v-text-field
              v-model="editForm.title"
              label="Title"
              variant="outlined"
              density="comfortable"
              :rules="[(r) => !!r || 'Title is required']"
              class="mb-3"
            />
            <v-textarea
              v-model="editForm.source_text"
              label="Source Text"
              variant="outlined"
              rows="8"
              class="mb-3"
            />
            <v-combobox
              v-model="editForm.tags"
              label="Tags"
              variant="outlined"
              multiple
              chips
              closable-chips
            />
          </v-card>

          <v-card class="glass-card pa-4">
            <v-card-title class="pa-0 mb-3">Images</v-card-title>
            <v-row v-if="images.length > 0" class="mb-3">
              <v-col v-for="img in images" :key="img.id" cols="6" sm="4" md="3">
                <v-card>
                  <v-img :src="img.presigned_url" height="140" cover />
                  <v-card-actions class="pa-1">
                    <v-spacer />
                    <v-btn
                      icon="mdi-delete"
                      size="x-small"
                      color="error"
                      variant="text"
                      @click="confirmDeleteImage(img)"
                    />
                  </v-card-actions>
                </v-card>
              </v-col>
            </v-row>
            <v-card-text v-else class="text-medium-emphasis pa-0 pb-3"
              >No images attached.</v-card-text
            >
            <v-file-input
              v-model="newImages"
              label="Add images"
              multiple
              accept="image/*"
              variant="outlined"
              prepend-icon="mdi-camera"
              show-size
              class="mb-2"
            />
            <v-btn
              v-if="newImages.length > 0"
              color="primary"
              variant="tonal"
              size="small"
              :loading="uploadingImages"
              @click="uploadImages"
            >
              Upload Images
            </v-btn>
          </v-card>
        </v-col>

        <v-col cols="12" md="4">
          <v-card class="glass-card pa-4">
            <v-card-title class="pa-0 mb-3">Details</v-card-title>
            <v-chip :color="statusColor(document.status)" size="small" class="mb-3">
              {{ document.status }}
            </v-chip>
            <div class="text-body-2 mb-2">
              <strong>Created by:</strong> {{ document.created_by ?? "Unknown" }}
            </div>
            <div class="text-body-2 mb-2">
              <strong>Created at:</strong> {{ formatDateTime(document.created_at) }}
            </div>
            <div class="text-body-2"><strong>Chunks:</strong> {{ document.chunk_count ?? 0 }}</div>
          </v-card>
        </v-col>
      </v-row>
    </template>

    <!-- Confirm Dialog -->
    <v-dialog v-model="confirmDialog" max-width="400" persistent>
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
    <ArchiveOrDeleteDialog
      v-model="deleteDialog"
      noun="document"
      :name="document?.title || ''"
      @archive="doArchive"
      @delete="doDelete"
    />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  addKnowledgeDocumentImage,
  approveKnowledgeDocument,
  archiveKnowledgeDocument,
  deleteKnowledgeDocument,
  deleteKnowledgeDocumentImage,
  getKnowledgeDocument,
  reembedKnowledgeDocument,
  restoreKnowledgeDocument,
  updateKnowledgeDocument,
} from "@/services/modules/knowledge";
import { knowledgeStatusColor as statusColor } from "@/constants/knowledgeStatus.js";
import { useNotify } from "@/composables/useNotify.js";
import ArchiveOrDeleteDialog from "@/components/common/ArchiveOrDeleteDialog.vue";
import { useConfirm } from "@/composables/useConfirm.js";
import { formatDateTime } from "@/services/timezone.js";

const route = useRoute();
const router = useRouter();
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

const document = ref(null);
const loading = ref(true);
const saving = ref(false);
const uploadingImages = ref(false);
const newImages = ref([]);
const deleteDialog = ref(false);
const reembedding = ref(false);
const docId = () => Number(route.params.id);

const editForm = reactive({
  title: "",
  source_text: "",
  tags: [],
});

const images = ref([]);

async function fetchDocument() {
  loading.value = true;
  try {
    const res = await getKnowledgeDocument(docId());
    const doc = res;
    document.value = doc;
    editForm.title = doc.title ?? "";
    editForm.source_text = doc.source_text ?? "";
    editForm.tags = doc.tags ?? [];
    images.value = doc.images ?? [];
  } catch (err) {
    notify.error("Failed to load document: " + (err.message || err));
  } finally {
    loading.value = false;
  }
}

async function save() {
  if (!editForm.title) {
    notify.warning("Title is required.");
    return;
  }
  saving.value = true;
  try {
    await updateKnowledgeDocument(docId(), {
      title: editForm.title,
      source_text: editForm.source_text,
      tags: editForm.tags,
    });
    notify.success("Document saved.");
    await fetchDocument();
  } catch (err) {
    notify.error("Failed to save: " + (err.message || err));
  } finally {
    saving.value = false;
  }
}

async function uploadImages() {
  if (newImages.value.length === 0) return;
  uploadingImages.value = true;
  try {
    for (const img of newImages.value) {
      const fd = new FormData();
      fd.append("file", img);
      await addKnowledgeDocumentImage(docId(), fd);
    }
    notify.success("Images uploaded.");
    newImages.value = [];
    await fetchDocument();
  } catch (err) {
    notify.error("Failed to upload images: " + (err.message || err));
  } finally {
    uploadingImages.value = false;
  }
}

async function confirmDeleteImage(img) {
  const ok = await confirmRequire("Delete this image?");
  if (!ok) return;
  try {
    await deleteKnowledgeDocumentImage(docId(), img.id);
    notify.success("Image deleted.");
    await fetchDocument();
  } catch (err) {
    notify.error("Failed to delete image: " + (err.message || err));
  }
}

async function approve() {
  try {
    await approveKnowledgeDocument(docId());
    notify.success("Document approved.");
    await fetchDocument();
  } catch (err) {
    notify.error("Failed to approve: " + (err.message || err));
  }
}

async function archive() {
  try {
    await archiveKnowledgeDocument(docId());
    notify.success("Document archived.");
    await fetchDocument();
  } catch (err) {
    notify.error("Failed to archive: " + (err.message || err));
  }
}

async function restore() {
  try {
    await restoreKnowledgeDocument(docId());
    notify.success("Document restored.");
    await fetchDocument();
  } catch (err) {
    notify.error("Failed to restore: " + (err.message || err));
  }
}

function confirmDelete() {
  deleteDialog.value = true;
}

async function doArchive() {
  deleteDialog.value = false;
  await archive();
}

async function doDelete() {
  deleteDialog.value = false;
  try {
    await deleteKnowledgeDocument(docId());
    notify.success("Document deleted.");
    router.push("/admin/knowledge/documents");
  } catch (err) {
    notify.error("Failed to delete: " + (err.message || err));
  }
}

async function reEmbed() {
  reembedding.value = true;
  try {
    await reembedKnowledgeDocument(docId());
    notify.success("Document re-embedded.");
    await fetchDocument();
  } catch (err) {
    notify.error("Failed to re-embed: " + (err.message || err));
  } finally {
    reembedding.value = false;
  }
}

/** Open the card or quiz page with its generator pre-set to this document. */
function createFromDocument(routeName) {
  router.push({ name: routeName, query: { suggest_doc_id: String(docId()) } });
}

onMounted(fetchDocument);
</script>
