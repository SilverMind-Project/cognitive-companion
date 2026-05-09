<template>
  <div>
    <div class="d-flex align-center mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Tracking Cameras</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Manage RTSP cameras for the continuous tracking system.
        </div>
      </div>
      <v-spacer />
      <v-btn variant="tonal" class="mr-2" prepend-icon="mdi-connection" @click="openTestConnect">
        Test RTSP
      </v-btn>
      <v-btn color="primary" variant="flat" prepend-icon="mdi-plus" @click="openCreate">
        Add Camera
      </v-btn>
    </div>

    <v-card class="glass-card">
      <v-data-table :headers="headers" :items="cameras" :loading="loading" item-value="id">
        <template #item.enabled="{ item }">
          <v-chip :color="item.enabled ? 'success' : 'default'" size="small">
            {{ item.enabled ? "Active" : "Disabled" }}
          </v-chip>
        </template>
        <template #item.has_homography="{ item }">
          <v-icon
            :color="item.has_homography ? 'success' : 'warning'"
            :icon="item.has_homography ? 'mdi-check-circle' : 'mdi-alert-circle-outline'"
            size="small"
          />
        </template>
        <template #item.privacy_zone_count="{ item }">
          <v-chip v-if="item.privacy_zone_count > 0" size="small" color="primary" variant="tonal">
            {{ item.privacy_zone_count }}
          </v-chip>
          <span v-else class="text-medium-emphasis">0</span>
        </template>
        <template #item.actions="{ item }">
          <v-btn icon="mdi-image-outline" size="small" variant="text" title="Snapshot" @click="viewSnapshot(item.id)" />
          <v-btn icon="mdi-pencil" size="small" variant="text" @click="openEdit(item)" />
          <v-btn icon="mdi-delete" size="small" variant="text" color="error" @click="confirmDelete(item)" />
        </template>
      </v-data-table>
    </v-card>

    <!-- Add / Edit dialog -->
    <v-dialog v-model="dialog" max-width="520" persistent>
      <v-card>
        <v-card-title>{{ editing ? "Edit Camera" : "Add Camera" }}</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="form.id"
            label="Camera ID"
            variant="outlined"
            class="mb-3"
            :disabled="editing"
            hint="Stable slug, e.g. kitchen-cam-1"
            persistent-hint
          />
          <v-text-field v-model="form.name" label="Display Name" variant="outlined" class="mb-3" />
          <v-text-field
            v-model="form.rtsp_url"
            label="RTSP URL"
            variant="outlined"
            class="mb-3"
            placeholder="rtsp://192.168.1.10/stream"
          />
          <v-text-field v-model="form.location" label="Location (optional)" variant="outlined" class="mb-3" />
          <v-switch v-model="form.enabled" label="Enabled" color="primary" class="mb-3" />
          <v-divider class="mb-3" />
          <div class="text-subtitle-2 font-weight-medium mb-2">Face Identification</div>
          <v-switch
            v-model="form.face_id_enabled"
            label="Enable face identification"
            color="primary"
            hint="Disable for top-down or surveillance cameras where faces are never visible"
            persistent-hint
            density="compact"
            class="mb-2"
          />
          <v-text-field
            v-if="form.face_id_enabled"
            v-model.number="form.face_id_min_confidence"
            label="Min confidence (optional)"
            variant="outlined"
            type="number"
            min="0"
            max="1"
            step="0.05"
            hint="Higher values require stronger face matches. Leave empty for system default (0.4)."
            persistent-hint
            density="compact"
          />
        </v-card-text>
        <v-card-actions class="px-6 pb-4">
          <v-spacer />
          <v-btn variant="text" :disabled="saving" @click="dialog = false">Cancel</v-btn>
          <v-btn color="primary" variant="flat" :loading="saving" @click="saveCamera">
            {{ editing ? "Update" : "Create" }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Test-connect dialog -->
    <v-dialog v-model="testDialog" max-width="480">
      <v-card>
        <v-card-title>Test RTSP Connection</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="testUrl"
            label="RTSP URL"
            variant="outlined"
            placeholder="rtsp://192.168.1.10/stream"
          />
          <v-alert v-if="testResult" :type="testResult.ok ? 'success' : 'error'" class="mt-2" density="compact">
            {{ testResult.message }}
          </v-alert>
        </v-card-text>
        <v-card-actions class="px-6 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="testDialog = false">Close</v-btn>
          <v-btn color="primary" variant="flat" :loading="testing" @click="runTestConnect">
            Test
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Snapshot dialog -->
    <v-dialog v-model="snapshotDialog" max-width="800">
      <v-card>
        <v-card-title>Camera Snapshot</v-card-title>
        <v-card-text class="pa-0">
          <v-img v-if="snapshotUrl" :src="snapshotUrl" cover />
          <div v-else class="d-flex align-center justify-center pa-8">
            <v-progress-circular indeterminate />
          </div>
        </v-card-text>
        <v-card-actions class="px-6 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="closeSnapshot">Close</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete confirm -->
    <v-dialog v-model="confirmDialog" max-width="400">
      <v-card rounded="xl">
        <v-card-title>{{ confirmTitle }}</v-card-title>
        <v-card-text>{{ confirmText }}</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="onCancel">Cancel</v-btn>
          <v-btn color="error" variant="flat" @click="onConfirm">Delete</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snack" :color="snackColor" timeout="3500">{{ snackText }}</v-snackbar>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from "vue";
import { cts } from "../../services/cts.js";
import { useNotify } from "../../composables/useNotify.js";
import { useConfirm } from "../../composables/useConfirm.js";

const { snack, snackText, snackColor, notify } = useNotify();
const { confirmDialog, confirmTitle, confirmText, showConfirm, onConfirm, onCancel } = useConfirm();

const cameras = ref([]);
const loading = ref(false);
const dialog = ref(false);
const editing = ref(false);
const saving = ref(false);
const editId = ref(null);

const testDialog = ref(false);
const testUrl = ref("");
const testResult = ref(null);
const testing = ref(false);

const snapshotDialog = ref(false);
const snapshotUrl = ref(null);

const headers = [
  { title: "ID", key: "id" },
  { title: "Name", key: "name" },
  { title: "Location", key: "location" },
  { title: "Status", key: "enabled", width: 100 },
  { title: "Calibrated", key: "has_homography", width: 110 },
  { title: "Privacy Zones", key: "privacy_zone_count", width: 130 },
  { title: "", key: "actions", sortable: false, align: "end" },
];

const emptyForm = () => ({
  id: "",
  name: "",
  rtsp_url: "",
  location: "",
  enabled: true,
  face_id_enabled: true,
  face_id_min_confidence: null,
});

const form = ref(emptyForm());

async function loadCameras() {
  loading.value = true;
  try {
    cameras.value = await cts.getCameras();
  } catch (e) {
    notify(e.message, "error");
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  editing.value = false;
  editId.value = null;
  form.value = emptyForm();
  dialog.value = true;
}

function openEdit(cam) {
  editing.value = true;
  editId.value = cam.id;
  form.value = {
    id: cam.id,
    name: cam.name,
    rtsp_url: cam.rtsp_url,
    location: cam.location || "",
    enabled: cam.enabled,
    face_id_enabled: cam.face_id_enabled !== false,
    face_id_min_confidence: cam.face_id_min_confidence ?? null,
  };
  dialog.value = true;
}

async function saveCamera() {
  saving.value = true;
  try {
    if (editing.value) {
      const { id, ...patch } = form.value;
      await cts.updateCamera(editId.value, patch);
      notify("Camera updated");
    } else {
      await cts.createCamera(form.value);
      notify("Camera created");
    }
    dialog.value = false;
    await loadCameras();
  } catch (e) {
    notify(e.message, "error");
  } finally {
    saving.value = false;
  }
}

async function confirmDelete(cam) {
  const ok = await showConfirm(
    `Delete "${cam.name}"?`,
    "This will permanently remove the camera and its calibration data."
  );
  if (ok) deleteCamera(cam.id);
}

async function deleteCamera(id) {
  try {
    await cts.deleteCamera(id);
    notify("Camera deleted");
    await loadCameras();
  } catch (e) {
    notify(e.message, "error");
  }
}

function openTestConnect() {
  testUrl.value = "";
  testResult.value = null;
  testDialog.value = true;
}

async function runTestConnect() {
  if (!testUrl.value) return;
  testing.value = true;
  testResult.value = null;
  try {
    const r = await cts.testConnect(testUrl.value);
    testResult.value = { ok: true, message: r.message || "Connection successful" };
  } catch (e) {
    testResult.value = { ok: false, message: e.message };
  } finally {
    testing.value = false;
  }
}

async function viewSnapshot(id) {
  snapshotUrl.value = null;
  snapshotDialog.value = true;
  try {
    snapshotUrl.value = await cts.getSnapshot(id);
  } catch (e) {
    snapshotDialog.value = false;
    notify(e.message, "error");
  }
}

function closeSnapshot() {
  snapshotDialog.value = false;
  if (snapshotUrl.value) {
    URL.revokeObjectURL(snapshotUrl.value);
    snapshotUrl.value = null;
  }
}

onMounted(loadCameras);
onBeforeUnmount(() => {
  if (snapshotUrl.value) URL.revokeObjectURL(snapshotUrl.value);
});
</script>
