<template>
  <div>
    <div class="d-flex align-center flex-wrap ga-3 mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Event Logs</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">A history of every trigger the system has processed.</div>
      </div>
      <v-spacer />
      <v-select
        v-model="filter.status"
        :items="['', 'completed', 'failed', 'ignored', 'processing']"
        label="Status"
        variant="outlined"
        density="compact"
        clearable
        hide-details
        style="max-width: 180px"
        @update:model-value="loadEvents"
      />
      <v-text-field
        v-model="filter.rule_name"
        label="Rule Name"
        variant="outlined"
        density="compact"
        clearable
        hide-details
        style="max-width: 200px"
        @keyup.enter="loadEvents"
      />
      <v-btn variant="tonal" prepend-icon="mdi-refresh" @click="loadEvents" :loading="loading">
        Refresh
      </v-btn>
    </div>

    <v-card class="glass-card">
      <v-data-table :headers="headers" :items="events" :loading="loading" item-value="id">
        <template #item.status="{ item }">
          <v-chip :color="statusColor(item.status)" size="small">{{ item.status }}</v-chip>
        </template>
        <template #item.timestamp="{ item }">
          {{ formatDateTime(item.timestamp) }}
        </template>
        <template #no-data>
          <div class="pa-6 text-center">
            <v-card flat>
              <v-card-text class="text-grey text-h6">No events yet</v-card-text>
              <v-card-text class="text-grey">System events will appear here as rules execute and actions are triggered.</v-card-text>
            </v-card>
          </div>
        </template>
      </v-data-table>
    </v-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { api } from "../../services/api.js";
import { formatDateTime, DATETIME_COLUMN_WIDTH } from "../../services/timezone.js";

const events = ref([]);
const loading = ref(false);
const filter = ref({ status: "", rule_name: "" });

const headers = [
  { title: "Time", key: "timestamp", width: DATETIME_COLUMN_WIDTH },
  { title: "Rule", key: "rule_name" },
  { title: "Room", key: "room_name" },
  { title: "Trigger", key: "trigger_type" },
  { title: "Status", key: "status" },
];

function statusColor(s) {
  return { completed: "success", failed: "error", ignored: "grey", processing: "info" }[s] || "grey";
}

async function loadEvents() {
  loading.value = true;
  const params = {};
  if (filter.value.status) params.status = filter.value.status;
  if (filter.value.rule_name) params.rule_name = filter.value.rule_name;
  try { events.value = await api.getEvents(params); } catch (e) { console.error("Failed to load events:", e); events.value = []; }
  loading.value = false;
}

onMounted(loadEvents);
</script>
