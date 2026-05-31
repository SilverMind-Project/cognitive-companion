<template>
  <div>
    <!-- Header -->
    <div class="d-flex align-center flex-wrap ga-3 mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Process Activity</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Live pipeline runs, image ingest feed, and signal trends.
        </div>
      </div>
      <v-spacer />
      <v-chip
        :color="wsColor"
        size="small"
        variant="tonal"
        :prepend-icon="wsIcon"
        data-testid="connection-chip"
      >
        {{ connectionState }}
      </v-chip>
      <v-btn size="small" variant="outlined" @click="refresh">Refresh</v-btn>
    </div>

    <!-- Stream interrupted alert (D5 / rule 15: never a frozen DAG) -->
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
      <v-tab value="runs">Live Runs</v-tab>
      <v-tab value="ingest">Ingest Feed</v-tab>
      <v-tab value="trends">Trends</v-tab>
    </v-tabs>

    <v-window v-model="activeTab">
      <!-- Live Runs panel -->
      <v-window-item value="runs">
        <v-row>
          <!-- Run list -->
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
                  :active="selectedRunId === run.execution_id"
                  :title="run.rule_name"
                  :subtitle="`#${run.execution_id} · ${run.status}`"
                  data-testid="run-item"
                  @click="selectRun(run)"
                >
                  <template #append>
                    <v-icon
                      :color="run.status === 'running' ? 'primary' : 'grey'"
                      size="12"
                    >mdi-circle</v-icon>
                  </template>
                </v-list-item>
              </v-list>
            </v-card>

            <!-- Recent completed runs -->
            <v-card class="glass-card mt-3">
              <v-card-title class="text-subtitle-1">Recent</v-card-title>
              <v-card-text v-if="loadingRecent" class="text-center">
                <v-progress-circular indeterminate size="24" />
              </v-card-text>
              <v-list v-else density="compact">
                <v-list-item
                  v-for="run in recentRuns"
                  :key="run.execution_id"
                  :active="selectedRunId === run.execution_id"
                  :title="run.rule_name"
                  :subtitle="`#${run.execution_id} · ${run.status}`"
                  data-testid="recent-run-item"
                  @click="selectRun(run)"
                />
              </v-list>
            </v-card>
          </v-col>

          <!-- Run detail: DAG + timeline -->
          <v-col cols="12" md="8">
            <v-card v-if="selectedRun" class="glass-card" data-testid="run-detail-card">
              <v-card-title class="d-flex align-center">
                {{ selectedRun.rule_name }}
                <v-chip :color="statusColor(selectedRun.status)" size="x-small" variant="tonal" class="ml-2">
                  {{ selectedRun.status }}
                </v-chip>
                <v-spacer />
                <v-btn
                  size="small"
                  variant="text"
                  :to="`/admin/rules`"
                  prepend-icon="mdi-open-in-new"
                >
                  Open Rule
                </v-btn>
              </v-card-title>

              <v-card-text>
                <div class="text-subtitle-2 mb-2">Step DAG</div>
                <div style="height: 260px" data-testid="dag-chart-wrapper">
                  <CcDagChart
                    :nodes="selectedRun.nodes"
                    :edges="selectedRun.edges"
                    :active-node-id="activeNodeId"
                    :loading="false"
                    data-testid="cc-dag-chart"
                  />
                </div>

                <v-divider class="my-3" />

                <div class="text-subtitle-2 mb-2">Step Timeline</div>
                <div style="height: 160px">
                  <CcStatusTimeline
                    :lanes="timelineLanes"
                    :events="timelineEvents"
                    :loading="false"
                  />
                </div>
              </v-card-text>
            </v-card>

            <v-card v-else class="glass-card">
              <v-card-text class="text-medium-emphasis pa-8 text-center">
                Select a run to inspect its live DAG.
              </v-card-text>
            </v-card>
          </v-col>
        </v-row>
      </v-window-item>

      <!-- Ingest Feed panel -->
      <v-window-item value="ingest">
        <v-row>
          <!-- Metric tiles -->
          <v-col cols="6" sm="3">
            <CcMetricTile
              label="Frames / min"
              :value="framesPerMin"
              status="neutral"
            />
          </v-col>
          <v-col cols="6" sm="3">
            <CcMetricTile
              label="Rules triggered"
              :value="rulesTriggered"
              status="neutral"
            />
          </v-col>
          <v-col cols="6" sm="3">
            <CcMetricTile
              label="Active sensors"
              :value="activeSensors"
              status="neutral"
            />
          </v-col>
          <v-col cols="6" sm="3">
            <CcMetricTile
              label="Last ingest"
              :value="lastIngestAge"
              status="neutral"
            />
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
      </v-window-item>

      <!-- Trends panel -->
      <v-window-item value="trends">
        <v-card class="glass-card">
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

    <!-- Run inspector drawer -->
    <v-navigation-drawer
      v-if="selectedRun"
      v-model="drawerOpen"
      location="right"
      temporary
      width="480"
      class="cc-drawer-right"
    >
      <div class="h-100 d-flex flex-column">
        <div class="d-flex align-center px-4 py-3">
          <span class="text-subtitle-1 font-weight-semibold">{{ selectedRun.rule_name }}</span>
          <v-chip :color="statusColor(selectedRun.status)" size="x-small" variant="tonal" class="ml-2">
            {{ selectedRun.status }}
          </v-chip>
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="drawerOpen = false" />
        </div>
        <v-divider />
        <div class="flex-grow-1 overflow-y-auto" style="min-height: 0">
          <v-card-text>
            <ExecutionDetail
              v-if="fullExecution"
              :execution="fullExecution"
              :live="selectedRun.status === 'running'"
            />
            <div v-else class="text-medium-emphasis text-center pa-4">
              <v-progress-circular indeterminate size="24" />
            </div>
          </v-card-text>
        </div>
      </div>
    </v-navigation-drawer>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from "vue";
import { useLivePipeline } from "@/composables/useLivePipeline.js";
import { useNotify } from "@/composables/useNotify.js";
import { api } from "@/services/api.js";
import { formatDateTimeShort } from "@/services/timezone.js";
import CcDagChart from "@/components/process/CcDagChart.vue";
import CcStatusTimeline from "@/components/process/CcStatusTimeline.vue";
import CcLiveActivityFeed from "@/components/process/CcLiveActivityFeed.vue";
import CcMetricTile from "@/components/dashboard/CcMetricTile.vue";
import ExecutionDetail from "@/components/pipeline/ExecutionDetail.vue";

const { notify } = useNotify();
const { connectionState, activeRuns, ingestEvents, error, refresh: refreshSocket } = useLivePipeline();

const activeTab = ref("runs");
const selectedRunId = ref(null);
const drawerOpen = ref(false);
const recentRuns = ref([]);
const loadingRecent = ref(false);
const fullExecution = ref(null);

// Ingest activity from REST (seeded once, augmented by WS events).
const ingestActivity = ref([]);
const loadingIngest = ref(false);

// -- Connection state display ------------------------------------------------

const wsColor = computed(() => {
  switch (connectionState.value) {
    case "open":       return "success";
    case "connecting": return "warning";
    case "error":
    case "closed":     return "error";
    default:           return "grey";
  }
});

const wsIcon = computed(() => {
  switch (connectionState.value) {
    case "open":       return "mdi-wifi";
    case "connecting": return "mdi-wifi-sync";
    default:           return "mdi-wifi-off";
  }
});

// -- Run selection -----------------------------------------------------------

const selectedRun = computed(
  () => activeRuns.value.find((r) => r.execution_id === selectedRunId.value)
       || recentRuns.value.find((r) => r.execution_id === selectedRunId.value)
       || null,
);

const activeNodeId = computed(() => {
  if (!selectedRun.value) return null;
  const running = selectedRun.value.nodes?.find((n) => n.status === "running");
  return running?.id || null;
});

function selectRun(run) {
  selectedRunId.value = run.execution_id;
  drawerOpen.value = true;
  loadFullExecution(run.execution_id);
}

async function loadFullExecution(id) {
  fullExecution.value = null;
  try {
    fullExecution.value = await api.getWorkflowDetail(id);
  } catch {
    // non-blocking — the DAG still shows from the envelope
  }
}

// -- Timeline derivation from the selected run -------------------------------

const timelineLanes = computed(() => {
  if (!selectedRun.value) return [];
  return (selectedRun.value.nodes || []).map((n) => ({ id: n.id, label: n.label }));
});

const timelineEvents = computed(() => {
  const run = selectedRun.value;
  if (!run) return [];
  return (run.nodes || [])
    .filter((n) => n.status !== "pending")
    .map((n) => ({
      laneId: n.id,
      t: run.started_at,
      label: n.status,
    }));
});

// -- Status color ------------------------------------------------------------

function statusColor(status) {
  switch (status) {
    case "running":   return "primary";
    case "completed": return "success";
    case "succeeded": return "success";
    case "failed":    return "error";
    case "waiting":   return "warning";
    case "cancelled": return "grey";
    default:          return "grey";
  }
}

// -- Ingest feed -------------------------------------------------------

const feedEvents = computed(() => {
  const fromRest = (ingestActivity.value || []).map((ev) => ({
    id: ev.id,
    timestamp: ev.timestamp,
    title: ev.event_type === "frame_received"
      ? `Frame from ${ev.sensor_id || "sensor"}`
      : `Rule triggered: ${ev.rule_name || "unknown"}`,
    description: ev.sensor_id || undefined,
    icon: ev.event_type === "frame_received" ? "mdi-camera" : "mdi-flash",
    color: ev.event_type === "frame_received" ? "teal" : "primary",
  }));

  const fromWs = ingestEvents.value
    .filter((e) => e.event_type === "pipeline_started")
    .map((e) => ({
      id: `ws-${e.execution_id}-${e.sequence}`,
      timestamp: e.started_at,
      title: `Pipeline started: ${e.rule_name}`,
      icon: "mdi-flash",
      color: "primary",
    }));

  return [...fromRest, ...fromWs].sort(
    (a, b) => new Date(b.timestamp) - new Date(a.timestamp),
  );
});

const framesPerMin = computed(() => {
  const cutoff = Date.now() - 60_000;
  return ingestActivity.value.filter(
    (e) => e.event_type === "frame_received" && new Date(e.timestamp).getTime() > cutoff,
  ).length;
});

const rulesTriggered = computed(() =>
  ingestActivity.value.filter((e) => e.event_type === "rule_triggered").length,
);

const activeSensors = computed(() => {
  const ids = new Set(
    ingestActivity.value
      .filter((e) => e.sensor_id)
      .map((e) => e.sensor_id),
  );
  return ids.size;
});

const lastIngestAge = computed(() => {
  if (!ingestActivity.value.length) return "—";
  const latest = ingestActivity.value[0];
  return formatDateTimeShort(latest.timestamp);
});

// -- Trends ------------------------------------------------------------------

const trendLanes = computed(() => [
  { id: "ingest", label: "Ingest" },
  { id: "rules", label: "Rules" },
]);

const trendEvents = computed(() =>
  (ingestActivity.value || []).map((ev) => ({
    laneId: ev.event_type === "frame_received" ? "ingest" : "rules",
    t: ev.timestamp,
    label: ev.event_type === "frame_received" ? "frame" : "rule",
  })),
);

// -- Data loading ------------------------------------------------------------

async function loadRecentRuns() {
  loadingRecent.value = true;
  try {
    recentRuns.value = await api.getPipelineRuns({ limit: 10 });
  } catch (e) {
    notify.error("Failed to load recent runs: " + (e?.message || e));
  } finally {
    loadingRecent.value = false;
  }
}

async function loadIngestActivity() {
  loadingIngest.value = true;
  try {
    ingestActivity.value = await api.getIngestActivity({ limit: 50 });
  } catch (e) {
    notify.error("Failed to load ingest activity: " + (e?.message || e));
  } finally {
    loadingIngest.value = false;
  }
}

function refresh() {
  refreshSocket();
  loadRecentRuns();
  loadIngestActivity();
}

onMounted(() => {
  loadRecentRuns();
  loadIngestActivity();
});

// Re-fetch full execution when WS updates the selected run.
watch(
  () => activeRuns.value.find((r) => r.execution_id === selectedRunId.value),
  (run) => {
    if (run && drawerOpen.value) {
      loadFullExecution(run.execution_id);
    }
  },
);

defineExpose({ connectionState, activeRuns, activeTab, selectedRun, feedEvents, ingestEvents, selectRun });
</script>

