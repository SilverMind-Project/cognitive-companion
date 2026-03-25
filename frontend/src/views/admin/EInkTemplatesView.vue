<template>
  <div>
    <div class="d-flex align-center mb-4">
      <h2 class="text-h5">E-Ink Templates</h2>
      <v-spacer />
      <v-btn icon="mdi-refresh" variant="text" class="mr-2" @click="load" />
      <v-btn color="primary" prepend-icon="mdi-plus" @click="openCreate">New Template</v-btn>
    </div>

    <!-- Device Status Panel -->
    <v-card rounded="xl" class="mb-4">
      <v-card-title class="text-subtitle-1">Display Status</v-card-title>
      <v-card-text>
        <v-chip
          v-for="s in states"
          :key="s.sensor_id"
          class="mr-2 mb-2"
          :color="s.expired ? 'grey' : 'success'"
          variant="outlined"
        >
          <v-icon start>mdi-monitor</v-icon>
          {{ s.sensor_id }}
          <span class="ml-1 text-caption">
            {{ s.expired ? "(expired)" : s.rendered_text ? `"${truncate(s.rendered_text)}"` : "(active)" }}
          </span>
        </v-chip>
        <span v-if="!states.length" class="text-grey">No active displays</span>
      </v-card-text>
    </v-card>

    <!-- Templates List -->
    <v-card rounded="xl">
      <v-data-table
        :headers="headers"
        :items="templates"
        :loading="loading"
        item-value="id"
        hover
      >
        <template #item.is_default="{ item }">
          <v-icon v-if="item.is_default" color="success">mdi-check-circle</v-icon>
        </template>
        <template #item.regions_json="{ item }">
          {{ (item.regions_json || []).length }} region(s)
        </template>
        <template #item.actions="{ item }">
          <v-btn icon="mdi-pencil" size="small" variant="text" @click.stop="openEdit(item)" />
          <v-btn icon="mdi-delete" size="small" variant="text" color="error" @click.stop="deleteTemplate(item.id)" />
        </template>
      </v-data-table>
    </v-card>

    <!-- Create / Edit Dialog -->
    <v-dialog v-model="dialog" max-width="900" scrollable>
      <v-card rounded="xl">
        <v-card-title>{{ editing ? "Edit Template" : "Create Template" }}</v-card-title>
        <v-card-text>
          <v-row>
            <v-col cols="12" md="7">
              <!-- Image Upload -->
              <div v-if="!editing" class="mb-4">
                <v-file-input
                  v-model="imageFile"
                  label="Template Image"
                  accept="image/*"
                  variant="outlined"
                  density="comfortable"
                  prepend-icon="mdi-image"
                  @update:model-value="onFileChange"
                />
              </div>

              <!-- Canvas -->
              <BoundingBoxCanvas
                :image-url="previewUrl"
                :regions="form.regions_json"
                :selected-index="selectedRegion"
                @update:regions="form.regions_json = $event"
                @select-region="selectedRegion = $event"
              />

              <p class="text-caption text-grey mt-1">
                Click and drag to create text regions. Click a region to select it.
              </p>
            </v-col>

            <v-col cols="12" md="5">
              <v-text-field
                v-model="form.name"
                label="Name"
                variant="outlined"
                density="comfortable"
                class="mb-3"
              />
              <v-textarea
                v-model="form.description"
                label="Description"
                variant="outlined"
                rows="2"
                class="mb-3"
              />
              <v-select
                v-model="form.font_filename"
                :items="fonts"
                label="Font"
                variant="outlined"
                density="comfortable"
                class="mb-3"
              />
              <v-checkbox
                v-model="form.is_default"
                label="Default template"
                density="comfortable"
                hide-details
                class="mb-3"
              />

              <!-- Region Editor -->
              <template v-if="selectedRegion >= 0 && form.regions_json[selectedRegion]">
                <RegionEditor
                  :region="form.regions_json[selectedRegion]"
                  @update:region="updateRegion"
                  @delete="deleteRegion"
                />
              </template>

              <!-- Preview -->
              <v-divider class="my-3" />
              <v-text-field
                v-model="previewText"
                label="Preview Text"
                variant="outlined"
                density="comfortable"
                class="mb-2"
              />
              <v-btn
                block
                variant="tonal"
                color="primary"
                prepend-icon="mdi-eye"
                :loading="previewing"
                @click="doPreview"
              >
                Preview Render
              </v-btn>
              <v-img
                v-if="renderedPreviewUrl"
                :src="renderedPreviewUrl"
                class="mt-3 rounded"
                max-height="240"
              />
            </v-col>
          </v-row>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="dialog = false">Cancel</v-btn>
          <v-btn color="primary" :loading="saving" @click="save">
            {{ editing ? "Update" : "Create" }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snack" :color="snackColor" timeout="3000">{{ snackText }}</v-snackbar>

    <v-dialog v-model="confirmDialog" max-width="400">
      <v-card rounded="xl">
        <v-card-title>{{ confirmTitle }}</v-card-title>
        <v-card-text>{{ confirmText }}</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="onCancel">Cancel</v-btn>
          <v-btn color="error" @click="onConfirm">Confirm</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { api } from "../../services/api.js";
import BoundingBoxCanvas from "../../components/eink/BoundingBoxCanvas.vue";
import RegionEditor from "../../components/eink/RegionEditor.vue";
import { useNotify } from "../../composables/useNotify.js";
import { useConfirm } from "../../composables/useConfirm.js";

const { snack, snackText, snackColor, notify } = useNotify();
const { confirmDialog, confirmTitle, confirmText, showConfirm, onConfirm, onCancel } = useConfirm();

const templates = ref([]);
const states = ref([]);
const fonts = ref([]);
const loading = ref(false);
const dialog = ref(false);
const editing = ref(false);
const saving = ref(false);
const previewing = ref(false);
const selectedRegion = ref(-1);
const imageFile = ref(null);
const previewUrl = ref("");
const previewText = ref("Hello, this is a sample notification message.");
const renderedPreviewUrl = ref("");
const editingId = ref(null);

const form = ref({
  name: "",
  description: "",
  font_filename: "NotoSansTamil-Regular.ttf",
  is_default: false,
  regions_json: [],
});

const headers = [
  { title: "Name", key: "name" },
  { title: "Image", key: "image_filename" },
  { title: "Font", key: "font_filename" },
  { title: "Regions", key: "regions_json" },
  { title: "Default", key: "is_default", width: 80 },
  { title: "", key: "actions", sortable: false, width: 100 },
];

async function load() {
  loading.value = true;
  try {
    const [tmplResult, stateResult, fontResult] = await Promise.all([
      api.getImageTemplates(),
      api.getImageStates().catch(() => []),
      api.getImageFonts().catch(() => ({ fonts: [] })),
    ]);
    templates.value = tmplResult;
    states.value = stateResult;
    fonts.value = fontResult.fonts || [];
  } catch (e) {
    console.error("Failed to load templates:", e);
    templates.value = [];
  }
  loading.value = false;
}

function openCreate() {
  editing.value = false;
  editingId.value = null;
  form.value = {
    name: "",
    description: "",
    font_filename: fonts.value[0] || "NotoSansTamil-Regular.ttf",
    is_default: false,
    regions_json: [],
  };
  imageFile.value = null;
  previewUrl.value = "";
  renderedPreviewUrl.value = "";
  selectedRegion.value = -1;
  dialog.value = true;
}

function openEdit(item) {
  editing.value = true;
  editingId.value = item.id;
  form.value = {
    name: item.name,
    description: item.description || "",
    font_filename: item.font_filename,
    is_default: item.is_default,
    regions_json: JSON.parse(JSON.stringify(item.regions_json || [])),
  };
  previewUrl.value = `/api/v1/image/templates/${item.id}/preview`;
  renderedPreviewUrl.value = "";
  selectedRegion.value = -1;
  dialog.value = true;
}

function onFileChange(files) {
  const file = Array.isArray(files) ? files[0] : files;
  if (file) {
    previewUrl.value = URL.createObjectURL(file);
  } else {
    previewUrl.value = "";
  }
}

function updateRegion(updated) {
  const regions = [...form.value.regions_json];
  regions[selectedRegion.value] = updated;
  form.value.regions_json = regions;
}

function deleteRegion() {
  const regions = [...form.value.regions_json];
  regions.splice(selectedRegion.value, 1);
  form.value.regions_json = regions;
  selectedRegion.value = -1;
}

async function save() {
  saving.value = true;
  try {
    if (editing.value) {
      await api.updateImageTemplate(editingId.value, {
        name: form.value.name,
        description: form.value.description,
        font_filename: form.value.font_filename,
        is_default: form.value.is_default,
        regions_json: form.value.regions_json,
      });
    } else {
      const file = Array.isArray(imageFile.value) ? imageFile.value[0] : imageFile.value;
      if (!file) {
        notify("Please select an image file", "warning");
        saving.value = false;
        return;
      }
      const fd = new FormData();
      fd.append("name", form.value.name);
      fd.append("description", form.value.description || "");
      fd.append("font_filename", form.value.font_filename);
      fd.append("is_default", form.value.is_default);
      fd.append("regions_json", JSON.stringify(form.value.regions_json));
      fd.append("image", file);
      await api.createImageTemplate(fd);
    }
    dialog.value = false;
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
  saving.value = false;
}

async function deleteTemplate(id) {
  if (!await showConfirm("Delete Template", "Delete this template?")) return;
  try {
    await api.deleteImageTemplate(id);
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function doPreview() {
  if (!previewText.value) return;
  previewing.value = true;
  try {
    const params = { text: previewText.value };
    if (editingId.value) {
      params.template_id = editingId.value;
    } else {
      params.template_name = "alert";
    }
    renderedPreviewUrl.value = await api.previewImage(params);
  } catch (e) {
    notify("Preview failed: " + e.message, "error");
  }
  previewing.value = false;
}

function truncate(str, len = 30) {
  return str && str.length > len ? str.slice(0, len) + "…" : str;
}

onMounted(load);
</script>
