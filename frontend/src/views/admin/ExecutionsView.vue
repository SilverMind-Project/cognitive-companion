<template>
  <div>
    <div class="d-flex align-center flex-wrap ga-3 mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Executions</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          {{ pageDescription }}
        </div>
      </div>
      <v-spacer />
      <v-chip
        v-if="scopedRuleId"
        size="small"
        variant="tonal"
        prepend-icon="mdi-filter-outline"
        data-testid="rule-scope-chip"
      >
        {{ scopedRuleName || `Rule #${scopedRuleId}` }}
      </v-chip>
      <v-btn
        v-if="scopedRuleId"
        size="small"
        variant="text"
        prepend-icon="mdi-pencil-outline"
        :to="{
          name: 'admin-rule-detail',
          params: { id: scopedRuleId },
          query: { tab: 'executions' },
        }"
      >
        Rule
      </v-btn>
      <v-btn
        v-if="scopedRuleId"
        size="small"
        variant="text"
        prepend-icon="mdi-filter-remove-outline"
        @click="clearRuleScope"
      >
        All rules
      </v-btn>
      <v-chip
        :color="wsColor"
        size="small"
        variant="tonal"
        :prepend-icon="wsIcon"
        data-testid="connection-chip"
      >
        {{ connectionState }}
      </v-chip>
      <v-btn size="small" variant="outlined" prepend-icon="mdi-refresh" @click="refresh">
        Refresh
      </v-btn>
    </div>

    <v-alert
      v-if="connectionState === 'error' || connectionState === 'closed'"
      type="warning"
      variant="tonal"
      density="compact"
      class="mb-4"
      data-testid="stream-interrupted-alert"
    >
      Live stream interrupted. Attempting to reconnect...
    </v-alert>

    <v-tabs v-model="activeTab" color="primary" class="mb-4">
      <v-tab value="live">Live</v-tab>
      <v-tab value="history">History</v-tab>
      <v-tab value="ingest">Ingest</v-tab>
    </v-tabs>

    <v-window v-model="activeTab">
      <v-window-item value="live">
        <v-row>
          <v-col cols="12" md="4">
            <v-card class="glass-card">
              <v-card-title class="text-subtitle-1">
                Active Runs
                <v-chip v-if="activeRuns.length" size="x-small" color="primary" class="ml-2">
                  {{ activeRuns.length }}
                </v-chip>
              </v-card-title>
              <v-card-text v-if="!activeRuns.length" class="text-medium-emphasis">
                No active pipeline runs.
              </v-card-text>
              <v-list v-else density="compact">
                <v-list-item
                  v-for="run in activeRuns"
                  :key="run.execution_id"
                  :active="selectedExecutionId === run.execution_id"
                  :title="run.rule_name"
                  :subtitle="runSubtitle(run)"
                  data-testid="run-item"
                  @click="selectRun(run, 'live')"
                />
              </v-list>
            </v-card>

            <v-card class="glass-card mt-3">
              <v-card-title class="text-subtitle-1">Recent</v-card-title>
              <v-card-text v-if="loadingRecent" class="text-center">
                <v-progress-circular indeterminate size="24" />
              </v-card-text>
              <v-list v-else density="compact">
                <v-list-item
                  v-for="run in recentRuns"
                  :key="run.execution_id"
                  :active="selectedExecutionId === run.execution_id"
                  :title="run.rule_name"
                  :subtitle="runSubtitle(run)"
                  data-testid="recent-run-item"
                  @click="
                    selectRun(
                      run,
                      run.status === 'running' || run.status === 'waiting' ? 'live' : 'historic',
                    )
                  "
                />
              </v-list>
              <v-card-text v-if="!loadingRecent && !recentRuns.length" class="text-medium-emphasis">
                No recent executions.
              </v-card-text>
            </v-card>
          </v-col>

          <v-col cols="12" md="8">
            <ExecutionInspector
              v-if="activeTab === 'live'"
              :execution-id="selectedExecutionId"
              :source="selectedSource"
              :rule-id="selectedRun?.rule_id || null"
              :live-run="selectedRun"
              @rerun="handleRerun"
              @updated="handleInspectorUpdated"
            />
          </v-col>
        </v-row>
      </v-window-item>

      <v-window-item value="history">
        <div class="d-flex align-center flex-wrap ga-3 mb-3">
          <v-select
            v-model="filter.status"
            :items="['', 'running', 'waiting', 'completed', 'failed', 'cancelled']"
            label="Status"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="max-width: 200px"
            @update:model-value="loadHistory"
          />
          <v-spacer />
          <v-btn variant="tonal" prepend-icon="mdi-refresh" @click="loadHistory">Refresh</v-btn>
        </div>

        <v-card class="glass-card">
          <v-data-table
            :headers="historyHeaders"
            :items="historyItems"
            :loading="loadingHistory"
            item-value="id"
            hover
            data-testid="history-table"
            @click:row="(_, { item }) => selectHistory(item)"
          >
            <template #item.status="{ item }">
              <v-chip :color="statusColor(item.status)" size="small">{{ item.status }}</v-chip>
            </template>
            <template #item.started_at="{ item }">
              {{ formatDateTime(item.started_at) }}
            </template>
            <template #item.completed_at="{ item }">
              {{ item.completed_at ? formatDateTime(item.completed_at) : "-" }}
            </template>
            <template #item.duration="{ item }">
              {{ formatDuration(item.started_at, item.completed_at) }}
            </template>
            <template #no-data>
              <div class="pa-6 text-center text-medium-emphasis">
                Workflow executions will appear here once rules are triggered.
              </div>
            </template>
          </v-data-table>
        </v-card>

        <ExecutionInspector
          v-if="activeTab === 'history'"
          class="mt-4"
          :execution-id="selectedExecutionId"
          :source="selectedSource"
          :rule-id="selectedRun?.rule_id || null"
          :live-run="selectedRun"
          @rerun="handleRerun"
          @updated="handleInspectorUpdated"
        />
      </v-window-item>

      <v-window-item value="ingest">
        <v-row>
          <v-col cols="6" sm="3">
            <CcMetricTile label="Frames / min" :value="framesPerMin" status="neutral" />
          </v-col>
          <v-col cols="6" sm="3">
            <CcMetricTile label="Rules triggered" :value="rulesTriggered" status="neutral" />
          </v-col>
          <v-col cols="6" sm="3">
            <CcMetricTile label="Active sensors" :value="activeSensors" status="neutral" />
          </v-col>
          <v-col cols="6" sm="3">
            <CcMetricTile label="Last ingest" :value="lastIngestAge" status="neutral" />
          </v-col>
        </v-row>

        <v-card class="glass-card mt-4" data-testid="ingest-feed-card">
          <v-card-title class="text-subtitle-1">Ingest Activity</v-card-title>
          <v-card-text class="pa-0">
            <CcLiveActivityFeed
              :events="feedEvents"
              :max-height="420"
              data-testid="cc-live-activity-feed"
            >
              <template #empty>
                No ingest activity yet. Events will appear when ReCameras push frames.
              </template>
            </CcLiveActivityFeed>
          </v-card-text>
        </v-card>

        <v-card class="glass-card mt-4">
          <v-card-title class="text-subtitle-1">Signal Trends</v-card-title>
          <v-card-text>
            <div style="height: 280px">
              <CcStatusTimeline
                :lanes="trendLanes"
                :events="trendEvents"
                :loading="loadingIngest"
              />
            </div>
          </v-card-text>
        </v-card>
      </v-window-item>
    </v-window>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useLivePipeline } from "@/composables/useLivePipeline.js";
import { useNotify } from "@/composables/useNotify.js";
import { api } from "@/services/api.js";
import { DATETIME_COLUMN_WIDTH, formatDateTime, formatDateTimeShort } from "@/services/timezone.js";
import CcLiveActivityFeed from "@/components/process/CcLiveActivityFeed.vue";
import CcStatusTimeline from "@/components/process/CcStatusTimeline.vue";
import CcMetricTile from "@/components/dashboard/CcMetricTile.vue";
import ExecutionInspector from "@/components/pipeline/ExecutionInspector.vue";

const route = useRoute();
const router = useRouter();
const { notify } = useNotify();
const {
  connectionState,
  activeRuns: allActiveRuns,
  ingestEvents,
  refresh: refreshSocket,
} = useLivePipeline();

const activeTab = ref(
  route.query.tab === "history" ? "history" : route.query.tab === "ingest" ? "ingest" : "live",
);
const selectedExecutionId = ref(route.query.execution ? Number(route.query.execution) : null);
const selectedSource = ref(activeTab.value === "live" ? "live" : "historic");
const selectedRun = ref(null);
const recentRuns = ref([]);
const historyItems = ref([]);
const ingestActivity = ref([]);
const loadingRecent = ref(false);
const loadingHistory = ref(false);
const loadingIngest = ref(false);
const filter = ref({ status: "" });
const scopedRuleId = computed(() => {
  const value = Number(route.query.rule_id);
  return Number.isInteger(value) && value > 0 ? value : null;
});
const activeRuns = computed(() =>
  scopedRuleId.value
    ? allActiveRuns.value.filter((run) => Number(run.rule_id) === scopedRuleId.value)
    : allActiveRuns.value,
);
const scopedRuleName = computed(
  () =>
    selectedRun.value?.rule_name ||
    activeRuns.value[0]?.rule_name ||
    recentRuns.value[0]?.rule_name ||
    historyItems.value[0]?.rule_name ||
    null,
);
const pageDescription = computed(() =>
  scopedRuleId.value
    ? `Live runs and execution history for ${scopedRuleName.value || `rule #${scopedRuleId.value}`}.`
    : "Live pipeline runs, execution history, and ingest activity.",
);

const historyHeaders = [
  { title: "ID", key: "id", width: 80 },
  { title: "Rule", key: "rule_name" },
  { title: "Status", key: "status" },
  { title: "Started", key: "started_at", width: DATETIME_COLUMN_WIDTH },
  { title: "Completed", key: "completed_at", width: DATETIME_COLUMN_WIDTH },
  { title: "Duration", key: "duration", sortable: false },
];

const wsColor = computed(() => {
  switch (connectionState.value) {
    case "open":
      return "success";
    case "connecting":
      return "warning";
    case "error":
    case "closed":
      return "error";
    default:
      return "grey";
  }
});

const wsIcon = computed(() => {
  switch (connectionState.value) {
    case "open":
      return "mdi-wifi";
    case "connecting":
      return "mdi-wifi-sync";
    default:
      return "mdi-wifi-off";
  }
});

const feedEvents = computed(() => {
  const fromRest = (ingestActivity.value || []).map((ev) => ({
    id: ev.id,
    timestamp: ev.timestamp,
    title:
      ev.event_type === "frame_received"
        ? `Frame from ${ev.sensor_id || "sensor"}`
        : `Rule triggered: ${ev.rule_name || "unknown"}`,
    description: ev.sensor_id || undefined,
    icon: ev.event_type === "frame_received" ? "mdi-camera" : "mdi-flash",
    color: ev.event_type === "frame_received" ? "teal" : "primary",
  }));

  const fromWs = ingestEvents.value
    .filter((event) => event.event_type === "pipeline_started")
    .map((event) => ({
      id: `ws-${event.execution_id}-${event.sequence}`,
      timestamp: event.started_at,
      title: `Pipeline started: ${event.rule_name}`,
      icon: "mdi-flash",
      color: "primary",
    }));

  return [...fromRest, ...fromWs].sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
});

const framesPerMin = computed(() => {
  const cutoff = Date.now() - 60_000;
  return ingestActivity.value.filter(
    (event) =>
      event.event_type === "frame_received" && new Date(event.timestamp).getTime() > cutoff,
  ).length;
});

const rulesTriggered = computed(
  () => ingestActivity.value.filter((event) => event.event_type === "rule_triggered").length,
);

const activeSensors = computed(
  () =>
    new Set(ingestActivity.value.filter((event) => event.sensor_id).map((event) => event.sensor_id))
      .size,
);

const lastIngestAge = computed(() => {
  if (!ingestActivity.value.length) return "-";
  return formatDateTimeShort(ingestActivity.value[0].timestamp);
});

const trendLanes = computed(() => [
  { id: "ingest", label: "Ingest" },
  { id: "rules", label: "Rules" },
]);

const trendEvents = computed(() =>
  (ingestActivity.value || []).map((event) => ({
    laneId: event.event_type === "frame_received" ? "ingest" : "rules",
    t: event.timestamp,
    label: event.event_type === "frame_received" ? "frame" : "rule",
  })),
);

watch(activeTab, (tab) => {
  router.replace({ query: { ...route.query, tab } });
  if (tab === "history") selectedSource.value = "historic";
});

watch(scopedRuleId, () => {
  loadRecentRuns();
  loadHistory();
});

function selectRun(run, source) {
  selectedRun.value = run;
  selectedExecutionId.value = run.execution_id;
  selectedSource.value = source;
  router.replace({ query: { ...route.query, tab: activeTab.value, execution: run.execution_id } });
}

function selectHistory(item) {
  selectedRun.value = {
    execution_id: item.id,
    rule_id: item.rule_id,
    rule_name: item.rule_name,
    status: item.status,
  };
  selectedExecutionId.value = item.id;
  selectedSource.value =
    item.status === "running" || item.status === "waiting" ? "live" : "historic";
  router.replace({ query: { ...route.query, tab: "history", execution: item.id } });
}

function clearRuleScope() {
  const query = { ...route.query };
  delete query.rule_id;
  router.replace({ query });
}

function runSubtitle(run) {
  const started = run.started_at ? ` · ${formatDateTimeShort(run.started_at)}` : "";
  return `#${run.execution_id} · ${run.status}${started}`;
}

function formatDuration(startIso, endIso) {
  if (!startIso || !endIso) return "-";
  const elapsedMs = new Date(endIso).getTime() - new Date(startIso).getTime();
  if (!Number.isFinite(elapsedMs) || elapsedMs < 0) return "-";
  const seconds = Math.floor(elapsedMs / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return remainder ? `${minutes}m ${remainder}s` : `${minutes}m`;
}

function handleRerun(result) {
  activeTab.value = "live";
  selectedExecutionId.value = result.execution_id;
  selectedSource.value = "live";
  selectedRun.value = {
    execution_id: result.execution_id,
    rule_id: result.rule_id,
    rule_name: selectedRun.value?.rule_name || "Rerun",
    status: result.status,
  };
  refresh();
}

function handleInspectorUpdated(detail) {
  if (!detail) return;
  selectedRun.value = {
    ...(selectedRun.value || {}),
    execution_id: detail.id,
    rule_id: detail.rule_id,
    rule_name: detail.rule_name,
    status: detail.status,
  };
}

async function loadRecentRuns() {
  loadingRecent.value = true;
  try {
    if (scopedRuleId.value) {
      const executions = await api.getWorkflows({ rule_id: scopedRuleId.value, limit: 10 });
      recentRuns.value = executions.map((execution) => ({
        execution_id: execution.id,
        rule_id: execution.rule_id,
        rule_name: execution.rule_name,
        status: execution.status,
        started_at: execution.started_at,
        completed_at: execution.completed_at,
      }));
    } else {
      recentRuns.value = await api.getPipelineRuns({ limit: 10 });
    }
  } catch (error) {
    notify.error("Failed to load recent runs: " + (error?.message || error));
  } finally {
    loadingRecent.value = false;
  }
}

async function loadHistory() {
  loadingHistory.value = true;
  try {
    const params = {};
    if (scopedRuleId.value) params.rule_id = scopedRuleId.value;
    if (filter.value.status) params.status = filter.value.status;
    historyItems.value = await api.getWorkflows(params);
  } catch (error) {
    notify.error("Failed to load execution history: " + (error?.message || error));
  } finally {
    loadingHistory.value = false;
  }
}

async function loadIngestActivity() {
  loadingIngest.value = true;
  try {
    ingestActivity.value = await api.getIngestActivity({ limit: 50 });
  } catch (error) {
    notify.error("Failed to load ingest activity: " + (error?.message || error));
  } finally {
    loadingIngest.value = false;
  }
}

function refresh() {
  refreshSocket();
  loadRecentRuns();
  loadHistory();
  loadIngestActivity();
}

function statusColor(status) {
  switch (status) {
    case "running":
      return "primary";
    case "completed":
    case "success":
    case "succeeded":
      return "success";
    case "failed":
      return "error";
    case "waiting":
    case "skipped":
      return "warning";
    case "cancelled":
      return "grey";
    default:
      return "grey";
  }
}

onMounted(refresh);

defineExpose({
  activeTab,
  activeRuns,
  selectedExecutionId,
  selectedSource,
  selectedRun,
  scopedRuleId,
  ingestEvents,
  feedEvents,
  filter,
  loadHistory,
  selectRun,
  selectHistory,
});
</script>
