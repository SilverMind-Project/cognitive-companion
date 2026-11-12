<template>
  <div>
    <div class="d-flex align-center flex-wrap ga-3 mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Privacy Zones</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Define regions of a camera's view that the tracking system hides or ignores.
        </div>
      </div>
      <v-spacer />
      <v-select
        :model-value="selectedCameraId"
        :items="cameras"
        item-title="name"
        item-value="id"
        label="Camera"
        variant="outlined"
        density="compact"
        hide-details
        style="max-width: 260px"
        @update:model-value="selectCamera"
      />
    </div>

    <template v-if="selectedCameraId">
      <div class="d-flex align-center flex-wrap ga-3 mb-4">
        <span class="text-h6">Zones for {{ cameraName }}</span>
        <v-chip v-if="dirty" size="small" color="warning" variant="tonal">Unsaved changes</v-chip>
        <v-spacer />
        <v-btn
          v-if="dirty"
          color="primary"
          variant="flat"
          :loading="saving"
          prepend-icon="mdi-content-save"
          @click="saveZones"
        >
          Save to Camera
        </v-btn>
        <v-btn color="primary" variant="tonal" prepend-icon="mdi-plus" @click="openCreate">
          Add Zone
        </v-btn>
      </div>

      <v-alert v-if="zones.length === 0" type="info" variant="tonal" class="mb-4">
        No privacy zones configured for this camera.
      </v-alert>

      <v-row>
        <v-col v-for="zone in zones" :key="zone.zone_id" cols="12" sm="6" md="4">
          <v-card :class="{ 'opacity-60': !zone.enabled }">
            <v-card-title class="d-flex align-center">
              <v-icon class="mr-2" size="small" color="primary">mdi-eye-off-outline</v-icon>
              {{ zone.name || zone.zone_id }}
              <v-spacer />
              <v-chip size="x-small" :color="zone.enabled ? 'success' : 'default'" class="ml-1">
                {{ zone.enabled ? "On" : "Off" }}
              </v-chip>
            </v-card-title>
            <v-card-text>
              <div class="text-caption text-medium-emphasis mb-1">ID: {{ zone.zone_id }}</div>
              <v-chip size="x-small" variant="tonal" color="primary">
                {{ policyTitle(zone.policy) }}
              </v-chip>
              <div class="text-caption mt-2 text-medium-emphasis">
                {{ zone.polygon.length }} vertices
                <span v-if="zone.drop_count !== undefined" class="ml-2">
                  · {{ zone.drop_count }} detections dropped (24h)
                </span>
              </div>
              <!-- Mini polygon preview -->
              <svg viewBox="0 0 160 90" class="zone-preview mt-2">
                <polygon
                  :points="zone.polygon.map(([x, y]) => `${x * 160},${y * 90}`).join(' ')"
                  style="fill: var(--cc-brand-soft); stroke: var(--cc-brand); stroke-width: 1.5"
                />
              </svg>
            </v-card-text>
            <v-card-actions>
              <v-btn
                size="small"
                variant="text"
                prepend-icon="mdi-pencil"
                color="primary"
                @click="openEdit(zone)"
                >Edit</v-btn
              >
              <v-spacer />
              <v-btn size="small" variant="text" color="error" @click="removeZone(zone.zone_id)"
                >Remove</v-btn
              >
            </v-card-actions>
          </v-card>
        </v-col>
      </v-row>
    </template>

    <v-alert v-else type="info" variant="tonal" class="mt-4">
      Select a camera to manage its privacy zones.
    </v-alert>

    <!-- Add / Edit zone dialog: large split (form beside the drawing canvas) -->
    <AppDialog
      v-model="dialog"
      size="lg"
      persistent
      icon="mdi-shield-lock-outline"
      :label="editingZone ? 'Edit Privacy Zone' : 'Create New Privacy Zone'"
      :title="cameraName || 'Privacy Zone'"
      hint="Zones take effect when you save them to the camera."
      :confirm-label="editingZone ? 'Update' : 'Add'"
      :confirm-disabled="!canCommitZone"
      @confirm="commitZone"
    >
      <template #aside>
        <v-text-field
          v-model="form.zone_id"
          label="Zone ID"
          class="mb-3"
          :disabled="!!editingZone"
          :error-messages="zoneIdError"
          placeholder="bathroom-mirror"
          hint="A stable identifier that never changes."
          persistent-hint
        />
        <v-text-field v-model="form.name" label="Display Name" class="mb-3" />
        <v-select
          v-model="form.policy"
          :items="POLICY_OPTIONS"
          item-title="title"
          item-value="value"
          :item-props="policyItemProps"
          label="What happens in this zone"
          :hint="policyDescription"
          persistent-hint
          class="mb-3"
        />
        <v-switch v-model="form.enabled" label="Enabled" hide-details />
      </template>

      <div class="d-flex align-center flex-wrap ga-2 mb-3">
        <div>
          <div class="text-subtitle-2">Draw the zone</div>
          <div class="text-caption text-medium-emphasis">
            Click to place each vertex; double-click to close the shape.
          </div>
        </div>
        <v-spacer />
        <BlurToggle />
        <v-btn
          size="small"
          variant="tonal"
          prepend-icon="mdi-camera"
          :loading="snapshotLoading"
          :disabled="!selectedCameraId"
          @click="loadDialogSnapshot"
        >
          Refresh snapshot
        </v-btn>
      </div>
      <PolygonOnSnapshot
        :image-url="displaySrc(dialogSnapshotUrl)"
        :model-value="form.polygon"
        :min-points="3"
        @update:model-value="form.polygon = $event"
      />
    </AppDialog>

    <!-- Discard-changes confirm -->
    <v-dialog v-model="confirmDialog" max-width="400" persistent>
      <v-card rounded="xl">
        <v-card-title>{{ confirmTitle }}</v-card-title>
        <v-card-text>{{ confirmText }}</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="onCancel">{{ cancelLabel }}</v-btn>
          <v-btn :color="confirmColor" variant="flat" @click="onConfirm">{{ confirmLabel }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from "vue";
import { cts } from "../../services/cts.js";
import { useNotify } from "../../composables/useNotify.js";
import { useConfirm } from "../../composables/useConfirm.js";
import { useBlurMode, useDisplaySrc } from "../../composables/useBlurMode.js";
import AppDialog from "../../components/common/AppDialog.vue";
import PolygonOnSnapshot from "../../components/cts/PolygonOnSnapshot.vue";
import BlurToggle from "../../components/cts/BlurToggle.vue";

const { notify } = useNotify();
const {
  confirmDialog,
  confirmTitle,
  confirmText,
  confirmLabel,
  cancelLabel,
  confirmColor,
  showConfirm,
  onConfirm,
  onCancel,
} = useConfirm();
const { blurMode } = useBlurMode();
const { displaySrc } = useDisplaySrc(blurMode);

const cameras = ref([]);
const selectedCameraId = ref(null);
const zones = ref([]);
// Serialized zones as last loaded from or saved to the camera; the baseline for `dirty`.
const savedZones = ref("[]");
const dialog = ref(false);
const editingZone = ref(null);
const saving = ref(false);

// Dialog snapshot
const dialogSnapshotUrl = ref(null);
const snapshotLoading = ref(false);

// The values are the tracking orchestrator's canonical privacy policies. Its privacy stage runs
// after person detection: mask and blur hide the region in every image analyzed or kept from
// then on, while drop removes detections whose foot point falls inside the polygon.
const POLICY_OPTIONS = [
  {
    value: "mask_region",
    title: "Mask region",
    description: "Covers the area in solid grey in every image analyzed or kept after detection.",
  },
  {
    value: "blur_region",
    title: "Blur region",
    description: "Blurs the area in every image analyzed or kept after detection.",
  },
  {
    value: "drop_detection",
    title: "Drop detections",
    description: "People whose feet are inside the area are not tracked.",
  },
];

const cameraName = computed(
  () => cameras.value.find((c) => c.id === selectedCameraId.value)?.name ?? selectedCameraId.value,
);

const dirty = computed(() => JSON.stringify(zones.value) !== savedZones.value);

const emptyForm = () => ({
  zone_id: "",
  name: "",
  policy: "mask_region",
  enabled: true,
  polygon: [],
});

const form = ref(emptyForm());

const zoneIdError = computed(() => {
  if (editingZone.value) return "";
  const id = form.value.zone_id.trim();
  if (id && zones.value.some((z) => z.zone_id === id)) return "A zone with this ID already exists";
  return "";
});

const canCommitZone = computed(
  () => !!form.value.zone_id.trim() && !zoneIdError.value && form.value.polygon.length >= 3,
);

const policyDescription = computed(
  () => POLICY_OPTIONS.find((option) => option.value === form.value.policy)?.description ?? "",
);

function policyItemProps(option) {
  return { subtitle: option.description };
}

function policyTitle(value) {
  return POLICY_OPTIONS.find((option) => option.value === value)?.title ?? value;
}

async function loadCameras() {
  try {
    cameras.value = await cts.getCameras();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function loadZones() {
  if (!selectedCameraId.value) return;
  try {
    const data = await cts.getPrivacyZones(selectedCameraId.value);
    zones.value = data.zones || [];
  } catch (e) {
    zones.value = [];
    notify(e.message, "error");
  }
  savedZones.value = JSON.stringify(zones.value);
}

async function selectCamera(cameraId) {
  if (cameraId === selectedCameraId.value) return;
  if (dirty.value) {
    const discard = await showConfirm(
      "Discard unsaved zones?",
      `Your changes to ${cameraName.value}'s privacy zones have not been saved to the camera.`,
    );
    if (!discard) return;
  }
  selectedCameraId.value = cameraId;
  await loadZones();
}

async function loadDialogSnapshot() {
  if (!selectedCameraId.value) return;
  snapshotLoading.value = true;
  if (dialogSnapshotUrl.value) {
    URL.revokeObjectURL(dialogSnapshotUrl.value);
    dialogSnapshotUrl.value = null;
  }
  try {
    dialogSnapshotUrl.value = await cts.getSnapshot(selectedCameraId.value);
  } catch (e) {
    notify(`Snapshot failed: ${e.message}`, "warning");
  } finally {
    snapshotLoading.value = false;
  }
}

function openCreate() {
  editingZone.value = null;
  form.value = emptyForm();
  dialog.value = true;
  loadDialogSnapshot();
}

function openEdit(zone) {
  editingZone.value = zone;
  form.value = JSON.parse(JSON.stringify(zone));
  dialog.value = true;
  loadDialogSnapshot();
}

function commitZone() {
  if (!canCommitZone.value) return;
  const z = {
    ...form.value,
    zone_id: form.value.zone_id.trim(),
    polygon: form.value.polygon.map(([x, y]) => [Number(x), Number(y)]),
  };
  if (editingZone.value) {
    const idx = zones.value.findIndex((z) => z.zone_id === editingZone.value.zone_id);
    if (idx >= 0) zones.value[idx] = z;
  } else {
    zones.value.push(z);
  }
  dialog.value = false;
}

function removeZone(zoneId) {
  zones.value = zones.value.filter((z) => z.zone_id !== zoneId);
}

async function saveZones() {
  saving.value = true;
  try {
    await cts.postPrivacyZones(selectedCameraId.value, zones.value);
    savedZones.value = JSON.stringify(zones.value);
    notify("Privacy zones saved and applied to the tracker");
  } catch (e) {
    // The server saves zones only after the tracker accepts them, so a failure changed nothing.
    const trackerFailed = [502, 503, 504].includes(e.status);
    notify(
      trackerFailed
        ? `Privacy zones not saved: the tracker could not apply them. ${e.message}`
        : `Privacy zones not saved. ${e.message}`,
      "error",
    );
  } finally {
    saving.value = false;
  }
}

onMounted(loadCameras);
onBeforeUnmount(() => {
  if (dialogSnapshotUrl.value) URL.revokeObjectURL(dialogSnapshotUrl.value);
});
</script>

<style scoped>
.zone-preview {
  display: block;
  width: 100%;
  height: 60px;
  border: 1px solid var(--cc-divider-strong);
  border-radius: 4px;
  background: var(--cc-surface-3);
}
</style>
