<template>
  <div>
    <div class="d-flex align-center mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Rooms</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">Spaces in the home where sensors live and rules apply.</div>
      </div>
      <v-spacer />
      <v-btn variant="tonal" class="mr-2" prepend-icon="mdi-home-automation" @click="syncFromHA">
        Sync from HA
      </v-btn>
      <v-btn color="primary" variant="flat" prepend-icon="mdi-plus" @click="openCreate">Add Room</v-btn>
    </div>

    <v-card class="glass-card">
      <v-data-table :headers="headers" :items="rooms" :loading="loading" item-value="id">
        <template #item.actions="{ item }">
          <v-btn icon="mdi-pencil" size="small" variant="text" color="primary" @click="openEdit(item)" />
          <v-btn icon="mdi-delete" size="small" variant="text" color="error" @click="deleteRoom(item.id)" />
        </template>
        <template #no-data>
          <div class="pa-6 text-center">
            <v-card flat>
              <v-card-text class="text-grey text-h6">No rooms yet</v-card-text>
              <v-card-text class="text-grey">Add rooms to organize sensors by location.</v-card-text>
            </v-card>
          </div>
        </template>
      </v-data-table>
    </v-card>

    <v-dialog v-model="dialog" max-width="400" persistent>
      <v-card>
        <DialogHeader
          icon="mdi-door-open"
          :label="editing ? 'Edit' : 'Create New'"
          :title="editing ? 'Room' : 'Room'"
          @close="dialog = false"
        />
        <v-card-text>
          <v-text-field v-model="form.name" label="Name" variant="outlined" class="mb-2" />
          <v-text-field v-model="form.ha_area_id" label="HA Area ID (optional)" variant="outlined" class="mb-2" />
          <v-text-field v-model="form.floor" label="Floor (optional)" variant="outlined" />
        </v-card-text>
        <DialogFooter
          hint="Rooms group sensors and define spatial context for rules and presence tracking."
          :confirm-label="editing ? 'Update' : 'Create'"
          @cancel="dialog = false"
          @confirm="saveRoom"
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

<style scoped>
.tracking-tight {
  letter-spacing: -0.018em;
}
</style>
