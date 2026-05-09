<template>
  <div>
    <div class="d-flex align-center flex-wrap ga-3 mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Emergency Alerts</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">Active and resolved alerts raised by the system.</div>
      </div>
      <v-spacer />
      <v-select
        v-model="filter.resolved"
        :items="[{title:'All', value:''},{title:'Active', value:'false'},{title:'Resolved', value:'true'}]"
        label="Status"
        variant="outlined"
        density="compact"
        hide-details
        style="max-width: 180px"
        @update:model-value="loadAlerts"
      />
      <v-btn variant="tonal" prepend-icon="mdi-refresh" @click="loadAlerts" :loading="loading">
        Refresh
      </v-btn>
    </div>

    <v-card class="glass-card">
      <v-data-table :headers="headers" :items="alerts" :loading="loading" item-value="id">
        <template #item.resolved="{ item }">
          <v-chip :color="item.resolved ? 'success' : 'error'" size="small">
            {{ item.resolved ? 'Resolved' : 'Active' }}
          </v-chip>
        </template>
        <template #item.timestamp="{ item }">
          {{ formatDateTime(item.timestamp) }}
        </template>
        <template #item.actions="{ item }">
          <v-btn v-if="!item.resolved" size="small" variant="tonal" color="success" @click="dismiss(item.id)">
            Dismiss
          </v-btn>
        </template>
        <template #no-data>
          <div class="pa-6 text-center">
            <v-card flat>
              <v-card-text class="text-grey text-h6">No alerts yet</v-card-text>
              <v-card-text class="text-grey">Alerts will appear here when rules detect conditions that need attention.</v-card-text>
            </v-card>
          </div>
        </template>
      </v-data-table>
    </v-card>
    <v-snackbar v-model="snack" :color="snackColor" timeout="3000">{{ snackText }}</v-snackbar>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { api } from "../../services/api.js";
import { useNotify } from "../../composables/useNotify.js";
import { formatDateTime, DATETIME_COLUMN_WIDTH } from "../../services/timezone.js";

const { snack, snackText, snackColor, notify } = useNotify();

const alerts = ref([]);
const loading = ref(false);
const filter = ref({ resolved: "" });

const headers = [
  { title: "Time", key: "timestamp", width: DATETIME_COLUMN_WIDTH },
  { title: "Type", key: "alert_type" },
  { title: "Room", key: "room_name" },
  { title: "Description", key: "description" },
  { title: "Status", key: "resolved" },
  { title: "Actions", key: "actions", sortable: false },
];

async function loadAlerts() {
  loading.value = true;
  const params = {};
  if (filter.value.resolved) params.resolved = filter.value.resolved;
  try { alerts.value = await api.getAlerts(params); } catch (e) { console.error("Failed to load alerts:", e); alerts.value = []; }
  loading.value = false;
}

async function dismiss(id) {
  try {
    await api.alertAction(id, { action: "dismiss" });
    await loadAlerts();
  } catch (e) { notify(e.message, "error"); }
}

onMounted(loadAlerts);
</script>
