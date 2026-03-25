<template>
  <div>
    <div class="d-flex align-center mb-4">
      <h2 class="text-h5">Workflow Executions</h2>
      <v-spacer />
      <v-btn icon="mdi-refresh" variant="text" @click="load" />
    </div>

    <v-card rounded="xl" class="mb-4">
      <v-card-text class="d-flex ga-3">
        <v-select
          v-model="filter.status"
          :items="['', 'running', 'waiting', 'completed', 'failed', 'cancelled']"
          label="Status"
          variant="outlined"
          density="compact"
          clearable
          style="max-width: 200px"
          @update:model-value="load"
        />
      </v-card-text>
    </v-card>

    <v-card rounded="xl">
      <v-data-table
        :headers="headers"
        :items="items"
        :loading="loading"
        item-value="id"
        @click:row="(_, { item }) => openDetail(item)"
        hover
      >
        <template #item.status="{ item }">
          <v-chip :color="statusColor(item.status)" size="small">{{ item.status }}</v-chip>
        </template>
        <template #item.started_at="{ item }">
          {{ formatDate(item.started_at) }}
        </template>
        <template #item.actions="{ item }">
          <v-btn
            v-if="item.status === 'running' || item.status === 'waiting'"
            icon="mdi-stop"
            size="x-small"
            variant="text"
            color="error"
            @click.stop="cancel(item.id)"
          />
        </template>
      </v-data-table>
    </v-card>

    <!-- Detail dialog -->
    <v-dialog v-model="detailOpen" max-width="700" scrollable>
      <v-card v-if="detail" rounded="xl">
        <v-card-title>Execution #{{ detail.id }}</v-card-title>
        <v-card-text>
          <v-list density="compact">
            <v-list-item>
              <v-list-item-title>Rule</v-list-item-title>
              <v-list-item-subtitle>{{ detail.rule_name }} (#{{ detail.rule_id }})</v-list-item-subtitle>
            </v-list-item>
            <v-list-item>
              <v-list-item-title>Status</v-list-item-title>
              <v-list-item-subtitle>
                <v-chip :color="statusColor(detail.status)" size="small">{{ detail.status }}</v-chip>
              </v-list-item-subtitle>
            </v-list-item>
            <v-list-item v-if="detail.error">
              <v-list-item-title>Error</v-list-item-title>
              <v-list-item-subtitle class="text-error">{{ detail.error }}</v-list-item-subtitle>
            </v-list-item>
          </v-list>
          <v-divider class="my-3" />
          <h4 class="text-subtitle-2 mb-2">Pipeline Data</h4>
          <pre class="text-body-2 bg-grey-lighten-4 pa-3 rounded overflow-auto" style="max-height: 400px">{{ JSON.stringify(detail.pipeline_data_json, null, 2) }}</pre>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="detailOpen = false">Close</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { api } from "../../services/api.js";

const items = ref([]);
const loading = ref(false);
const filter = ref({ status: "" });
const detailOpen = ref(false);
const detail = ref(null);

const headers = [
  { title: "ID", key: "id", width: 80 },
  { title: "Rule", key: "rule_name" },
  { title: "Status", key: "status" },
  { title: "Started", key: "started_at" },
  { title: "", key: "actions", sortable: false, width: 60 },
];

async function load() {
  loading.value = true;
  try {
    const params = {};
    if (filter.value.status) params.status = filter.value.status;
    items.value = await api.getWorkflows(params);
  } catch (e) {
    console.error("Failed to load workflows:", e);
    items.value = [];
  }
  loading.value = false;
}

async function openDetail(item) {
  try {
    detail.value = await api.getWorkflow(item.id);
    detailOpen.value = true;
  } catch (e) { console.error("Failed to load workflow detail:", e); }
}

async function cancel(id) {
  try {
    await api.cancelWorkflow(id);
    await load();
  } catch (e) { console.error("Failed to cancel workflow:", e); }
}

function statusColor(status) {
  const map = { completed: "success", failed: "error", running: "info", waiting: "warning", cancelled: "grey" };
  return map[status] || "grey";
}

function formatDate(iso) {
  return iso ? new Date(iso).toLocaleString() : "";
}

onMounted(load);
</script>
