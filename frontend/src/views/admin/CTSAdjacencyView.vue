<template>
  <div>
    <div class="d-flex align-center mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Camera Adjacency</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Define which cameras share a physical boundary and the expected transit time between them.
        </div>
      </div>
      <v-spacer />
      <v-btn color="primary" variant="flat" prepend-icon="mdi-plus" @click="openCreate">
        Add Edge
      </v-btn>
    </div>

    <v-alert v-if="edges.length === 0" type="info" variant="tonal" class="mb-4">
      No adjacency edges defined. Add edges to help the tracker resolve cross-camera identity.
    </v-alert>

    <v-card v-if="edges.length > 0" class="mb-4">
      <v-data-table :headers="headers" :items="edges" item-value="_key">
        <template #item.transit="{ item }">
          {{ item.min_transit_s }}s – {{ item.max_transit_s }}s
        </template>
        <template #item.actions="{ item }">
          <v-btn icon="mdi-pencil" size="small" variant="text" @click="openEdit(item)" />
          <v-btn icon="mdi-delete" size="small" variant="text" color="error" @click="removeEdge(item)" />
        </template>
      </v-data-table>
    </v-card>

    <div class="d-flex justify-end mt-2">
      <v-btn
        color="primary"
        variant="flat"
        :loading="saving"
        :disabled="edges.length === 0"
        prepend-icon="mdi-content-save"
        @click="saveAdjacency"
      >
        Save Adjacency
      </v-btn>
    </div>

    <!-- Add / Edit edge dialog -->
    <v-dialog v-model="dialog" max-width="460">
      <v-card>
        <v-card-title>{{ editingIdx !== null ? "Edit Edge" : "Add Adjacency Edge" }}</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="form.from"
            label="From Camera ID"
            variant="outlined"
            class="mb-3"
            hint="Stable camera ID, e.g. hallway-cam-1"
            persistent-hint
          />
          <v-text-field
            v-model="form.to"
            label="To Camera ID"
            variant="outlined"
            class="mb-3"
          />
          <v-row dense>
            <v-col cols="6">
              <v-text-field
                v-model.number="form.min_transit_s"
                label="Min transit (s)"
                variant="outlined"
                density="compact"
                type="number"
                min="0"
                step="0.5"
                hint="Fastest plausible crossing"
                persistent-hint
              />
            </v-col>
            <v-col cols="6">
              <v-text-field
                v-model.number="form.max_transit_s"
                label="Max transit (s)"
                variant="outlined"
                density="compact"
                type="number"
                min="0"
                step="1"
                hint="Slowest plausible crossing"
                persistent-hint
              />
            </v-col>
          </v-row>
          <v-alert
            v-if="form.max_transit_s < form.min_transit_s"
            type="error"
            density="compact"
            class="mt-3"
          >
            Max transit must be ≥ min transit.
          </v-alert>
        </v-card-text>
        <v-card-actions class="px-6 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="dialog = false">Cancel</v-btn>
          <v-btn
            color="primary"
            variant="flat"
            :disabled="form.max_transit_s < form.min_transit_s || !form.from || !form.to"
            @click="commitEdge"
          >
            {{ editingIdx !== null ? "Update" : "Add" }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snack" :color="snackColor" timeout="3500">{{ snackText }}</v-snackbar>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { cts } from "../../services/cts.js";
import { useNotify } from "../../composables/useNotify.js";

const { snack, snackText, snackColor, notify } = useNotify();

const edges = ref([]);
const dialog = ref(false);
const editingIdx = ref(null);
const saving = ref(false);

const headers = [
  { title: "From", key: "from" },
  { title: "To", key: "to" },
  { title: "Transit Window", key: "transit" },
  { title: "", key: "actions", sortable: false, align: "end" },
];

const emptyForm = () => ({ from: "", to: "", min_transit_s: 0.5, max_transit_s: 30 });
const form = ref(emptyForm());

async function loadAdjacency() {
  try {
    // edge_count only from GET; edges are managed locally until saved
    await cts.getAdjacency();
  } catch {
    // orchestrator may be offline in dev — silently ignore
  }
}

function openCreate() {
  editingIdx.value = null;
  form.value = emptyForm();
  dialog.value = true;
}

function openEdit(edge) {
  editingIdx.value = edges.value.indexOf(edge);
  form.value = { ...edge };
  dialog.value = true;
}

function commitEdge() {
  const edge = { ...form.value };
  // synthetic key for v-data-table deduplication
  edge._key = `${edge.from}->${edge.to}`;
  if (editingIdx.value !== null) {
    edges.value[editingIdx.value] = edge;
  } else {
    edges.value.push(edge);
  }
  dialog.value = false;
}

function removeEdge(edge) {
  edges.value = edges.value.filter((e) => e !== edge);
}

async function saveAdjacency() {
  saving.value = true;
  try {
    // Strip synthetic _key before sending
    const payload = edges.value.map(({ _key: _k, ...rest }) => rest);
    await cts.postAdjacency(payload);
    notify("Adjacency graph saved");
  } catch (e) {
    notify(e.message, "error");
  } finally {
    saving.value = false;
  }
}

onMounted(loadAdjacency);
</script>
