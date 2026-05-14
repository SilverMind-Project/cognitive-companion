<template>
  <v-dialog :model-value="modelValue" max-width="700" persistent @update:model-value="$emit('update:modelValue', $event)">
    <v-card>
      <v-card-title class="d-flex align-center">
        <v-icon class="mr-2" color="primary">mdi-package-down</v-icon>
        Import Rule
      </v-card-title>
      <v-card-text>
        <!-- Step 1: File selection -->
        <template v-if="step === 'select'">
          <div
            class="dropzone pa-8 text-center rounded-lg mb-4"
            :class="{ 'dropzone-drag': dragging }"
            @dragover.prevent="dragging = true"
            @dragleave.prevent="dragging = false"
            @drop.prevent="onDrop"
          >
            <v-icon size="48" color="primary" class="mb-2">mdi-cloud-upload</v-icon>
            <div class="text-body-1 mb-2">Drop a <code>.cc-rule.yaml</code> or <code>.cc-rule.json</code> file here</div>
            <div class="text-caption text-medium-emphasis mb-3">or</div>
            <v-btn variant="tonal" prepend-icon="mdi-file" @click="triggerFileInput">
              Choose File
            </v-btn>
            <input
              ref="fileInput"
              type="file"
              accept=".json,.yaml,.yml"
              class="d-none"
              @change="onFileSelected"
            />
          </div>
          <v-alert v-if="fileError" type="error" density="compact" class="mb-3">
            {{ fileError }}
          </v-alert>
        </template>

        <!-- Step 2: Preview / loading -->
        <template v-if="step === 'preview'">
          <div v-if="previewLoading" class="text-center py-6">
            <v-progress-circular indeterminate color="primary" class="mb-3" />
            <div class="text-body-1">Validating rule bundle...</div>
          </div>
          <template v-else-if="report">
            <!-- Status banner -->
            <v-alert
              :type="report.status === 'error' ? 'error' : report.status === 'warning' ? 'warning' : 'success'"
              density="compact"
              class="mb-4"
            >
              <template v-if="report.status === 'ok'">
                <strong>{{ report.rule_name }}</strong> is valid and ready to import.
              </template>
              <template v-else-if="report.status === 'warning'">
                <strong>{{ report.rule_name }}</strong> can be imported with warnings.
              </template>
              <template v-else>
                Import has errors that must be resolved before committing.
              </template>
            </v-alert>

            <!-- Rule summary -->
            <v-card variant="tonal" class="mb-4 pa-3">
              <div class="text-subtitle-2 mb-1">{{ report.rule_name }}</div>
              <div class="d-flex ga-4 text-caption text-medium-emphasis">
                <span>{{ bundle?.steps?.length || 0 }} steps</span>
                <span>{{ bundle?.contexts?.length || 0 }} contexts</span>
                <span>{{ bundle?.dependencies?.length || 0 }} dependencies</span>
                <span v-if="bundle?.source?.app_version">v{{ bundle.source.app_version }}</span>
              </div>
              <div v-if="bundle?.exported_by" class="text-caption text-medium-emphasis mt-1">
                Exported by {{ bundle.exported_by }}
              </div>
            </v-card>

            <!-- Step import results -->
            <div v-if="report.steps?.length" class="mb-4">
              <div class="text-caption font-weight-bold mb-2">Step Status</div>
              <div
                v-for="s in report.steps"
                :key="s.label"
                class="d-flex align-center ga-2 py-1"
              >
                <v-chip size="x-small" :color="stepStatusColor(s.status)">
                  {{ s.status }}
                </v-chip>
                <span class="text-body-2">{{ s.label }}</span>
                <span class="text-caption text-medium-emphasis">{{ s.step_type }}</span>
                <span v-if="s.description" class="text-caption text-medium-emphasis">— {{ s.description }}</span>
              </div>
            </div>

            <!-- Warnings -->
            <v-alert
              v-if="report.warnings?.length"
              type="warning"
              density="compact"
              variant="tonal"
              class="mb-3"
            >
              <div v-for="(w, i) in report.warnings" :key="i" class="text-caption">{{ w }}</div>
            </v-alert>

            <!-- Errors -->
            <v-alert
              v-if="report.errors?.length"
              type="error"
              density="compact"
              variant="tonal"
              class="mb-3"
            >
              <div v-for="(e, i) in report.errors" :key="i" class="text-caption">{{ e }}</div>
            </v-alert>

            <!-- Min version warning -->
            <v-alert
              v-if="report.min_app_version_required"
              type="info"
              density="compact"
              variant="tonal"
            >
              This bundle requires Cognitive Companion v{{ report.min_app_version_required }} or newer.
            </v-alert>
          </template>
        </template>

        <!-- Step 3: Success -->
        <template v-if="step === 'success'">
          <v-alert type="success" density="compact" class="mb-4">
            <strong>{{ report?.rule_name }}</strong> imported successfully.
          </v-alert>
        </template>
      </v-card-text>

      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="close">Cancel</v-btn>
        <v-btn
          v-if="step === 'preview' && report?.status !== 'error'"
          color="primary"
          :loading="importing"
          @click="commitImport"
        >
          Import
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "../../services/api.js";
import { useNotify } from "../../composables/useNotify.js";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
});

const emit = defineEmits(["update:modelValue", "imported"]);

const router = useRouter();
const { notify } = useNotify();

const step = ref("select");
const dragging = ref(false);
const fileInput = ref(null);
const fileError = ref("");
const bundle = ref(null);
const report = ref(null);
const previewLoading = ref(false);
const importing = ref(false);

function triggerFileInput() {
  fileInput.value?.click();
}

function stepStatusColor(status) {
  switch (status) {
    case "ok": return "success";
    case "migrated": return "info";
    case "warning": return "warning";
    case "error": return "error";
    default: return "grey";
  }
}

async function parseFile(file) {
  const text = await file.text();
  const ext = file.name.split(".").pop().toLowerCase();
  if (ext === "json") {
    return JSON.parse(text);
  }
  if (ext === "yaml" || ext === "yml") {
    // Simple YAML parsing for the basic bundle structure
    // A full YAML parser would be heavy; we accept JSON for now and show
    // a helpful message for YAML files
    throw new Error("YAML files are not yet supported in the browser. Please use JSON export format.");
  }
  throw new Error(`Unsupported file type: .${ext}. Please use .json files.`);
}

async function onDrop(e) {
  dragging.value = false;
  const file = e.dataTransfer?.files?.[0];
  if (file) await loadFile(file);
}

async function onFileSelected(e) {
  const file = e.target?.files?.[0];
  if (file) await loadFile(file);
}

async function loadFile(file) {
  fileError.value = "";
  try {
    bundle.value = await parseFile(file);
    await runPreview();
  } catch (e) {
    fileError.value = e.message || "Failed to read file.";
  }
}

async function runPreview() {
  step.value = "preview";
  previewLoading.value = true;
  try {
    report.value = await api.importRulePreview(bundle.value);
  } catch (e) {
    report.value = {
      status: "error",
      rule_name: bundle.value?.rule?.name || "Unknown",
      errors: [e.message || "Preview failed"],
      steps: [],
      warnings: [],
    };
  } finally {
    previewLoading.value = false;
  }
}

async function commitImport() {
  importing.value = true;
  try {
    const result = await api.importRule(bundle.value);
    report.value = result;
    if (result.rule_id) {
      step.value = "success";
      notify.success(`Imported "${result.rule_name}"`);
      emit("imported", result.rule_id);
      setTimeout(() => {
        router.push(`/admin/rules/${result.rule_id}`);
        close();
      }, 600);
    } else if (result.status === "error") {
      notify.error("Import failed: " + (result.errors?.[0] || "Unknown error"));
    }
  } catch (e) {
    notify.error("Import failed: " + (e.message || "Unknown error"));
  } finally {
    importing.value = false;
  }
}

function close() {
  step.value = "select";
  fileError.value = "";
  bundle.value = null;
  report.value = null;
  emit("update:modelValue", false);
}
</script>

<style scoped>
.dropzone {
  border: 2px dashed var(--cc-divider);
  border-radius: var(--cc-radius-lg);
  background: var(--cc-surface-2);
  transition: border-color 0.2s, background-color 0.2s;
  cursor: pointer;
}

.dropzone:hover,
.dropzone-drag {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.04);
}

code {
  font-family: var(--cc-font-mono);
  font-size: 13px;
  background: var(--cc-surface-3);
  padding: 2px 6px;
  border-radius: 4px;
}
</style>
