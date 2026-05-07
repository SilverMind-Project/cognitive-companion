<template>
  <div>
    <!-- ── Page Header ──────────────────────────────────────────────────── -->
    <div class="d-flex align-center mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">E-Ink Templates</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Layouts and regions used to render text onto e-ink displays.
        </div>
      </div>
      <v-spacer />
      <v-btn variant="tonal" prepend-icon="mdi-refresh" class="mr-2" @click="load">Refresh</v-btn>
      <v-btn color="primary" variant="flat" prepend-icon="mdi-plus" @click="openCreate">New Template</v-btn>
    </div>

    <!-- ── Device Status Panel ─────────────────────────────────────────── -->
    <v-card class="mb-4">
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

    <!-- ── Templates Table ─────────────────────────────────────────────── -->
    <v-card class="glass-card">
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
          <v-btn
            icon="mdi-delete"
            size="small"
            variant="text"
            color="error"
            @click.stop="deleteTemplate(item.id)"
          />
        </template>
      </v-data-table>
    </v-card>

    <!-- ── Create / Edit Dialog ────────────────────────────────────────── -->
    <v-dialog
      v-model="dialog"
      width="1020"
      max-width="96vw"
      :fullscreen="$vuetify.display.smAndDown"
      persistent
    >
      <v-card class="eink-dialog-card d-flex flex-column">
        <!-- Header -->
        <div class="eink-dialog-header px-6 py-4 d-flex align-center">
          <v-avatar size="40" class="eink-dialog-icon mr-3">
            <v-icon color="white">mdi-monitor</v-icon>
          </v-avatar>
          <div class="flex-grow-1">
            <div class="text-overline text-medium-emphasis">E-Ink Template</div>
            <div class="text-h6 font-weight-bold tracking-tight">
              {{ editing ? form.name || "Edit Template" : "New Template" }}
            </div>
          </div>
          <v-btn icon="mdi-close" variant="text" @click="dialog = false" />
        </div>

        <v-divider />

        <!-- Body: vertical tabs + content -->
        <div class="eink-dialog-body d-flex flex-grow-1 overflow-hidden">
          <!-- Left nav tabs -->
          <v-tabs
            v-model="activeTab"
            direction="vertical"
            color="primary"
            class="eink-dialog-tabs flex-shrink-0"
          >
            <v-tab value="settings" class="justify-start" prepend-icon="mdi-cog">
              Settings
            </v-tab>
            <v-tab value="regions" class="justify-start" prepend-icon="mdi-vector-rectangle">
              Regions
            </v-tab>
            <v-tab value="preview" class="justify-start" prepend-icon="mdi-eye">
              Preview
            </v-tab>
          </v-tabs>

          <v-divider vertical />

          <!-- Tab content -->
          <div class="eink-dialog-content flex-grow-1">
            <v-window v-model="activeTab">

              <!-- ── Settings Tab ────────────────────────────────────────── -->
              <v-window-item value="settings" class="pa-6">
                <v-text-field
                  v-model="form.name"
                  label="Name"
                  variant="outlined"
                  density="comfortable"
                  class="mb-4"
                  hint="Unique identifier for this template"
                  persistent-hint
                />
                <v-textarea
                  v-model="form.description"
                  label="Description"
                  variant="outlined"
                  rows="2"
                  class="mb-4"
                />
                <v-select
                  v-model="form.font_filename"
                  :items="fonts"
                  label="Default Font"
                  variant="outlined"
                  density="comfortable"
                  prepend-inner-icon="mdi-format-font"
                  class="mb-4"
                />
                <v-checkbox
                  v-model="form.is_default"
                  label="Set as default template"
                  density="comfortable"
                  hide-details
                  class="mb-5"
                />

                <v-divider class="mb-4" />

                <!-- Background Image -->
                <div class="text-subtitle-2 font-weight-medium mb-2">Background Image</div>

                <!-- Create mode: required upload -->
                <v-file-input
                  v-if="!editing"
                  v-model="imageFile"
                  label="Upload image (800 × 480 recommended)"
                  accept="image/*"
                  variant="outlined"
                  density="comfortable"
                  prepend-icon="mdi-image-plus"
                  show-size
                  @update:model-value="onCreateImageChange"
                />

                <!-- Edit mode: optional replace -->
                <template v-else>
                  <v-img
                    v-if="previewUrl"
                    :src="previewUrl"
                    max-height="160"
                    class="rounded-lg mb-3"
                    cover
                  />
                  <v-file-input
                    v-model="newImageFile"
                    label="Replace background image (optional)"
                    accept="image/*"
                    variant="outlined"
                    density="comfortable"
                    prepend-icon="mdi-image-edit"
                    show-size
                    clearable
                    @update:model-value="onEditImageChange"
                  />
                </template>
              </v-window-item>

              <!-- ── Regions Tab ─────────────────────────────────────────── -->
              <v-window-item value="regions" class="pa-4">
                <v-row>
                  <v-col cols="12" md="7">
                    <BoundingBoxCanvas
                      ref="bboxCanvas"
                      :image-url="previewUrl"
                      :regions="form.regions_json"
                      :selected-index="selectedRegion"
                      @update:regions="form.regions_json = $event"
                      @select-region="selectedRegion = $event"
                    />
                    <p class="text-caption text-medium-emphasis mt-2">
                      Drag to create a region · Click to select · Drag selected region to move
                    </p>
                  </v-col>
                  <v-col cols="12" md="5">
                    <template v-if="selectedRegion >= 0 && form.regions_json[selectedRegion]">
                      <RegionEditor
                        :region="form.regions_json[selectedRegion]"
                        @update:region="updateRegion"
                        @delete="deleteRegion"
                      />
                    </template>
                    <div v-else class="d-flex flex-column align-center justify-center pa-6 text-center" style="min-height: 200px">
                      <v-icon size="40" class="text-medium-emphasis mb-2">mdi-cursor-default-click</v-icon>
                      <span class="text-body-2 text-medium-emphasis">
                        Draw a region on the canvas<br />or click an existing one to edit it.
                      </span>
                    </div>
                  </v-col>
                </v-row>
              </v-window-item>

              <!-- ── Preview Tab ─────────────────────────────────────────── -->
              <v-window-item value="preview" class="pa-6">
                <v-textarea
                  v-model="previewText"
                  label="Preview Text"
                  variant="outlined"
                  density="comfortable"
                  rows="3"
                  hint="Use Enter for explicit line breaks (requires Multi-line enabled on the region)"
                  persistent-hint
                  class="mb-4"
                />
                <v-btn
                  block
                  variant="flat"
                  color="primary"
                  prepend-icon="mdi-eye"
                  :loading="previewing"
                  @click="doPreview"
                >
                  Render Preview
                </v-btn>

                <template v-if="renderedPreviewUrl">
                  <v-divider class="my-4" />
                  <div class="text-caption text-medium-emphasis mb-2">Rendered output</div>
                  <v-img
                    :src="renderedPreviewUrl"
                    class="rounded-lg"
                    max-height="300"
                    cover
                  />
                </template>

                <v-empty-state
                  v-else
                  icon="mdi-image-off-outline"
                  text="Click Render Preview to see how text will look on this template."
                  class="mt-6"
                />
              </v-window-item>

            </v-window>
          </div>
        </div>

        <v-divider />

        <!-- Footer actions -->
        <v-card-actions class="px-6 py-3">
          <v-spacer />
          <v-btn variant="text" @click="dialog = false">Cancel</v-btn>
          <v-btn color="primary" variant="flat" :loading="saving" @click="save">
            {{ editing ? "Update" : "Create" }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Snackbar ────────────────────────────────────────────────────── -->
    <v-snackbar v-model="snack" :color="snackColor" timeout="3000">{{ snackText }}</v-snackbar>

    <!-- ── Confirm Dialog ─────────────────────────────────────────────── -->
    <v-dialog v-model="confirmDialog" max-width="400">
      <v-card>
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
import { ref, watch, onMounted } from "vue";
import { api } from "../../services/api.js";
import BoundingBoxCanvas from "../../components/eink/BoundingBoxCanvas.vue";
import RegionEditor from "../../components/eink/RegionEditor.vue";
import { useNotify } from "../../composables/useNotify.js";
import { useConfirm } from "../../composables/useConfirm.js";

const { snack, snackText, snackColor, notify } = useNotify();
const { confirmDialog, confirmTitle, confirmText, showConfirm, onConfirm, onCancel } =
  useConfirm();

// ── State ────────────────────────────────────────────────────────────────────

const templates = ref([]);
const states = ref([]);
const fonts = ref([]);
const loading = ref(false);

// Dialog state
const dialog = ref(false);
const activeTab = ref("settings");
const editing = ref(false);
const saving = ref(false);
const editingId = ref(null);
const selectedRegion = ref(-1);

// Image file refs
const imageFile = ref(null);     // Create mode: new template image
const newImageFile = ref(null);  // Edit mode: replacement image
const bboxCanvas = ref(null);    // BoundingBoxCanvas component ref

// URLs
const previewUrl = ref("");          // Canvas background (always an object URL or "")
const previewText = ref("Hello, this is a sample notification message.");
const renderedPreviewUrl = ref("");
const previewing = ref(false);

// Track object URLs we created so we can revoke them and avoid memory leaks.
let _ownedPreviewUrl = "";
let _ownedRenderedUrl = "";

function setPreviewUrl(url) {
  if (_ownedPreviewUrl) URL.revokeObjectURL(_ownedPreviewUrl);
  _ownedPreviewUrl = url;
  previewUrl.value = url;
}

function setRenderedPreviewUrl(url) {
  if (_ownedRenderedUrl) URL.revokeObjectURL(_ownedRenderedUrl);
  _ownedRenderedUrl = url;
  renderedPreviewUrl.value = url;
}

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

// When the user switches to the Regions tab, the BoundingBoxCanvas wrapper
// transitions from hidden (clientWidth = 0) to visible. Notify the canvas so
// it can re-measure and redraw correctly.
watch(activeTab, (tab) => {
  if (tab === "regions") {
    bboxCanvas.value?.activate();
  }
});

// ── Data loading ─────────────────────────────────────────────────────────────

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

// ── Dialog openers ───────────────────────────────────────────────────────────

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
  newImageFile.value = null;
  setPreviewUrl("");
  setRenderedPreviewUrl("");
  selectedRegion.value = -1;
  activeTab.value = "settings";
  dialog.value = true;
}

async function openEdit(item) {
  editing.value = true;
  editingId.value = item.id;
  form.value = {
    name: item.name,
    description: item.description || "",
    font_filename: item.font_filename,
    is_default: item.is_default,
    regions_json: JSON.parse(JSON.stringify(item.regions_json || [])),
  };
  newImageFile.value = null;
  setPreviewUrl("");
  setRenderedPreviewUrl("");
  selectedRegion.value = -1;
  activeTab.value = "settings";
  dialog.value = true;
  // Fetch the template background image with auth and set as object URL.
  try {
    setPreviewUrl(await api.getImageTemplatePreview(item.id));
  } catch (e) {
    console.error("Failed to load template preview:", e);
  }
}

// ── Image file handlers ──────────────────────────────────────────────────────

function onCreateImageChange(files) {
  const file = Array.isArray(files) ? files[0] : files;
  setPreviewUrl(file ? URL.createObjectURL(file) : "");
}

async function onEditImageChange(files) {
  const file = Array.isArray(files) ? files[0] : files;
  if (file) {
    setPreviewUrl(URL.createObjectURL(file));
  } else {
    // Restore the saved template image when the file input is cleared.
    setPreviewUrl("");
    if (editingId.value) {
      try {
        setPreviewUrl(await api.getImageTemplatePreview(editingId.value));
      } catch (e) {
        console.error("Failed to restore template preview:", e);
      }
    }
  }
}

// ── Region operations ────────────────────────────────────────────────────────

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

// ── Save ─────────────────────────────────────────────────────────────────────

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

      // Upload replacement background image if one was selected
      const replaceFile = Array.isArray(newImageFile.value)
        ? newImageFile.value[0]
        : newImageFile.value;
      if (replaceFile) {
        const fd = new FormData();
        fd.append("image", replaceFile);
        await api.updateImageTemplateImage(editingId.value, fd);
      }
    } else {
      const file = Array.isArray(imageFile.value) ? imageFile.value[0] : imageFile.value;
      if (!file) {
        notify("Please select a background image", "warning");
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

// ── Delete ───────────────────────────────────────────────────────────────────

async function deleteTemplate(id) {
  if (!(await showConfirm("Delete Template", "Delete this template? This cannot be undone.")))
    return;
  try {
    await api.deleteImageTemplate(id);
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

// ── Preview ──────────────────────────────────────────────────────────────────

async function doPreview() {
  if (!previewText.value.trim()) return;
  previewing.value = true;
  try {
    const fd = new FormData();
    fd.append("text", previewText.value);
    fd.append("regions_json", JSON.stringify(form.value.regions_json));
    fd.append("font_filename", form.value.font_filename);

    if (editing.value) {
      // Use replacement image if selected, otherwise the stored template
      const replaceFile = Array.isArray(newImageFile.value)
        ? newImageFile.value[0]
        : newImageFile.value;
      if (replaceFile) {
        fd.append("image", replaceFile);
      } else {
        fd.append("template_id", editingId.value);
      }
    } else {
      // New template: use the locally uploaded image
      const file = Array.isArray(imageFile.value) ? imageFile.value[0] : imageFile.value;
      if (file) {
        fd.append("image", file);
      }
      // If no image yet, backend falls back to default template
    }

    setRenderedPreviewUrl(await api.previewImageForm(fd));
  } catch (e) {
    notify("Preview failed: " + e.message, "error");
  }
  previewing.value = false;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function truncate(str, len = 30) {
  return str && str.length > len ? str.slice(0, len) + "…" : str;
}

onMounted(load);
</script>

<style scoped>
.tracking-tight {
  letter-spacing: -0.018em;
}

/* ── Dialog shell ────────────────────────────────────────────────────────── */
.eink-dialog-card {
  height: 88vh;
  max-height: 880px;
  border-radius: 24px !important;
  overflow: hidden;
}

.eink-dialog-header {
  background: linear-gradient(
    135deg,
    rgba(10, 132, 255, 0.08) 0%,
    rgba(94, 92, 230, 0.04) 100%
  );
  flex-shrink: 0;
}

.eink-dialog-icon {
  background: linear-gradient(135deg, #0a84ff 0%, #5e5ce6 60%, #bf5af2 100%);
}

.eink-dialog-body {
  min-height: 0; /* Required for flex children to shrink */
}

/* ── Left tabs ───────────────────────────────────────────────────────────── */
.eink-dialog-tabs {
  width: 180px;
  background-color: var(--cc-bg-elevated, rgba(0, 0, 0, 0.02));
  padding-top: 12px;
}

.eink-dialog-tabs :deep(.v-tab) {
  justify-content: flex-start !important;
  padding-inline: 20px !important;
  border-radius: 0;
  font-weight: 500;
  height: 44px;
}

/* ── Scrollable content ──────────────────────────────────────────────────── */
.eink-dialog-content {
  overflow-y: auto;
  min-width: 0;
}

/* Prevent Vuetify's v-window slide transition from clipping floating labels */
.eink-dialog-content :deep(.v-window),
.eink-dialog-content :deep(.v-window__container) {
  overflow: visible !important;
}
</style>
