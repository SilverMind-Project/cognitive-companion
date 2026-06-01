<template>
  <div>
    <div class="d-flex align-center flex-wrap ga-3 mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Workflow Executions</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">Every pipeline run, in flight or finished.</div>
      </div>
      <v-spacer />
      <v-select
        v-model="filter.status"
        :items="['', 'running', 'waiting', 'completed', 'failed', 'cancelled']"
        label="Status"
        variant="outlined"
        density="compact"
        clearable
        hide-details
        style="max-width: 200px"
        @update:model-value="load"
      />
      <v-btn variant="tonal" prepend-icon="mdi-refresh" @click="load">Refresh</v-btn>
    </div>

    <v-card class="glass-card">
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
          {{ formatDateTime(item.started_at) }}
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
        <template #no-data>
          <div class="pa-6 text-center">
            <v-card flat>
              <v-card-text class="text-grey text-h6">No executions yet</v-card-text>
              <v-card-text class="text-grey">Workflow executions will appear here once rules are triggered.</v-card-text>
            </v-card>
          </div>
        </template>
      </v-data-table>
    </v-card>

    <!-- Detail dialog -->
    <v-dialog v-model="detailOpen" max-width="1100" scrollable>
      <v-card v-if="detail">
        <v-card-title class="d-flex align-center">
          Execution #{{ detail.id }}
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" @click="detailOpen = false" />
        </v-card-title>
        <v-card-text>
          <ExecutionInspector
            v-if="detail"
            :execution-id="detail.id"
            source="historic"
            :rule-id="detail.rule_id"
            @rerun="rerunDetail"
          />
        </v-card-text>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { api } from "../../services/api.js";
import { formatDateTime, DATETIME_COLUMN_WIDTH } from "../../services/timezone.js";
import ExecutionInspector from "../../components/pipeline/ExecutionInspector.vue";
import { useNotify } from "../../composables/useNotify.js";

const router = useRouter();
const { notify } = useNotify();

const items = ref([]);
const loading = ref(false);
const filter = ref({ status: "" });
const detailOpen = ref(false);
const detail = ref(null);

const headers = [
  { title: "ID", key: "id", width: 80 },
  { title: "Rule", key: "rule_name" },
  { title: "Status", key: "status" },
  { title: "Started", key: "started_at", width: DATETIME_COLUMN_WIDTH },
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
    detail.value = await api.getWorkflowDetail(item.id);
    detailOpen.value = true;
  } catch (e) { console.error("Failed to load workflow detail:", e); }
}

async function rerunDetail() {
  if (!detail.value) return;
  try {
    const result = await api.rerunWorkflow(detail.value.id);
    notify.success(`Rerun started (#${result.execution_id})`);
    detailOpen.value = false;
    router.push(`/admin/rules/${detail.value.rule_id || ""}`);
  } catch (e) {
    notify.error("Rerun failed: " + (e.message || "Unknown error"));
  }
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

onMounted(load);
</script>

<style scoped>
.tracking-tight {
  letter-spacing: -0.018em;
}
</style>
