<template>
  <div>
    <div class="d-flex align-center flex-wrap ga-3 mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Guided Sessions</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Monitor and manage active guided task sessions.
        </div>
      </div>
      <v-spacer />
      <v-select
        v-model="filterStatus"
        :items="statusOptions"
        label="Status"
        density="compact"
        hide-details
        clearable
        style="max-width: 200px"
        @update:model-value="
          page = 1;
          fetchSessions();
        "
      />
      <v-select
        v-model="filterPersonId"
        :items="personItems"
        item-title="name"
        item-value="id"
        label="Member"
        density="compact"
        hide-details
        clearable
        style="max-width: 200px"
        @update:model-value="
          page = 1;
          fetchSessions();
        "
      />
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
        @click:row="(_ev, { item }) => goToConsole(item.id)"
        @update:options="onPageOptions"
      >
        <template #item.status="{ item }">
          <v-chip :color="statusColor(item.status)" size="small" variant="tonal">
            {{ item.status }}
          </v-chip>
        </template>
        <template #item.started_at="{ item }">
          <span class="font-mono text-caption">{{ formatDateTime(item.started_at) }}</span>
        </template>
        <template #item.actions="{ item }">
          <v-btn
            icon="mdi-monitor-eye"
            variant="text"
            size="small"
            title="Open console"
            @click.stop="goToConsole(item.id)"
          />
        </template>
        <template #no-data>
          <div class="pa-6 text-center">
            <v-card flat>
              <v-card-text class="text-grey text-h6">No sessions yet</v-card-text>
              <v-card-text class="text-grey">
                Sessions appear here when a guided routine is triggered.
              </v-card-text>
            </v-card>
          </div>
        </template>
      </v-data-table>
    </v-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { api } from "@/services/api.js";
import { useNotify } from "@/composables/useNotify.js";
import { formatDateTime } from "@/services/timezone.js";

const router = useRouter();
const { notify } = useNotify();

const headers = [
  { title: "ID", key: "id", width: 80 },
  { title: "Person", key: "person_id" },
  { title: "Routine", key: "routine_id", width: 100 },
  { title: "Status", key: "status", width: 160 },
  { title: "Step", key: "current_step_ord", width: 80 },
  { title: "Started", key: "started_at" },
  { title: "", key: "actions", width: 60, sortable: false },
];

const statusOptions = [
  "pending",
  "summoning",
  "active",
  "waiting",
  "escalated",
  "caregiver_takeover",
  "completed",
  "abandoned",
  "failed",
];

const items = ref([]);
const totalItems = ref(0);
const itemsPerPage = ref(20);
const page = ref(1);
const loading = ref(false);
const filterStatus = ref(null);
const filterPersonId = ref(null);
const personItems = ref([]);

function statusColor(status) {
  const map = {
    active: "success",
    waiting: "info",
    escalated: "warning",
    caregiver_takeover: "warning",
    completed: "success",
    abandoned: undefined,
    failed: "error",
    summoning: "info",
    pending: undefined,
  };
  return map[status];
}

function onPageOptions({ page: newPage, itemsPerPage: newPerPage }) {
  if (newPerPage !== itemsPerPage.value) {
    itemsPerPage.value = newPerPage;
    page.value = 1;
  } else {
    page.value = newPage;
  }
  fetchSessions();
}

async function fetchSessions() {
  loading.value = true;
  try {
    const params = {
      limit: itemsPerPage.value,
      offset: (page.value - 1) * itemsPerPage.value,
    };
    if (filterStatus.value) params.status = filterStatus.value;
    if (filterPersonId.value) params.person_id = filterPersonId.value;
    const res = await api.listGuidedSessions(params);
    items.value = res.items ?? [];
    totalItems.value = res.total ?? 0;
  } catch (err) {
    notify.error("Failed to load sessions: " + (err.message || err));
  } finally {
    loading.value = false;
  }
}

async function fetchPersons() {
  try {
    personItems.value = (await api.getPersons()) ?? [];
  } catch {
    // non-fatal
  }
}

function goToConsole(id) {
  router.push({ name: "admin-guided-session-console", params: { id } });
}

onMounted(() => {
  fetchPersons();
  fetchSessions();
});
</script>
