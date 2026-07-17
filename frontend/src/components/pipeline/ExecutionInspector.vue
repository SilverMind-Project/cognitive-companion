<template>
  <v-card class="glass-card execution-inspector" data-testid="execution-inspector">
    <v-card-text v-if="!executionId" class="text-medium-emphasis text-center pa-8">
      Select an execution to inspect its graph and step data.
    </v-card-text>

    <template v-else>
      <div class="d-flex align-center flex-wrap ga-2 px-4 py-3">
        <div class="min-w-0">
          <div class="text-subtitle-1 font-weight-semibold text-truncate">
            {{ detail?.rule_name || runTitle }}
          </div>
          <div class="text-caption text-medium-emphasis">Execution #{{ executionId }}</div>
        </div>
        <v-chip
          :color="statusColor(detail?.status || liveRun?.status)"
          size="small"
          variant="tonal"
        >
          {{ detail?.status || liveRun?.status || "loading" }}
        </v-chip>
        <v-spacer />
        <v-btn
          v-if="detail?.can_cancel"
          color="error"
          variant="tonal"
          size="small"
          prepend-icon="mdi-stop-circle"
          :loading="busy"
          @click="cancelExecution"
        >
          Cancel
        </v-btn>
        <v-btn
          v-if="detail?.can_rerun"
          color="primary"
          variant="tonal"
          size="small"
          prepend-icon="mdi-replay"
          :loading="busy"
          @click="rerunExecution"
        >
          Rerun
        </v-btn>
        <v-btn
          v-if="isActiveExecution"
          variant="text"
          size="small"
          :prepend-icon="polling ? 'mdi-pause' : 'mdi-play'"
          @click="togglePolling"
        >
          {{ polling ? "Pause" : "Resume" }}
        </v-btn>
        <v-btn
          v-if="detail"
          variant="text"
          size="small"
          prepend-icon="mdi-content-copy"
          @click="copyPipelineData"
        >
          Copy data
        </v-btn>
        <v-btn
          icon="mdi-refresh"
          variant="text"
          size="small"
          :loading="loading"
          @click="loadDetail"
        />
      </div>
      <v-divider />

      <div v-if="loading" class="d-flex justify-center pa-8">
        <v-progress-circular indeterminate color="primary" />
      </div>

      <v-alert v-else-if="error" type="error" density="compact" variant="tonal" class="ma-4">
        {{ error }}
      </v-alert>

      <div v-else-if="detail" class="execution-inspector__body">
        <div class="execution-inspector__canvas">
          <div class="d-flex align-center flex-wrap ga-2 mb-3 text-caption">
            <v-chip size="small" variant="tonal" prepend-icon="mdi-source-branch">
              {{ detail.trigger_summary }}
            </v-chip>
            <span class="text-medium-emphasis">
              Started {{ formatDateTime(detail.started_at) }}
            </span>
            <span v-if="detail.completed_at" class="text-medium-emphasis">
              Completed {{ formatDateTime(detail.completed_at) }}
            </span>
            <span v-if="executionDuration" class="text-medium-emphasis">
              Duration {{ executionDuration }}
            </span>
            <v-btn
              v-if="resolvedRuleId"
              size="x-small"
              variant="text"
              prepend-icon="mdi-pencil-outline"
              :to="{
                name: 'admin-rule-detail',
                params: { id: resolvedRuleId },
                query: { tab: 'executions' },
              }"
            >
              Rule
            </v-btn>
          </div>

          <v-alert
            v-if="detail.error"
            type="error"
            density="compact"
            variant="tonal"
            class="mb-3"
            data-testid="execution-error"
          >
            {{ detail.error }}
          </v-alert>
          <v-alert
            v-if="detail.cooloff_triggered"
            type="warning"
            density="compact"
            variant="tonal"
            class="mb-3"
            data-testid="cooloff-alert"
          >
            This execution triggered the rule cool-off limit.
          </v-alert>

          <PipelineMonitorCanvas
            :source="source"
            :rule-id="resolvedRuleId"
            :execution-id="executionId"
            :execution="detail"
            @step-selected="selectStep"
          />

          <v-card
            v-if="!detail.graph"
            variant="tonal"
            class="mt-3"
            data-testid="flat-timeline-fallback"
          >
            <v-list density="compact">
              <v-list-item
                v-for="step in detail.timeline"
                :key="step.step_id || step.label"
                :active="selectedStepKey === stepKey(step)"
                :title="step.label"
                :subtitle="step.step_type"
                @click="selectStep(step)"
              >
                <template #append>
                  <v-chip :color="statusColor(step.status)" size="x-small" variant="tonal">
                    {{ step.status }}
                  </v-chip>
                </template>
              </v-list-item>
            </v-list>
          </v-card>
        </div>

        <div class="execution-inspector__panel">
          <StepInspectorPanel :step="selectedStep" />
        </div>
      </div>
    </template>

    <v-dialog v-model="confirmDialog" max-width="400" persistent>
      <v-card rounded="xl">
        <v-card-title>{{ confirmTitle }}</v-card-title>
        <v-card-text>{{ confirmText }}</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="onCancel">{{ cancelLabel }}</v-btn>
          <v-btn :color="confirmColor" variant="flat" @click="onConfirm">{{ confirmLabel }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-card>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { api } from "@/services/api.js";
import { useConfirm } from "@/composables/useConfirm.js";
import { useNotify } from "@/composables/useNotify.js";
import { formatDateTime } from "@/services/timezone.js";
import PipelineMonitorCanvas from "./PipelineMonitorCanvas.vue";
import StepInspectorPanel from "./StepInspectorPanel.vue";

const props = defineProps({
  executionId: { type: Number, default: null },
  source: {
    type: String,
    default: "historic",
    validator: (value) => ["live", "historic"].includes(value),
  },
  ruleId: { type: Number, default: null },
  liveRun: { type: Object, default: null },
});

const emit = defineEmits(["updated", "rerun"]);

const router = useRouter();
const detail = ref(null);
const selectedStep = ref(null);
const loading = ref(false);
const busy = ref(false);
const error = ref(null);
const polling = ref(false);
let pollTimer = null;
const { notify } = useNotify();
const {
  confirmDialog,
  confirmTitle,
  confirmText,
  confirmLabel,
  cancelLabel,
  confirmColor,
  showConfirm,
  onConfirm,
  onCancel,
} = useConfirm();

const runTitle = computed(() => props.liveRun?.rule_name || "Execution");
const resolvedRuleId = computed(
  () => detail.value?.rule_id || props.ruleId || props.liveRun?.rule_id || null,
);
const selectedStepKey = computed(() => stepKey(selectedStep.value));
const isActiveExecution = computed(
  () =>
    props.source === "live" &&
    ["running", "waiting"].includes(detail.value?.status || props.liveRun?.status),
);
const executionDuration = computed(() =>
  formatDuration(detail.value?.started_at, detail.value?.completed_at),
);

watch(
  () => [props.executionId, props.source],
  async () => {
    stopPolling();
    polling.value = props.source === "live";
    await loadDetail();
    syncPolling();
  },
  { immediate: true },
);

async function loadDetail() {
  if (!props.executionId) {
    detail.value = null;
    selectedStep.value = null;
    return;
  }
  if (loading.value) return;
  const previousStepKey = selectedStepKey.value;
  loading.value = true;
  error.value = null;
  try {
    detail.value = await api.getWorkflowDetail(props.executionId);
    selectedStep.value =
      detail.value?.timeline?.find((step) => stepKey(step) === previousStepKey) ||
      detail.value?.timeline?.[0] ||
      null;
    emit("updated", detail.value);
    if (!["running", "waiting"].includes(detail.value?.status)) {
      stopPolling();
    }
  } catch (err) {
    error.value = err?.message || "Failed to load execution detail";
  } finally {
    loading.value = false;
  }
}

function startPolling() {
  stopPolling();
  polling.value = true;
  pollTimer = setInterval(loadDetail, 1000);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  polling.value = false;
}

function syncPolling() {
  if (polling.value && isActiveExecution.value) {
    startPolling();
  } else {
    stopPolling();
  }
}

function togglePolling() {
  if (polling.value) {
    stopPolling();
  } else {
    startPolling();
    loadDetail();
  }
}

async function copyPipelineData() {
  const pipelineData = {};
  for (const step of detail.value?.timeline || []) {
    if (step.label && step.outputs) {
      pipelineData[`steps.${step.label}.outputs`] = step.outputs;
    }
    if (step.label && step.resolved_config) {
      pipelineData[`steps.${step.label}.resolved_config`] = step.resolved_config;
    }
  }
  try {
    await navigator.clipboard.writeText(JSON.stringify(pipelineData, null, 2));
    notify.success("Pipeline data copied.");
  } catch {
    notify.error("Copy failed.");
  }
}

function selectStep(step) {
  selectedStep.value = step || null;
}

async function cancelExecution() {
  if (!props.executionId) return;
  const confirmed = await showConfirm(
    "Stop this execution?",
    "This will cancel the running or waiting workflow execution.",
  );
  if (!confirmed) return;

  busy.value = true;
  try {
    await api.cancelWorkflow(props.executionId);
    notify.success("Execution cancelled.");
    await loadDetail();
  } catch (err) {
    notify.error("Cancel failed: " + (err?.message || "Unknown error"));
  } finally {
    busy.value = false;
  }
}

async function rerunExecution() {
  if (!props.executionId) return;
  busy.value = true;
  try {
    const result = await api.rerunWorkflow(props.executionId);
    notify.success(`Rerun started (#${result.execution_id})`);
    emit("rerun", result);
    router.push({
      name: "admin-executions",
      query: {
        tab: "live",
        execution: result.execution_id,
        ...(resolvedRuleId.value ? { rule_id: resolvedRuleId.value } : {}),
      },
    });
  } catch (err) {
    notify.error("Rerun failed: " + (err?.message || "Unknown error"));
  } finally {
    busy.value = false;
  }
}

function stepKey(step) {
  if (!step) return "";
  return String(step.step_id ?? step.label ?? "");
}

function formatDuration(startIso, endIso) {
  if (!startIso || !endIso) return "";
  const elapsedMs = new Date(endIso).getTime() - new Date(startIso).getTime();
  if (!Number.isFinite(elapsedMs) || elapsedMs < 0) return "";
  const seconds = Math.floor(elapsedMs / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return remainder ? `${minutes}m ${remainder}s` : `${minutes}m`;
}

function statusColor(status) {
  switch (status) {
    case "running":
    case "in_progress":
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

onBeforeUnmount(stopPolling);

defineExpose({ loadDetail, selectStep, detail, selectedStep, polling });
</script>

<style scoped>
.execution-inspector {
  overflow: hidden;
}

.execution-inspector__body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 380px);
  gap: 16px;
  padding: 16px;
}

.execution-inspector__canvas,
.execution-inspector__panel {
  min-width: 0;
}

@media (max-width: 960px) {
  .execution-inspector__body {
    grid-template-columns: 1fr;
  }
}
</style>
