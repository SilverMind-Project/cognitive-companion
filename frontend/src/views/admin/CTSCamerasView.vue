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
          <div class="d-flex align-center ga-1">
            <v-icon
              :color="item.has_homography ? 'success' : 'warning'"
              :icon="item.has_homography ? 'mdi-check-circle' : 'mdi-alert-circle-outline'"
              size="small"
            />
            <v-chip
              v-if="item.needs_recalibration"
              color="warning"
              size="x-small"
              variant="tonal"
              prepend-icon="mdi-camera-off"
              :title="
                item.drift_reason
                  ? `Drift: ${item.drift_reason}`
                  : 'Camera drift detected — recalibration needed'
              "
            >
              Drift
            </v-chip>
          </div>
        </template>
        <template #item.privacy_zone_count="{ item }">
          <v-chip v-if="item.privacy_zone_count > 0" size="small" color="primary" variant="tonal">
            {{ item.privacy_zone_count }}
          </v-chip>
          <span v-else class="text-medium-emphasis">0</span>
        </template>
        <template #item.actions="{ item }">
          <v-btn
            icon="mdi-image-outline"
            size="small"
            variant="text"
            title="Snapshot"
            @click="viewSnapshot(item.id)"
          />
          <v-btn
            icon="mdi-pencil"
            size="small"
            variant="text"
            color="primary"
            @click="openEdit(item)"
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

    <!-- Add / Edit dialog -->
    <v-dialog v-model="dialog" max-width="520" persistent>
      <v-card>
        <DialogHeader
          icon="mdi-cctv"
          :label="editing ? 'Edit' : 'Create New'"
          :title="editing ? 'Camera' : 'Camera'"
          @close="dialog = false"
        />
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
          <v-autocomplete
            v-if="!useCustomName"
            v-model="form.room_id"
            :items="rooms"
            item-title="name"
            item-value="id"
            label="Room"
            variant="outlined"
            class="mb-2"
            clearable
          />
          <div class="d-flex align-center mb-2">
            <v-switch
              v-model="useCustomName"
              label="Custom name"
              density="compact"
              hide-details
              color="secondary"
            />
          </div>
          <v-text-field
            v-if="useCustomName"
            v-model="form.room_name"
            label="Custom location name"
            variant="outlined"
            class="mb-3"
          />
          <v-switch v-model="form.enabled" label="Enabled" color="primary" class="mb-3" />
          <v-radio-group
            v-model="form.role"
            label="Camera role"
            class="mb-3"
            density="compact"
            inline
          >
            <v-radio label="Surveillance" value="surveillance" />
            <v-radio label="Face-capable" value="face_capable" />
            <v-radio label="Mixed" value="mixed" />
          </v-radio-group>
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
          <v-divider class="mb-3" />
          <div class="text-subtitle-2 font-weight-medium mb-1">Physical Parameters</div>
          <div class="text-caption text-medium-emphasis mb-3">
            Optional. Improves automatic homography calibration accuracy.
          </div>
          <v-text-field
            v-model.number="form.horizontal_fov_deg"
            label="Horizontal FOV (degrees)"
            variant="outlined"
            type="number"
            min="20"
            max="180"
            step="1"
            density="compact"
            class="mb-3"
            clearable
            hint="Enter your camera's horizontal field of view (HFOV). If the spec sheet lists diagonal FOV, multiply by ~0.8 for 16:9 sensors. Typical range: 60°–130°. Examples: Reolink 823A ≈ 87°, Hikvision DS-2CD series ≈ 103°, Wyze Cam v3 ≈ 110°."
            persistent-hint
          />
          <v-row dense class="mb-1">
            <v-col cols="6">
              <v-text-field
                v-model.number="form.mounting_height_m"
                label="Mounting height (m)"
                variant="outlined"
                type="number"
                min="0.1"
                max="10"
                step="0.1"
                density="compact"
                clearable
                hint="Camera lens height above the floor."
                persistent-hint
              />
            </v-col>
            <v-col cols="6">
              <v-text-field
                v-model.number="form.tilt_deg"
                label="Tilt (°, must be ≤ 0)"
                variant="outlined"
                type="number"
                min="-90"
                max="0"
                step="1"
                density="compact"
                clearable
                hint="0 = horizontal, −90 = pointing straight down."
                persistent-hint
              />
            </v-col>
          </v-row>
        </v-card-text>
        <DialogFooter
          hint="Cameras feed the continuous tracking system for presence and activity detection."
          :confirm-label="editing ? 'Update' : 'Create'"
          :confirm-loading="saving"
          @cancel="dialog = false"
          @confirm="saveCamera"
        />
      </v-card>
    </v-dialog>

    <!-- Test-connect dialog -->
    <v-dialog v-model="testDialog" max-width="480">
      <v-card>
        <DialogHeader
          icon="mdi-connection"
          label="Test"
          title="RTSP Connection"
          @close="testDialog = false"
        />
        <v-card-text>
          <v-text-field
            v-model="testUrl"
            label="RTSP URL"
            variant="outlined"
            placeholder="rtsp://192.168.1.10/stream"
          />
          <v-alert
            v-if="testResult"
            :type="testResult.ok ? 'success' : 'error'"
            class="mt-2"
            density="compact"
          >
            {{ testResult.message }}
          </v-alert>
        </v-card-text>
        <DialogFooter
          cancel-label="Close"
          confirm-label="Test"
          :confirm-loading="testing"
          @cancel="testDialog = false"
          @confirm="runTestConnect"
        />
      </v-card>
    </v-dialog>

    <!-- Snapshot dialog -->
    <v-dialog v-model="snapshotDialog" max-width="800">
      <v-card>
        <DialogHeader
          icon="mdi-image-outline"
          label="Camera"
          title="Snapshot"
          @close="closeSnapshot"
        />
        <v-card-text class="pa-0">
          <v-img v-if="snapshotUrl" :src="displaySrc(snapshotUrl)" cover />
          <div v-else class="d-flex align-center justify-center pa-8">
            <v-progress-circular indeterminate />
          </div>
        </v-card-text>
        <v-divider />
        <v-card-actions class="px-6 py-3">
          <BlurToggle class="mx-3" />
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
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from "vue";
import { cts } from "../../services/cts.js";
import { api } from "../../services/api.js";
import { useNotify } from "../../composables/useNotify.js";
import { useConfirm } from "../../composables/useConfirm.js";
import { useBlurMode, useDisplaySrc } from "../../composables/useBlurMode.js";
import DialogHeader from "../../components/common/DialogHeader.vue";
import DialogFooter from "../../components/common/DialogFooter.vue";
import BlurToggle from "../../components/cts/BlurToggle.vue";

const { notify } = useNotify();
const { confirmDialog, confirmTitle, confirmText, showConfirm, onConfirm, onCancel } = useConfirm();
const { blurMode } = useBlurMode();
const { displaySrc } = useDisplaySrc(blurMode);

const cameras = ref([]);
const rooms = ref([]);
const useCustomName = ref(false);
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
  { title: "Location", key: "room_name" },
  { title: "Status", key: "enabled", width: 100 },
  { title: "Role", key: "role", width: 130 },
  { title: "Calibrated", key: "has_homography", width: 110 },
  { title: "Privacy Zones", key: "privacy_zone_count", width: 130 },
  { title: "", key: "actions", sortable: false, align: "end" },
];

const emptyForm = () => ({
  id: "",
  name: "",
  rtsp_url: "",
  room_name: "",
  room_id: null,
  enabled: true,
  face_id_enabled: true,
  face_id_min_confidence: null,
  role: "surveillance",
  horizontal_fov_deg: null,
  mounting_height_m: null,
  tilt_deg: null,
});

const form = ref(emptyForm());

async function loadRooms() {
  try {
    rooms.value = await api.getRooms();
  } catch (e) {
    notify(e.message, "error");
  }
}

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
  useCustomName.value = false;
  dialog.value = true;
}

function openEdit(cam) {
  editing.value = true;
  editId.value = cam.id;
  const hasRoom = cam.room_id != null;
  useCustomName.value = !hasRoom && !!cam.room_name && !(cam.room || {}).id;
  form.value = {
    id: cam.id,
    name: cam.name,
    rtsp_url: cam.rtsp_url,
    room_name: cam.room_name || "",
    room_id: cam.room_id ?? null,
    enabled: cam.enabled,
    face_id_enabled: cam.face_id_enabled !== false,
    face_id_min_confidence: cam.face_id_min_confidence ?? null,
    role: cam.role || "surveillance",
    horizontal_fov_deg: cam.horizontal_fov_deg ?? null,
    mounting_height_m: cam.mounting_height_m ?? null,
    tilt_deg: cam.tilt_deg ?? null,
  };
  dialog.value = true;
}

async function saveCamera() {
  saving.value = true;
  try {
    const payload = { ...form.value };
    if (useCustomName.value) {
      payload.room_id = null;
      if (!payload.room_name?.trim()) {
        notify("Enter a custom location name or choose a room", "error");
        return;
      }
    } else {
      if (!payload.room_id) {
        notify("Choose a room or enable Custom name", "error");
        return;
      }
      // When a room is selected, clear room_name so the backend denormalises it.
      payload.room_name = "";
    }
    if (editing.value) {
      const { id: _id, ...patch } = payload;
      await cts.updateCamera(editId.value, patch);
      notify("Camera updated");
    } else {
      await cts.createCamera(payload);
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
    "This will permanently remove the camera and its calibration data.",
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

onMounted(() => {
  loadCameras();
  loadRooms();
});
onBeforeUnmount(() => {
  if (snapshotUrl.value) URL.revokeObjectURL(snapshotUrl.value);
});
</script>
