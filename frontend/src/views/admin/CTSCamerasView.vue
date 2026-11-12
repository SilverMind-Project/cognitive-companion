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

    <!-- Add / Edit dialog: large, sectioned (one concern per section, no scrolling) -->
    <AppDialog
      v-model="dialog"
      v-model:section="activeSection"
      size="lg"
      persistent
      icon="mdi-cctv"
      :label="editing ? 'Edit Camera' : 'Create New Camera'"
      :title="editing ? form.name || form.id : 'Camera'"
      :sections="cameraSections"
      hint="Cameras feed the continuous tracking system for presence and activity detection."
      :confirm-label="editing ? 'Update' : 'Create'"
      :confirm-loading="saving"
      @confirm="saveCamera"
    >
      <template #section-general>
        <v-row dense>
          <v-col cols="12" sm="6">
            <v-text-field
              v-model="form.id"
              label="Camera ID"
              :disabled="editing"
              :error-messages="fieldErrors.id"
              hint="Stable slug, e.g. kitchen-cam-1"
              persistent-hint
            />
          </v-col>
          <v-col cols="12" sm="6">
            <v-text-field v-model="form.name" label="Display Name" />
          </v-col>
        </v-row>
        <v-row dense align="center">
          <v-col cols="12" sm="9">
            <v-text-field
              v-model="form.rtsp_url"
              label="RTSP URL"
              placeholder="rtsp://192.168.1.10/stream"
              @update:model-value="formProbe = null"
            />
          </v-col>
          <v-col cols="12" sm="3">
            <v-btn
              block
              variant="tonal"
              prepend-icon="mdi-connection"
              :loading="formProbing"
              :disabled="!form.rtsp_url"
              @click="probeFormUrl"
            >
              Test
            </v-btn>
          </v-col>
        </v-row>
        <v-alert
          v-if="formProbe"
          :type="formProbe.ok ? 'success' : 'error'"
          variant="tonal"
          density="compact"
          class="mb-3"
        >
          {{ formProbe.message }}
        </v-alert>
        <v-row dense align="center">
          <v-col cols="12" sm="8">
            <v-autocomplete
              v-if="!useCustomName"
              v-model="form.room_id"
              :items="rooms"
              item-title="name"
              item-value="id"
              label="Room"
              :error-messages="fieldErrors.location"
              clearable
            />
            <v-text-field
              v-else
              v-model="form.room_name"
              label="Custom location name"
              :error-messages="fieldErrors.location"
            />
          </v-col>
          <v-col cols="12" sm="4">
            <v-switch
              v-model="useCustomName"
              label="Custom name"
              density="compact"
              hide-details
              color="secondary"
            />
          </v-col>
        </v-row>
        <v-switch
          v-model="form.enabled"
          label="Enabled"
          hint="A disabled camera keeps its configuration but is not ingested."
          persistent-hint
        />
      </template>

      <template #section-identity>
        <div class="text-subtitle-2 font-weight-medium mb-1">Camera role</div>
        <v-radio-group v-model="form.role" inline hide-details class="mb-1">
          <v-radio
            v-for="option in ROLE_OPTIONS"
            :key="option.value"
            :label="option.title"
            :value="option.value"
          />
        </v-radio-group>
        <div class="text-caption text-medium-emphasis mb-5">{{ roleDescription }}</div>
        <v-switch
          v-model="form.face_id_enabled"
          label="Enable face identification"
          hint="Disable for top-down or surveillance cameras where faces are never visible"
          persistent-hint
          class="mb-4"
        />
        <v-alert
          v-if="form.face_id_enabled && form.role === 'surveillance'"
          type="info"
          variant="tonal"
          density="compact"
          class="mb-4"
        >
          Surveillance cameras rarely see faces. Consider turning face identification off for this
          camera.
        </v-alert>
        <v-row v-if="form.face_id_enabled" dense>
          <v-col cols="12" sm="8">
            <v-text-field
              v-model.number="form.face_id_min_raw_similarity"
              label="Minimum raw face similarity (advanced, leave empty)"
              type="number"
              min="0"
              max="1"
              step="0.05"
              clearable
              hint="Faces are weighed by calibrated confidence. Set a value only to ignore weak face matches from a camera that misidentifies people."
              persistent-hint
            />
          </v-col>
        </v-row>
      </template>

      <template #section-geometry>
        <v-row dense>
          <v-col cols="12" sm="4">
            <v-text-field
              v-model.number="form.horizontal_fov_deg"
              label="Horizontal FOV (°)"
              type="number"
              min="20"
              max="180"
              step="1"
              clearable
              hint="Typical range: 60° to 130°."
              persistent-hint
            />
          </v-col>
          <v-col cols="12" sm="4">
            <v-text-field
              v-model.number="form.mounting_height_m"
              label="Mounting height (m)"
              type="number"
              min="0.1"
              max="10"
              step="0.1"
              clearable
              hint="Camera lens height above the floor."
              persistent-hint
            />
          </v-col>
          <v-col cols="12" sm="4">
            <v-text-field
              v-model.number="form.tilt_deg"
              label="Tilt (°, must be ≤ 0)"
              type="number"
              min="-90"
              max="0"
              step="1"
              clearable
              hint="0 = horizontal, −90 = straight down."
              persistent-hint
            />
          </v-col>
        </v-row>
        <v-card variant="tonal" class="pa-4 mt-4">
          <div class="text-subtitle-2 mb-1">Finding the horizontal FOV</div>
          <div class="text-body-2 text-medium-emphasis">
            Use the horizontal field of view (HFOV) from the camera's spec sheet. If it lists only
            the diagonal FOV, multiply by about 0.8 for 16:9 sensors. Examples: Reolink 823A ≈ 87°,
            Hikvision DS-2CD series ≈ 103°, Wyze Cam v3 ≈ 110°.
          </div>
        </v-card>
      </template>

      <template #section-placement>
        <v-card variant="tonal" class="pa-4 d-flex align-center flex-wrap ga-3">
          <div>
            <div class="text-caption text-medium-emphasis">Map placement</div>
            <div class="font-weight-medium">{{ placementStatusLabel }}</div>
          </div>
          <v-spacer />
          <v-btn
            v-if="hasOperatorMarker"
            size="small"
            variant="text"
            color="error"
            @click="clearMarker"
          >
            Clear
          </v-btn>
          <v-btn
            size="small"
            variant="tonal"
            prepend-icon="mdi-map-marker-radius"
            :disabled="!editing"
            @click="openPlacementMap"
          >
            Place on Map
          </v-btn>
        </v-card>
        <div v-if="!editing" class="text-body-2 text-medium-emphasis mt-4">
          Create the camera first, then reopen it to place it on the floor plan.
        </div>
      </template>
    </AppDialog>

    <!-- Placement Map dialog -->
    <AppDialog
      v-model="placementDialog"
      size="lg"
      persistent
      icon="mdi-map-marker-radius"
      label="Camera"
      title="Placement on Map"
      hint="Click on the map to place the camera. Drag to set its heading."
      confirm-label="Save Placement"
      :confirm-loading="savingMarker"
      @confirm="saveMarker"
    >
      <CTSCameraPlacementMap
        :floor-plan-url="floorPlanUrl"
        :initial-marker="activeMarker"
        @placed="onMarkerPlaced"
      />
    </AppDialog>

    <!-- Test-connect dialog -->
    <AppDialog
      v-model="testDialog"
      size="sm"
      icon="mdi-connection"
      label="Test"
      title="RTSP Connection"
      cancel-label="Close"
      confirm-label="Test"
      :confirm-loading="testing"
      :confirm-disabled="!testUrl"
      @confirm="runTestConnect"
    >
      <div class="px-6 py-5">
        <v-text-field
          v-model="testUrl"
          label="RTSP URL"
          placeholder="rtsp://192.168.1.10/stream"
          autofocus
        />
        <v-alert
          v-if="testResult"
          :type="testResult.ok ? 'success' : 'error'"
          variant="tonal"
          density="compact"
          class="mt-2"
        >
          {{ testResult.message }}
        </v-alert>
      </div>
    </AppDialog>

    <!-- Snapshot dialog -->
    <AppDialog
      :model-value="snapshotDialog"
      size="lg"
      icon="mdi-image-outline"
      label="Camera"
      title="Snapshot"
      hide-footer
      @update:model-value="(open) => !open && closeSnapshot()"
    >
      <v-img v-if="snapshotUrl" :src="displaySrc(snapshotUrl)" />
      <div v-else class="d-flex align-center justify-center pa-8">
        <v-progress-circular indeterminate />
      </div>
      <template #footer>
        <v-divider />
        <v-card-actions class="px-6 py-3">
          <BlurToggle />
          <v-spacer />
          <v-btn variant="text" @click="closeSnapshot">Close</v-btn>
        </v-card-actions>
      </template>
    </AppDialog>

    <!-- Delete confirm -->
    <v-dialog v-model="confirmDialog" max-width="400" persistent>
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
import { ref, computed, watch, onMounted, onBeforeUnmount } from "vue";
import { cts } from "../../services/cts.js";
import { api } from "../../services/api.js";
import { useNotify } from "../../composables/useNotify.js";
import { useConfirm } from "../../composables/useConfirm.js";
import { useBlurMode, useDisplaySrc } from "../../composables/useBlurMode.js";
import { useFloorPlanCanvas } from "../../composables/useFloorPlanCanvas.js";
import AppDialog from "../../components/common/AppDialog.vue";
import BlurToggle from "../../components/cts/BlurToggle.vue";
import CTSCameraPlacementMap from "../../components/cts/cameras/CTSCameraPlacementMap.vue";

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

const activeSection = ref("general");
const fieldErrors = ref({});
const formProbe = ref(null);
const formProbing = ref(false);

const testDialog = ref(false);
const testUrl = ref("");
const testResult = ref(null);
const testing = ref(false);

const snapshotDialog = ref(false);
const snapshotUrl = ref(null);

const { floorPlanUrl, loadFloorPlan } = useFloorPlanCanvas();
const placementDialog = ref(false);
const activeMarker = ref(null);
const newMarker = ref(null);
const savingMarker = ref(false);
const visibilityPolygons = ref(null);

const placementStatusLabel = computed(() => {
  if (!editId.value || !visibilityPolygons.value) return "Unplaced";
  const vp = visibilityPolygons.value.cameras.find((c) => c.camera_id === editId.value);
  if (vp?.marker) return "Operator Defined";
  if (vp?.marker_estimate) return "Derived Estimate";
  return "Unplaced";
});

const ROLE_OPTIONS = [
  {
    value: "surveillance",
    title: "Surveillance",
    description: "Top-down or overview angle. Faces are rarely visible.",
  },
  {
    value: "face_capable",
    title: "Face-capable",
    description: "Eye-level angle with usable faces, such as a doorway or hallway.",
  },
  {
    value: "mixed",
    title: "Mixed",
    description: "Faces are visible some of the time.",
  },
];

const roleDescription = computed(
  () => ROLE_OPTIONS.find((option) => option.value === form.value.role)?.description ?? "",
);

const cameraSections = computed(() => [
  {
    key: "general",
    label: "General",
    icon: "mdi-cctv",
    description: "Identify the camera, its stream, and the room it watches.",
    error: Object.keys(fieldErrors.value).length > 0,
  },
  {
    key: "identity",
    label: "Identity",
    icon: "mdi-face-recognition",
    description: "How this camera contributes to recognizing who is in view.",
  },
  {
    key: "geometry",
    label: "Geometry",
    icon: "mdi-angle-acute",
    description: "Optional physical parameters. They improve automatic calibration accuracy.",
  },
  {
    key: "placement",
    label: "Placement",
    icon: "mdi-map-marker-radius",
    description: "Where the camera sits on the floor plan.",
  },
]);

const hasOperatorMarker = computed(() => {
  if (!editId.value || !visibilityPolygons.value) return false;
  const vp = visibilityPolygons.value.cameras.find((c) => c.camera_id === editId.value);
  return !!vp?.marker;
});

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

// Optional numeric fields: a cleared number input yields "", which the API rejects; send null.
const OPTIONAL_NUMBER_FIELDS = [
  "face_id_min_raw_similarity",
  "horizontal_fov_deg",
  "mounting_height_m",
  "tilt_deg",
];

const emptyForm = () => ({
  id: "",
  name: "",
  rtsp_url: "",
  room_name: "",
  room_id: null,
  enabled: true,
  face_id_enabled: true,
  face_id_min_raw_similarity: null,
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
    visibilityPolygons.value = await cts.getVisibilityPolygons();
  } catch (e) {
    notify(e.message, "error");
  } finally {
    loading.value = false;
  }
}

function resetDialogState() {
  activeSection.value = "general";
  fieldErrors.value = {};
  formProbe.value = null;
}

function openCreate() {
  resetDialogState();
  editing.value = false;
  editId.value = null;
  form.value = emptyForm();
  useCustomName.value = false;
  dialog.value = true;
}

function openEdit(cam) {
  resetDialogState();
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
    face_id_min_raw_similarity: cam.face_id_min_raw_similarity ?? null,
    role: cam.role || "surveillance",
    horizontal_fov_deg: cam.horizontal_fov_deg ?? null,
    mounting_height_m: cam.mounting_height_m ?? null,
    tilt_deg: cam.tilt_deg ?? null,
  };
  dialog.value = true;
}

/** Field errors for the General section; an empty object means the form may be sent. */
function validateForm() {
  const errors = {};
  if (!editing.value && !form.value.id?.trim()) errors.id = "Enter a camera ID";
  if (useCustomName.value ? !form.value.room_name?.trim() : !form.value.room_id) {
    errors.location = useCustomName.value
      ? "Enter a custom location name or choose a room"
      : "Choose a room or enable Custom name";
  }
  return errors;
}

// After a failed save, re-validate as the operator fixes the fields so errors clear in place.
watch(
  () => [form.value.id, form.value.room_id, form.value.room_name, useCustomName.value],
  () => {
    if (Object.keys(fieldErrors.value).length) fieldErrors.value = validateForm();
  },
);

async function saveCamera() {
  fieldErrors.value = validateForm();
  if (Object.keys(fieldErrors.value).length) {
    // Every validated field lives in General; show it rather than a toast about a hidden field.
    activeSection.value = "general";
    return;
  }
  saving.value = true;
  try {
    const payload = { ...form.value };
    for (const key of OPTIONAL_NUMBER_FIELDS) {
      if (payload[key] === "") payload[key] = null;
    }
    if (useCustomName.value) {
      payload.room_id = null;
    } else {
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

function openPlacementMap() {
  if (!editId.value || !visibilityPolygons.value) {
    notify("Please save the camera first", "warning");
    return;
  }
  const vp = visibilityPolygons.value.cameras.find((c) => c.camera_id === editId.value);
  activeMarker.value = vp?.marker ?? vp?.marker_estimate ?? null;
  newMarker.value = null;
  placementDialog.value = true;
}

function onMarkerPlaced(marker) {
  newMarker.value = marker;
}

async function saveMarker() {
  if (!newMarker.value) {
    placementDialog.value = false;
    return;
  }
  savingMarker.value = true;
  try {
    await cts.setCameraMarker(editId.value, newMarker.value);
    notify("Marker placement saved");
    placementDialog.value = false;
    await loadCameras(); // reload visibility polygons to get updated marker
  } catch (e) {
    notify(e.message, "error");
  } finally {
    savingMarker.value = false;
  }
}

async function clearMarker() {
  if (!editId.value) return;
  try {
    await cts.deleteCameraMarker(editId.value);
    notify("Marker placement cleared");
    await loadCameras();
  } catch (e) {
    notify(e.message, "error");
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

async function probeRtsp(url) {
  try {
    const r = await cts.testConnect(url);
    return { ok: true, message: r.message || "Connection successful" };
  } catch (e) {
    return { ok: false, message: e.message };
  }
}

async function runTestConnect() {
  if (!testUrl.value) return;
  testing.value = true;
  testResult.value = null;
  testResult.value = await probeRtsp(testUrl.value);
  testing.value = false;
}

async function probeFormUrl() {
  if (!form.value.rtsp_url) return;
  formProbing.value = true;
  formProbe.value = null;
  formProbe.value = await probeRtsp(form.value.rtsp_url);
  formProbing.value = false;
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
  loadFloorPlan();
});
onBeforeUnmount(() => {
  if (snapshotUrl.value) URL.revokeObjectURL(snapshotUrl.value);
});
</script>
