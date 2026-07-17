<template>
  <div>
    <div class="d-flex align-center mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Sensors</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">Cameras, motion sensors, and other inputs the system listens to.</div>
      </div>
      <v-spacer />
      <v-btn variant="tonal" class="mr-2" prepend-icon="mdi-home-automation" @click="syncFromHA">
        Import from HA
      </v-btn>
      <v-btn color="primary" variant="flat" prepend-icon="mdi-plus" @click="openCreate">Add Sensor</v-btn>
    </div>

    <v-card class="glass-card">
      <v-data-table :headers="headers" :items="sensors" :loading="loading" item-value="id">
        <template #item.enabled="{ item }">
          <v-chip :color="item.enabled ? 'success' : 'grey'" size="small">
            {{ item.enabled ? 'On' : 'Off' }}
          </v-chip>
        </template>
        <template #item.actions="{ item }">
          <v-btn icon="mdi-pencil" size="small" variant="text" color="primary" @click="openEdit(item)" />
          <v-btn icon="mdi-delete" size="small" variant="text" color="error" @click="deleteSensor(item.id)" />
        </template>
        <template #no-data>
          <div class="pa-6 text-center">
            <v-card flat>
              <v-card-text class="text-grey text-h6">No sensors yet</v-card-text>
              <v-card-text class="text-grey">Add sensors or import from Home Assistant to begin monitoring.</v-card-text>
            </v-card>
          </div>
        </template>
      </v-data-table>
    </v-card>

    <v-dialog v-model="dialog" max-width="500" persistent>
      <v-card>
        <DialogHeader
          icon="mdi-access-point"
          :label="editing ? 'Edit' : 'Create New'"
          :title="editing ? 'Sensor' : 'Sensor'"
          @close="dialog = false"
        />
        <v-card-text>
          <v-text-field v-model="form.name" label="Name" variant="outlined" class="mb-2" />
          <v-select v-model="form.sensor_type" :items="sensorTypes" label="Type" variant="outlined" class="mb-2" />
          <v-select v-model="form.source" :items="['manual', 'homeassistant']" label="Source" variant="outlined" class="mb-2" />
          <v-select v-model="form.room_id" :items="roomOptions" label="Room" variant="outlined" item-title="name" item-value="id" class="mb-2" />
          <v-text-field v-model="form.ha_entity_id" label="HA Entity ID (optional)" variant="outlined" class="mb-2" />
          <v-switch v-model="form.enabled" label="Enabled" color="primary" />
        </v-card-text>
        <DialogFooter
          hint="Sensors provide presence, motion, and environmental data for rule triggers."
          :confirm-label="editing ? 'Update' : 'Create'"
          @cancel="dialog = false"
          @confirm="saveSensor"
        />
      </v-card>
    </v-dialog>

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
import { useNotify } from "../../composables/useNotify.js";
import { useConfirm } from "../../composables/useConfirm.js";
import DialogHeader from "../../components/common/DialogHeader.vue";
import DialogFooter from "../../components/common/DialogFooter.vue";

const { notify } = useNotify();
const { confirmDialog, confirmTitle, confirmText, showConfirm, onConfirm, onCancel } = useConfirm();

const sensors = ref([]);
const roomOptions = ref([]);
const loading = ref(false);
const dialog = ref(false);
const editing = ref(false);
const editId = ref(null);
const sensorTypes = ["camera", "presence", "light", "button", "distance", "generic"];

const emptyForm = () => ({
  name: "", sensor_type: "camera", source: "manual", room_id: null, ha_entity_id: "", enabled: true,
});
const form = ref(emptyForm());

const headers = [
  { title: "Name", key: "name" },
  { title: "Type", key: "sensor_type" },
  { title: "Source", key: "source" },
  { title: "Room", key: "room_name" },
  { title: "Status", key: "enabled" },
  { title: "Actions", key: "actions", sortable: false },
];

async function loadData() {
  loading.value = true;
  try {
    const [rawSensors, rooms] = await Promise.all([
      api.getSensors(),
      api.getRooms(),
    ]);
    roomOptions.value = rooms;
    const roomMap = Object.fromEntries(rooms.map(r => [r.id, r.name]));
    sensors.value = rawSensors.map(s => ({ ...s, room_name: roomMap[s.room_id] ?? '' }));
  } catch (e) { console.error("Failed to load sensors:", e); sensors.value = []; roomOptions.value = []; }
  loading.value = false;
}

function openCreate() { form.value = emptyForm(); editing.value = false; dialog.value = true; }
function openEdit(item) {
  form.value = { ...item };
  editId.value = item.id;
  editing.value = true;
  dialog.value = true;
}

async function saveSensor() {
  try {
    if (editing.value) await api.updateSensor(editId.value, form.value);
    else await api.createSensor(form.value);
    dialog.value = false;
    await loadData();
  } catch (e) { notify(e.message, "error"); }
}

async function deleteSensor(id) {
  if (!await showConfirm("Delete Sensor", "Delete this sensor?")) return;
  try { await api.deleteSensor(id); await loadData(); } catch (e) { notify(e.message, "error"); }
}

async function syncFromHA() {
  try {
    const result = await api.syncSensors();
    notify(`Imported ${result.created} sensors (${result.skipped} skipped)`);
    await loadData();
  } catch (e) { notify(e.message, "error"); }
}

onMounted(loadData);
</script>

<style scoped>
.tracking-tight {
  letter-spacing: -0.018em;
}
</style>
