<template>
  <div>
    <div class="d-flex align-center mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Privacy Zones</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Define regions that the tracking system must never process.
        </div>
      </div>
      <v-spacer />
      <v-select
        v-model="selectedCameraId"
        :items="cameras"
        item-title="name"
        item-value="id"
        label="Camera"
        variant="outlined"
        density="compact"
        hide-details
        style="max-width: 260px"
        @update:model-value="loadZones"
      />
    </div>

    <template v-if="selectedCameraId">
      <div class="d-flex align-center mb-4">
        <span class="text-h6">Zones for {{ cameraName }}</span>
        <v-spacer />
        <v-btn color="primary" variant="flat" prepend-icon="mdi-plus" @click="openCreate">
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
              {{ zone.name }}
              <v-spacer />
              <v-chip
                size="x-small"
                :color="zone.enabled ? 'success' : 'default'"
                class="ml-1"
              >
                {{ zone.enabled ? "On" : "Off" }}
              </v-chip>
            </v-card-title>
            <v-card-text>
              <div class="text-caption text-medium-emphasis mb-1">ID: {{ zone.zone_id }}</div>
              <v-chip size="x-small" variant="tonal" color="primary">{{ zone.policy }}</v-chip>
              <div class="text-caption mt-2 text-medium-emphasis">
                {{ zone.polygon.length }} vertices
                <span v-if="zone.drop_count !== undefined" class="ml-2">
                  · {{ zone.drop_count }} detections dropped (24h)
                </span>
              </div>
              <!-- Mini polygon preview -->
              <svg viewBox="0 0 100 60" class="zone-preview mt-2">
                <polygon
                  :points="zone.polygon.map(([x, y]) => `${x * 100},${y * 60}`).join(' ')"
                  style="fill: var(--cc-brand-soft); stroke: var(--cc-brand); stroke-width: 1.5"
                />
              </svg>
            </v-card-text>
            <v-card-actions>
              <v-btn size="small" variant="text" prepend-icon="mdi-pencil" color="primary" @click="openEdit(zone)">Edit</v-btn>
              <v-spacer />
              <v-btn size="small" variant="text" color="error" @click="removeZone(zone.zone_id)">Remove</v-btn>
            </v-card-actions>
          </v-card>
        </v-col>
      </v-row>

      <div v-if="zones.length > 0" class="d-flex justify-end mt-4">
        <v-btn
          color="primary"
          variant="flat"
          :loading="saving"
          prepend-icon="mdi-content-save"
          @click="saveZones"
        >
          Save to Camera
        </v-btn>
      </div>
    </template>

    <v-alert v-else type="info" variant="tonal" class="mt-4">
      Select a camera to manage its privacy zones.
    </v-alert>

    <!-- Add / Edit zone dialog -->
    <v-dialog v-model="dialog" max-width="540" persistent>
      <v-card>
        <DialogHeader
          icon="mdi-shield-eye-outline"
          :label="editingZone ? 'Edit' : 'Create New'"
          :title="editingZone ? 'Privacy Zone' : 'Privacy Zone'"
          @close="dialog = false"
        />
        <v-card-text>
          <v-text-field
            v-model="form.zone_id"
            label="Zone ID"
            variant="outlined"
            class="mb-3"
            :disabled="!!editingZone"
            hint="Stable identifier, e.g. bathroom-mirror"
            persistent-hint
          />
          <v-text-field v-model="form.name" label="Display Name" variant="outlined" class="mb-3" />
          <v-select
            v-model="form.policy"
            :items="policies"
            label="Privacy Policy"
            variant="outlined"
            class="mb-3"
          />
          <v-switch v-model="form.enabled" label="Enabled" color="primary" class="mb-2" />

          <div class="text-subtitle-2 mb-2">
            Polygon Vertices
            <span class="text-caption text-medium-emphasis ml-1">(normalised 0–1, top-left origin)</span>
          </div>
          <div v-for="(pt, i) in form.polygon" :key="i" class="d-flex align-center mb-2">
            <v-chip size="x-small" class="mr-2" style="width:24px">{{ i + 1 }}</v-chip>
            <v-text-field
              v-model.number="pt[0]"
              label="X"
              variant="outlined"
              density="compact"
              type="number"
              step="0.01"
              min="0"
              max="1"
              hide-details
              class="mr-2"
              style="max-width:120px"
            />
            <v-text-field
              v-model.number="pt[1]"
              label="Y"
              variant="outlined"
              density="compact"
              type="number"
              step="0.01"
              min="0"
              max="1"
              hide-details
              style="max-width:120px"
            />
            <v-btn icon="mdi-close" size="x-small" variant="text" class="ml-1" @click="form.polygon.splice(i, 1)" />
          </div>
          <v-btn size="small" variant="tonal" prepend-icon="mdi-plus" class="mt-1" @click="form.polygon.push([0, 0])">
            Add Vertex
          </v-btn>
        </v-card-text>
        <DialogFooter
          hint="Privacy zones define regions where face identification is restricted for resident privacy."
          :confirm-label="editingZone ? 'Update' : 'Add'"
          @cancel="dialog = false"
          @confirm="commitZone"
        />
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snack" :color="snackColor" timeout="3500">{{ snackText }}</v-snackbar>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { cts } from "../../services/cts.js";
import { useNotify } from "../../composables/useNotify.js";
import DialogHeader from "../../components/common/DialogHeader.vue";
import DialogFooter from "../../components/common/DialogFooter.vue";

const { snack, snackText, snackColor, notify } = useNotify();

const cameras = ref([]);
const selectedCameraId = ref(null);
const zones = ref([]);
const dialog = ref(false);
const editingZone = ref(null);
const saving = ref(false);

const policies = ["mask_region", "blur_region", "skip_detection"];

const cameraName = computed(
  () => cameras.value.find((c) => c.id === selectedCameraId.value)?.name ?? selectedCameraId.value
);

const emptyForm = () => ({
  zone_id: "",
  name: "",
  policy: "mask_region",
  enabled: true,
  polygon: [
    [0.0, 0.0],
    [1.0, 0.0],
    [1.0, 1.0],
    [0.0, 1.0],
  ],
});

const form = ref(emptyForm());

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
}

function openCreate() {
  editingZone.value = null;
  form.value = emptyForm();
  dialog.value = true;
}

function openEdit(zone) {
  editingZone.value = zone;
  form.value = JSON.parse(JSON.stringify(zone));
  dialog.value = true;
}

function commitZone() {
  const z = { ...form.value, polygon: form.value.polygon.map(([x, y]) => [Number(x), Number(y)]) };
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
    notify("Privacy zones saved");
  } catch (e) {
    notify(e.message, "error");
  } finally {
    saving.value = false;
  }
}

onMounted(loadCameras);
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
