<template>
  <div>
    <div class="mb-6">
      <h2 class="text-h4 font-weight-bold tracking-tight">Interactive Responses</h2>
      <div class="text-body-2 text-medium-emphasis mt-1">
        Audit trail of user responses to interactive prompts in pipeline executions.
      </div>
    </div>

    <v-card>
      <v-card-text>
        <v-row>
          <v-col cols="12" sm="3">
            <v-select
              v-model="filter.channel"
              :items="channelOptions"
              label="Channel"
              variant="outlined"
              @update:model-value="loadResponses"
            />
          </v-col>
          <v-col cols="12" sm="3">
            <v-select
              v-model="filter.action"
              :items="actionOptions"
              label="Action"
              variant="outlined"
              @update:model-value="loadResponses"
            />
          </v-col>
          <v-col cols="12" sm="3">
            <v-text-field
              v-model="filter.date_from"
              label="From Date"
              type="date"
              variant="outlined"
              @update:model-value="loadResponses"
            />
          </v-col>
          <v-col cols="12" sm="3">
            <v-text-field
              v-model="filter.date_to"
              label="To Date"
              type="date"
              variant="outlined"
              @update:model-value="loadResponses"
            />
          </v-col>
        </v-row>
      </v-card-text>

      <v-data-table
        :headers="headers"
        :items="responses"
        :loading="loading"
        :items-per-page="25"
        item-value="id"
      >
        <template #item.timestamp="{ item }">
          {{ formatDate(item.timestamp) }}
        </template>
        <template #item.channel="{ item }">
          <v-chip :color="getChannelColor(item.channel)" size="small" variant="tonal">
            {{ item.channel }}
          </v-chip>
        </template>
        <template #item.action="{ item }">
          <v-chip :color="getActionColor(item.action)" size="small" variant="tonal">
            {{ item.action }}
          </v-chip>
        </template>
        <template #item.latency_ms="{ item }">
          <span v-if="item.latency_ms">{{ formatLatency(item.latency_ms) }}</span>
          <span v-else class="text-medium-emphasis">—</span>
        </template>
        <template #item.execution_id="{ item }">
          <a
            :href="`/admin/workflows/executions/${item.execution_id}`"
            class="text-primary text-decoration-none"
            @click.prevent="navigateToExecution(item.execution_id)"
          >
            {{ item.execution_id }}
          </a>
        </template>
        <template #item.user_statement="{ item }">
          <span v-if="item.raw_response_json?.user_statement" class="text-truncate" style="max-width: 200px; display: inline-block;">
            {{ item.raw_response_json.user_statement }}
          </span>
          <span v-else class="text-medium-emphasis">—</span>
        </template>
      </v-data-table>
    </v-card>

    <v-snackbar v-model="snack" :color="snackColor" timeout="3000">
      {{ snackText }}
    </v-snackbar>
  </div>
</template>

<style scoped>
.tracking-tight {
  letter-spacing: -0.018em;
}
</style>

<script setup>
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { api } from "../../services/api.js";
import { useNotify } from "../../composables/useNotify.js";
import { formatDateTime } from "../../services/timezone.js";

const router = useRouter();
const { snack, snackText, snackColor, notify } = useNotify();

const responses = ref([]);
const loading = ref(false);
const filter = ref({
  channel: "",
  action: "",
  date_from: "",
  date_to: "",
});

const channelOptions = [
  { title: "All Channels", value: "" },
  { title: "Popup", value: "pwa_popup_text" },
  { title: "Voice", value: "pwa_realtime_ai" },
  { title: "Timeout", value: "timeout" },
];

const actionOptions = [
  { title: "All Actions", value: "" },
  { title: "Escalate", value: "escalate" },
  { title: "Dismiss", value: "dismiss" },
];

const headers = [
  { title: "Time", key: "timestamp", width: 180 },
  { title: "Execution", key: "execution_id", width: 120 },
  { title: "Step", key: "step_id", width: 100 },
  { title: "Channel", key: "channel", width: 140 },
  { title: "Action", key: "action", width: 120 },
  { title: "Latency", key: "latency_ms", width: 100 },
  { title: "User Statement", key: "user_statement" },
];

const formatDate = formatDateTime;

function formatLatency(ms) {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function getChannelColor(channel) {
  switch (channel) {
    case "pwa_popup_text":
      return "blue";
    case "pwa_realtime_ai":
      return "purple";
    case "timeout":
      return "orange";
    default:
      return "grey";
  }
}

function getActionColor(action) {
  switch (action) {
    case "escalate":
      return "error";
    case "dismiss":
      return "success";
    default:
      return "grey";
  }
}

function navigateToExecution(executionId) {
  router.push(`/admin/workflows/executions/${executionId}`);
}

async function loadResponses() {
  loading.value = true;
  const params = {};
  
  if (filter.value.channel) params.channel = filter.value.channel;
  if (filter.value.action) params.action = filter.value.action;
  if (filter.value.date_from) params.date_from = filter.value.date_from;
  if (filter.value.date_to) params.date_to = filter.value.date_to;
  
  try {
    responses.value = await api.getInteractiveResponses(params);
  } catch (e) {
    console.error("Failed to load interactive responses:", e);
    notify(e.message, "error");
    responses.value = [];
  }
  
  loading.value = false;
}

onMounted(loadResponses);
</script>
