<template>
  <div>
    <div class="d-flex align-center mb-4">
      <h2 class="text-h5">Rooms</h2>
      <v-spacer />
      <v-btn variant="tonal" class="mr-2" prepend-icon="mdi-home-automation" @click="syncFromHA">
        Sync from HA
      </v-btn>
      <v-btn color="primary" prepend-icon="mdi-plus" @click="openCreate">Add Room</v-btn>
    </div>

    <v-card rounded="xl">
      <v-data-table :headers="headers" :items="rooms" :loading="loading" item-value="id">
        <template #item.actions="{ item }">
          <v-btn icon="mdi-pencil" size="small" variant="text" @click="openEdit(item)" />
          <v-btn icon="mdi-delete" size="small" variant="text" color="error" @click="deleteRoom(item.id)" />
        </template>
      </v-data-table>
    </v-card>

    <v-dialog v-model="dialog" max-width="400">
      <v-card rounded="xl">
        <v-card-title>{{ editing ? 'Edit Room' : 'Add Room' }}</v-card-title>
        <v-card-text>
          <v-text-field v-model="form.name" label="Name" variant="outlined" class="mb-2" />
          <v-text-field v-model="form.ha_area_id" label="HA Area ID (optional)" variant="outlined" class="mb-2" />
          <v-text-field v-model="form.floor" label="Floor (optional)" variant="outlined" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="dialog = false">Cancel</v-btn>
          <v-btn color="primary" @click="saveRoom">{{ editing ? 'Update' : 'Create' }}</v-btn>
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
import { useNotify } from "../../composables/useNotify.js";
import { useConfirm } from "../../composables/useConfirm.js";

const { snack, snackText, snackColor, notify } = useNotify();
const { confirmDialog, confirmTitle, confirmText, showConfirm, onConfirm, onCancel } = useConfirm();

const rooms = ref([]);
const loading = ref(false);
const dialog = ref(false);
const editing = ref(false);
const editId = ref(null);

const emptyForm = () => ({ name: "", ha_area_id: "", floor: "" });
const form = ref(emptyForm());

const headers = [
  { title: "Name", key: "name" },
  { title: "HA Area ID", key: "ha_area_id" },
  { title: "Floor", key: "floor" },
  { title: "Actions", key: "actions", sortable: false },
];

async function loadRooms() {
  loading.value = true;
  try { rooms.value = await api.getRooms(); } catch (e) { console.error("Failed to load rooms:", e); rooms.value = []; }
  loading.value = false;
}

function openCreate() { form.value = emptyForm(); editing.value = false; dialog.value = true; }
function openEdit(item) { form.value = { ...item }; editId.value = item.id; editing.value = true; dialog.value = true; }

async function saveRoom() {
  try {
    if (editing.value) await api.updateRoom(editId.value, form.value);
    else await api.createRoom(form.value);
    dialog.value = false;
    await loadRooms();
  } catch (e) { notify(e.message, "error"); }
}

async function deleteRoom(id) {
  if (!await showConfirm("Delete Room", "Delete this room?")) return;
  try { await api.deleteRoom(id); await loadRooms(); } catch (e) { notify(e.message, "error"); }
}

async function syncFromHA() {
  try {
    const result = await api.syncRooms();
    notify(`Created ${result.created}, updated ${result.updated} rooms`);
    await loadRooms();
  } catch (e) { notify(e.message, "error"); }
}

onMounted(loadRooms);
</script>
