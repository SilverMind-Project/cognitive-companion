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

    <!-- Existing edges from orchestrator -->
    <v-card v-if="savedEdges.length > 0" class="mb-4" variant="flat" border>
      <v-card-subtitle class="pt-3 pb-1">Saved in orchestrator</v-card-subtitle>
      <v-data-table
        :headers="savedHeaders"
        :items="savedEdges"
        item-value="_key"
        density="compact"
        hide-default-footer
        :items-per-page="-1"
      >
        <template #item.transit="{ item }">
          {{ item.min_transit_s }}s – {{ item.max_transit_s }}s
        </template>
        <template #item.overlap="{ item }">
          <v-icon v-if="item.overlap" color="success" size="small">mdi-check</v-icon>
          <span v-else class="text-medium-emphasis">—</span>
        </template>
        <template #item.actions="{ item }">
          <v-btn icon="mdi-pencil" size="small" variant="text" color="primary" @click="stageForEdit(item)" />
        </template>
      </v-data-table>
    </v-card>

    <v-alert v-else-if="!loadingEdges" type="info" variant="tonal" class="mb-4">
      No adjacency edges saved yet. Add edges to help the tracker resolve cross-camera identity.
    </v-alert>

    <!-- Locally-staged edits -->
    <v-card v-if="stagedEdges.length > 0" class="mb-4">
      <v-card-subtitle class="pt-3 pb-1">Staged (unsaved)</v-card-subtitle>
      <v-data-table :headers="editHeaders" :items="stagedEdges" item-value="_key" density="compact" hide-default-footer :items-per-page="-1">
        <template #item.transit="{ item }">
          {{ item.min_transit_s }}s – {{ item.max_transit_s }}s
        </template>
        <template #item.actions="{ item }">
          <v-btn icon="mdi-pencil" size="small" variant="text" color="primary" @click="openEdit(item)" />
          <v-btn icon="mdi-delete" size="small" variant="text" color="error" @click="removeEdge(item)" />
        </template>
      </v-data-table>
    </v-card>

    <div class="d-flex justify-end mt-2">
      <v-btn
        color="primary"
        variant="flat"
        :loading="saving"
        :disabled="stagedEdges.length === 0"
        prepend-icon="mdi-content-save"
        @click="saveAdjacency"
      >
        Save Adjacency
      </v-btn>
    </div>

    <!-- Add / Edit edge dialog -->
    <v-dialog v-model="dialog" max-width="500" persistent>
      <v-card>
        <DialogHeader
          icon="mdi-graph"
          :label="editingIdx !== null ? 'Edit' : 'Create New'"
          title="Adjacency Edge"
          @close="dialog = false"
        />
        <v-card-text>
          <v-autocomplete
            v-model="form.from"
            :items="cameraOptions"
            item-title="name"
            item-value="id"
            label="From Camera"
            variant="outlined"
            class="mb-3"
            hint="Camera the person departs from"
            persistent-hint
            clearable
          />
          <v-autocomplete
            v-model="form.to"
            :items="cameraOptions"
            item-title="name"
            item-value="id"
            label="To Camera"
            variant="outlined"
            class="mb-3"
            clearable
          />

          <!-- Overlap-group hint -->
          <v-alert
            v-if="sameOverlapGroupHint"
            type="info"
            density="compact"
            variant="tonal"
            class="mb-3"
          >
            These cameras share overlap group <strong>{{ sameOverlapGroupHint }}</strong>. Consider
            setting min transit = 0, max transit = 2 s.
            <v-btn size="x-small" variant="text" class="ml-2" @click="applyGroupDefaults">Apply</v-btn>
          </v-alert>

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
            Max transit must be at least min transit.
          </v-alert>

          <v-switch
            v-model="form.overlap"
            color="primary"
            label="Field-of-view overlap"
            density="compact"
            class="mt-3"
            hide-details
          />
          <div class="text-caption text-medium-emphasis mt-1">
            Enable when cameras physically share a viewing zone (e.g. two cameras covering the same doorway).
            The cross-camera resolver will treat detections as potentially simultaneous rather than sequential.
          </div>
        </v-card-text>
        <DialogFooter
          hint="Adjacency edges define which cameras are physically connected for person tracking across rooms."
          :confirm-label="editingIdx !== null ? 'Update' : 'Add'"
          :confirm-disabled="form.max_transit_s < form.min_transit_s || !form.from || !form.to || form.from === form.to"
          @cancel="dialog = false"
          @confirm="commitEdge"
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

const cameraOptions = ref([]);
const overlapGroups = ref([]);
const savedEdges = ref([]);
const loadingEdges = ref(false);
const stagedEdges = ref([]);
const dialog = ref(false);
const editingIdx = ref(null);
const saving = ref(false);

const baseHeaders = [
  { title: "From", key: "from" },
  { title: "To", key: "to" },
  { title: "Transit", key: "transit" },
  { title: "Overlap", key: "overlap" },
];

const savedHeaders = [
  ...baseHeaders,
  { title: "", key: "actions", sortable: false, align: "end" },
];

const editHeaders = [
  ...baseHeaders,
  { title: "", key: "actions", sortable: false, align: "end" },
];

const emptyForm = () => ({ from: "", to: "", min_transit_s: 0.5, max_transit_s: 30, overlap: false });
const form = ref(emptyForm());

// Overlap-group hint: returns group name if both selected cameras share a group.
const sameOverlapGroupHint = computed(() => {
  if (!form.value.from || !form.value.to) return null;
  for (const grp of overlapGroups.value) {
    const ids = grp.camera_ids || [];
    if (ids.includes(form.value.from) && ids.includes(form.value.to)) {
      return grp.name || `Group ${grp.id}`;
    }
  }
  return null;
});

function applyGroupDefaults() {
  form.value.min_transit_s = 0;
  form.value.max_transit_s = 2;
}

async function loadCameras() {
  try {
    cameraOptions.value = await cts.getCameras();
  } catch {
    // orchestrator may be offline in dev
  }
}

async function loadOverlapGroups() {
  try {
    overlapGroups.value = await cts.getOverlapGroups();
  } catch {
    overlapGroups.value = [];
  }
}

async function loadSavedEdges() {
  loadingEdges.value = true;
  try {
    const data = await cts.getAdjacency();
    savedEdges.value = (data.edges || []).map((e) => ({
      ...e,
      _key: `${e.from}->${e.to}`,
    }));
  } catch {
    savedEdges.value = [];
  } finally {
    loadingEdges.value = false;
  }
}

function openCreate() {
  editingIdx.value = null;
  form.value = emptyForm();
  dialog.value = true;
}

function openEdit(edge) {
  editingIdx.value = stagedEdges.value.indexOf(edge);
  form.value = { ...edge };
  dialog.value = true;
}

function stageForEdit(savedEdge) {
  // Move a saved (orchestrator) edge into the staged list so it can be edited.
  // If it's already staged, just open the edit dialog for it.
  const existingIdx = stagedEdges.value.findIndex(
    (e) => e.from === savedEdge.from && e.to === savedEdge.to
  );
  if (existingIdx >= 0) {
    editingIdx.value = existingIdx;
    form.value = { ...stagedEdges.value[existingIdx] };
  } else {
    const staged = { ...savedEdge };
    stagedEdges.value.push(staged);
    editingIdx.value = stagedEdges.value.length - 1;
    form.value = { ...staged };
  }
  dialog.value = true;
}

function commitEdge() {
  const edge = { ...form.value, _key: `${form.value.from}->${form.value.to}` };
  if (editingIdx.value !== null) {
    stagedEdges.value[editingIdx.value] = edge;
  } else {
    stagedEdges.value.push(edge);
  }
  dialog.value = false;
}

function removeEdge(edge) {
  stagedEdges.value = stagedEdges.value.filter((e) => e !== edge);
}

async function saveAdjacency() {
  saving.value = true;
  try {
    const payload = stagedEdges.value.map(({ _key: _k, ...rest }) => rest);
    await cts.postAdjacency(payload);
    notify("Adjacency graph saved");
    stagedEdges.value = [];
    await loadSavedEdges();
  } catch (e) {
    notify(e.message, "error");
  } finally {
    saving.value = false;
  }
}

onMounted(() => {
  loadCameras();
  loadOverlapGroups();
  loadSavedEdges();
});
</script>
