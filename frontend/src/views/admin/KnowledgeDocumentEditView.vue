<template>
  <div>
    <v-btn
      variant="text"
      prepend-icon="mdi-arrow-left"
      class="mb-2"
      to="/admin/knowledge/documents"
    >
      Back to Documents
    </v-btn>

    <v-card v-if="loading" class="pa-8 text-center">
      <v-progress-circular indeterminate />
    </v-card>

    <template v-else-if="document">
      <v-card class="pa-4 mb-4">
        <v-row dense>
          <v-col cols="12" md="8">
            <v-text-field
              v-model="editForm.title"
              label="Title"
              :rules="[r => !!r || 'Title is required']"
            />
            <v-textarea
              v-model="editForm.source_text"
              label="Source Text"
              rows="8"
            />
            <v-combobox
              v-model="editForm.tags"
              label="Tags"
              multiple
              chips
              deletable-chips
            />
          </v-col>
          <v-col cols="12" md="4">
            <v-list-subheader>Details</v-list-subheader>
            <v-chip :color="statusColor(document.status)" size="small" class="mb-2">
              {{ document.status }}
            </v-chip>
            <div class="text-body-2 mt-1">
              <strong>Created by:</strong> {{ document.created_by ?? "—" }}
            </div>
            <div class="text-body-2">
              <strong>Created at:</strong> {{ formatDateTime(document.created_at) }}
            </div>
            <div class="text-body-2">
              <strong>Chunks:</strong> {{ document.chunk_count ?? 0 }}
            </div>
          </v-col>
        </v-row>
      </v-card>

      <!-- Image Gallery -->
      <v-card class="pa-4 mb-4">
        <v-card-title class="pa-0 mb-2">Images</v-card-title>
        <v-row v-if="images.length > 0">
          <v-col v-for="img in images" :key="img.id" cols="6" sm="4" md="3">
            <v-card>
              <v-img :src="img.url || img.image_url" height="140" cover />
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
        <v-card-text v-else class="text-grey pa-0">No images attached.</v-card-text>
        <v-file-input
          v-model="newImages"
          label="Add images"
          multiple
          accept="image/*"
          prepend-icon="mdi-camera"
          class="mt-2"
          show-size
        />
        <v-btn
          v-if="newImages.length > 0"
          color="primary"
          size="small"
          :loading="uploadingImages"
          @click="uploadImages"
        >
          Upload Images
        </v-btn>
      </v-card>

      <!-- Actions -->
      <v-card-actions class="pa-0">
        <v-btn color="primary" :loading="saving" @click="save">Save</v-btn>
        <v-btn
          v-if="document.status !== 'approved'"
          color="success"
          variant="outlined"
          class="ml-2"
          @click="approve"
        >
          Approve
        </v-btn>
        <v-btn
          v-if="document.status !== 'archived'"
          variant="outlined"
          class="ml-2"
          @click="archive"
        >
          Archive
        </v-btn>
        <v-btn
          v-if="document.status === 'archived'"
          color="warning"
          variant="outlined"
          class="ml-2"
          @click="restore"
        >
          Restore
        </v-btn>
        <v-btn
          color="error"
          variant="text"
          class="ml-2"
          @click="confirmDelete"
        >
          Delete
        </v-btn>
        <v-btn
          variant="text"
          class="ml-2"
          @click="reEmbed"
        >
          Re-embed
        </v-btn>
      </v-card-actions>
    </template>

    <!-- Re-embed snackbar -->
    <v-snackbar v-model="reembedSnackbar" timeout="3000">
      Re-embed triggered (stub — not yet implemented).
    </v-snackbar>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "@/services/api.js";
import { useNotify } from "@/composables/useNotify.js";
import { useConfirm } from "@/composables/useConfirm.js";
import { formatDateTime } from "@/services/timezone.js";

const route = useRoute();
const router = useRouter();
const notify = useNotify();
const confirm = useConfirm();

const document = ref(null);
const loading = ref(true);
const saving = ref(false);
const uploadingImages = ref(false);
const newImages = ref([]);
const reembedSnackbar = ref(false);

const editForm = reactive({
  title: "",
  source_text: "",
  tags: [],
});

const images = ref([]);

function statusColor(status) {
  const map = {
    uploaded: "blue",
    chunked: "orange",
    approved: "green",
    archived: "grey",
  };
  return map[status] || "default";
}

async function fetchDocument() {
  loading.value = true;
  try {
    const res = await api.getKnowledgeDocument(route.params.id);
    const doc = res.data ?? res;
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
    await api.updateKnowledgeDocument(route.params.id, {
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
    const fd = new FormData();
    for (const img of newImages.value) {
      fd.append("images", img);
    }
    await api.addKnowledgeDocumentImage(route.params.id, fd);
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
  const ok = await confirm.require("Delete this image?");
  if (!ok) return;
  try {
    await api.deleteKnowledgeDocumentImage(img.id);
    notify.success("Image deleted.");
    await fetchDocument();
  } catch (err) {
    notify.error("Failed to delete image: " + (err.message || err));
  }
}

async function approve() {
  try {
    await api.approveKnowledgeDocument(route.params.id);
    notify.success("Document approved.");
    await fetchDocument();
  } catch (err) {
    notify.error("Failed to approve: " + (err.message || err));
  }
}

async function archive() {
  try {
    await api.archiveKnowledgeDocument(route.params.id);
    notify.success("Document archived.");
    await fetchDocument();
  } catch (err) {
    notify.error("Failed to archive: " + (err.message || err));
  }
}

async function restore() {
  try {
    await api.restoreKnowledgeDocument(route.params.id);
    notify.success("Document restored.");
    await fetchDocument();
  } catch (err) {
    notify.error("Failed to restore: " + (err.message || err));
  }
}

async function confirmDelete() {
  const archiveFirst = await confirm.require(
    "Archive this item instead?",
    { confirmText: "Archive", cancelText: "Delete permanently" }
  );
  if (archiveFirst) {
    await archive();
    return;
  }
  const reallyDelete = await confirm.require(
    "Delete permanently? This cannot be undone.",
    { confirmText: "Delete", color: "error" }
  );
  if (!reallyDelete) return;
  try {
    await api.deleteKnowledgeDocument(route.params.id);
    notify.success("Document deleted.");
    router.push("/admin/knowledge/documents");
  } catch (err) {
    notify.error("Failed to delete: " + (err.message || err));
  }
}

function reEmbed() {
  reembedSnackbar.value = true;
}

onMounted(fetchDocument);
</script>
