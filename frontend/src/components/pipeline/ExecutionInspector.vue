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
          <div class="text-caption text-medium-emphasis">
            Execution #{{ executionId }}
          </div>
        </div>
        <v-chip :color="statusColor(detail?.status || liveRun?.status)" size="small" variant="tonal">
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

      <v-alert
        v-else-if="error"
        type="error"
        density="compact"
        variant="tonal"
        class="ma-4"
      >
        {{ error }}
      </v-alert>

      <div v-else-if="detail" class="execution-inspector__body">
        <div class="execution-inspector__canvas">
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

    <v-snackbar v-model="snack" :color="snackColor" timeout="3000">{{ snackText }}</v-snackbar>
  </v-card>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { api } from "@/services/api.js";
import { useConfirm } from "@/composables/useConfirm.js";
import { useNotify } from "@/composables/useNotify.js";
import PipelineMonitorCanvas from "./PipelineMonitorCanvas.vue";
import StepInspectorPanel from "./StepInspectorPanel.vue";

const props = defineProps({
  executionId: { type: Number, default: null },
  source: { type: String, default: "historic", validator: (value) => ["live", "historic"].includes(value) },
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
const { snack, snackText, snackColor, notify } = useNotify();
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
const resolvedRuleId = computed(() => detail.value?.rule_id || props.ruleId || props.liveRun?.rule_id || null);
const selectedStepKey = computed(() => stepKey(selectedStep.value));

watch(
  () => props.executionId,
  () => loadDetail(),
  { immediate: true },
);

async function loadDetail() {
  if (!props.executionId) {
    detail.value = null;
    selectedStep.value = null;
    return;
  }
  loading.value = true;
  error.value = null;
  try {
    detail.value = await api.getWorkflowDetail(props.executionId);
    selectedStep.value = detail.value?.timeline?.[0] || null;
    emit("updated", detail.value);
  } catch (err) {
    error.value = err?.message || "Failed to load execution detail";
  } finally {
    loading.value = false;
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
    router.push(`/admin/executions?tab=live&execution=${result.execution_id}`);
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

defineExpose({ loadDetail, selectStep, detail, selectedStep });
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
