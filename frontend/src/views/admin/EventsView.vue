<template>
  <div>
    <h2 class="text-h5 mb-4">Event Logs</h2>

    <v-card rounded="xl">
      <v-card-text>
        <v-row>
          <v-col cols="12" sm="4">
            <v-select v-model="filter.status" :items="['', 'completed', 'failed', 'ignored', 'processing']" label="Status" variant="outlined" clearable @update:model-value="loadEvents" />
          </v-col>
          <v-col cols="12" sm="4">
            <v-text-field v-model="filter.rule_name" label="Rule Name" variant="outlined" clearable @keyup.enter="loadEvents" />
          </v-col>
          <v-col cols="12" sm="4" class="d-flex align-center">
            <v-btn color="primary" @click="loadEvents">Filter</v-btn>
          </v-col>
        </v-row>
      </v-card-text>

      <v-data-table :headers="headers" :items="events" :loading="loading" item-value="id">
        <template #item.status="{ item }">
          <v-chip :color="statusColor(item.status)" size="small">{{ item.status }}</v-chip>
        </template>
        <template #item.timestamp="{ item }">
          {{ formatDate(item.timestamp) }}
        </template>
      </v-data-table>
    </v-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { api } from "../../services/api.js";

const events = ref([]);
const loading = ref(false);
const filter = ref({ status: "", rule_name: "" });

const headers = [
  { title: "Time", key: "timestamp" },
  { title: "Rule", key: "rule_name" },
  { title: "Room", key: "room_name" },
  { title: "Trigger", key: "trigger_type" },
  { title: "Status", key: "status" },
];

function statusColor(s) {
  return { completed: "success", failed: "error", ignored: "grey", processing: "info" }[s] || "grey";
}

function formatDate(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString();
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
