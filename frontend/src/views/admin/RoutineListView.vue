<template>
  <div>
    <div class="d-flex align-center flex-wrap ga-3 mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Routines</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Author and manage guided task routines for household members.
        </div>
      </div>
      <v-spacer />
      <v-select
        v-model="filterPersonId"
        :items="personItems"
        item-title="name"
        item-value="id"
        label="Member"
        density="compact"
        hide-details
        clearable
        style="max-width: 220px"
        @update:model-value="
          page = 1;
          fetchRoutines();
        "
      />
      <v-btn color="primary" variant="flat" prepend-icon="mdi-plus" @click="openCreate">
        New Routine
      </v-btn>
    </div>

    <v-card class="glass-card">
      <v-data-table
        :headers="headers"
        :items="items"
        :loading="loading"
        :items-length="totalItems"
        :items-per-page="itemsPerPage"
        :page="page"
        item-value="id"
        hover
        @click:row="(_ev, { item }) => goToBuilder(item.id)"
        @update:options="onPageOptions"
      >
        <template #item.is_enabled="{ item }">
          <v-chip :color="item.is_enabled ? 'success' : undefined" size="small" variant="tonal">
            {{ item.is_enabled ? "Enabled" : "Disabled" }}
          </v-chip>
        </template>
        <template #item.step_count="{ item }">
          {{ item.step_count }} step{{ item.step_count !== 1 ? "s" : "" }}
        </template>
        <template #item.actions="{ item }">
          <v-btn
            icon="mdi-pencil-outline"
            variant="text"
            size="small"
            @click.stop="goToBuilder(item.id)"
          />
          <v-btn
            icon="mdi-delete-outline"
            variant="text"
            size="small"
            color="error"
            @click.stop="confirmDelete(item)"
          />
        </template>
        <template #no-data>
          <div class="pa-6 text-center">
            <v-card flat>
              <v-card-text class="text-grey text-h6">No routines yet</v-card-text>
              <v-card-text class="text-grey">
                Create a routine to start guiding household members through tasks.
              </v-card-text>
            </v-card>
          </div>
        </template>
      </v-data-table>
    </v-card>

    <!-- Create dialog -->
    <v-dialog v-model="showCreate" max-width="600" persistent>
      <v-card>
        <v-card-title>New Routine</v-card-title>
        <v-card-text>
          <v-select
            v-model="createForm.person_id"
            :items="personItems"
            item-title="name"
            item-value="id"
            label="Household Member"
            :rules="[(r) => !!r || 'Required']"
          />
          <v-text-field
            v-model="createForm.name"
            label="Routine Name"
            :rules="[(r) => !!r || 'Required']"
            placeholder="e.g. Morning Tea"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="closeCreate">Cancel</v-btn>
          <v-btn
            color="primary"
            variant="flat"
            :loading="creating"
            :disabled="!createForm.name || !createForm.person_id"
            @click="submitCreate"
          >
            Create
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Confirm delete dialog -->
    <v-dialog v-model="confirmDialog" max-width="400" persistent>
      <v-card rounded="xl">
        <v-card-title>Delete Routine</v-card-title>
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
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { api } from "@/services/api.js";
import { useNotify } from "@/composables/useNotify.js";
import { useConfirm } from "@/composables/useConfirm.js";

const router = useRouter();
const { notify } = useNotify();
const { confirmDialog, confirmText, require: confirmRequire, onConfirm, onCancel } = useConfirm();

const headers = [
  { title: "Name", key: "name" },
  { title: "Member", key: "person_id" },
  { title: "Steps", key: "step_count", width: 100 },
  { title: "Status", key: "is_enabled", width: 110 },
  { title: "", key: "actions", width: 100, sortable: false },
];

const items = ref([]);
const totalItems = ref(0);
const itemsPerPage = ref(20);
const page = ref(1);
const loading = ref(false);
const filterPersonId = ref(null);
const personItems = ref([]);

// Create form
const showCreate = ref(false);
const creating = ref(false);
const createForm = ref({ name: "", person_id: "" });

function onPageOptions({ page: newPage, itemsPerPage: newPerPage }) {
  if (newPerPage !== itemsPerPage.value) {
    itemsPerPage.value = newPerPage;
    page.value = 1;
  } else {
    page.value = newPage;
  }
  fetchRoutines();
}

async function fetchRoutines() {
  loading.value = true;
  try {
    const params = {
      limit: itemsPerPage.value,
      offset: (page.value - 1) * itemsPerPage.value,
    };
    if (filterPersonId.value) params.person_id = filterPersonId.value;
    const res = await api.listRoutines(params);
    items.value = res.items ?? [];
    totalItems.value = res.total ?? 0;
  } catch (err) {
    notify.error("Failed to load routines: " + (err.message || err));
  } finally {
    loading.value = false;
  }
}

async function fetchPersons() {
  try {
    const data = await api.getPersons();
    personItems.value = data ?? [];
  } catch {
    // non-fatal
  }
}

function goToBuilder(id) {
  router.push({ name: "admin-routine-builder", params: { id } });
}

function openCreate() {
  createForm.value = { name: "", person_id: "" };
  showCreate.value = true;
}

function closeCreate() {
  showCreate.value = false;
}

async function submitCreate() {
  creating.value = true;
  try {
    const routine = await api.createRoutine({
      name: createForm.value.name,
      person_id: createForm.value.person_id,
    });
    showCreate.value = false;
    notify.success("Routine created.");
    router.push({ name: "admin-routine-builder", params: { id: routine.id } });
  } catch (err) {
    notify.error("Failed to create: " + (err.message || err));
  } finally {
    creating.value = false;
  }
}

async function confirmDelete(item) {
  const ok = await confirmRequire(`Delete routine "${item.name}"? This cannot be undone.`);
  if (!ok) return;
  try {
    await api.deleteRoutine(item.id);
    notify.success("Routine deleted.");
    fetchRoutines();
  } catch (err) {
    notify.error("Failed to delete: " + (err.message || err));
  }
}

onMounted(() => {
  fetchPersons();
  fetchRoutines();
});
</script>
