<template>
  <div class="cc-pipeline-monitor">
    <div v-if="state.loading" class="cc-pipeline-monitor__state">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <v-alert v-else-if="state.error" type="error" density="compact" variant="tonal" class="ma-4">
      {{ state.error }}
    </v-alert>

    <template v-else>
      <div class="cc-pipeline-monitor__toolbar">
        <v-chip
          v-if="props.source === 'live' && connectionState !== 'open'"
          size="x-small"
          color="warning"
          variant="tonal"
          prepend-icon="mdi-wifi-sync"
          data-testid="reconnect-badge"
        >
          Reconnecting
        </v-chip>
      </div>

      <v-alert
        v-if="props.source === 'historic' && !historicGraphAvailable"
        type="info"
        density="compact"
        variant="tonal"
        class="ma-4"
        data-testid="historic-fallback-notice"
      >
        This execution does not include a graph snapshot. Use the step inspector list for details.
      </v-alert>

      <VueFlow
        ref="flowElement"
        :nodes="monitorNodes"
        :edges="monitorEdges"
        :node-types="nodeTypes"
        :default-edge-options="defaultEdgeOptions"
        :fit-view-on-init="true"
        :nodes-draggable="false"
        :nodes-connectable="false"
        :edges-updatable="false"
        :elements-selectable="false"
        class="cc-pipeline-monitor__flow"
        data-testid="pipeline-monitor-flow"
        @node-click="onNodeClick"
      >
        <Background variant="dots" :gap="20" :size="1.35" color="var(--cc-pipeline-monitor-dot)" />
        <Controls />
        <MiniMap
          :node-color="minimapNodeColor"
          :width="minimapSize.width"
          :height="minimapSize.height"
          :offset-scale="0"
        />
      </VueFlow>

      <div
        v-if="connectionState === 'connecting' && !runState"
        class="cc-pipeline-monitor__overlay"
        data-testid="connecting-overlay"
      >
        <v-progress-circular indeterminate color="primary" size="28" />
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, markRaw, reactive, ref, watch } from "vue";
import { VueFlow } from "@vue-flow/core";
import { Background } from "@vue-flow/background";
import { Controls } from "@vue-flow/controls";
import { MiniMap } from "@vue-flow/minimap";
import {
  edgesToVueFlow,
  stepsToNodes,
  useCanvasPipeline,
} from "@/composables/useCanvasPipeline.js";
import { useLivePipeline } from "@/composables/useLivePipeline.js";
import { api } from "@/services/api.js";
import StepNode from "./nodes/StepNode.vue";
import { useCanvasMiniMapSize } from "./useCanvasMiniMapSize.js";
import "@vue-flow/core/dist/style.css";
import "@vue-flow/controls/dist/style.css";
import "@vue-flow/minimap/dist/style.css";

const props = defineProps({
  source: {
    type: String,
    default: "live",
    validator: (value) => ["live", "historic"].includes(value),
  },
  ruleId: { type: Number, default: null },
  executionId: { type: Number, required: true },
  execution: { type: Object, default: null },
});

const emit = defineEmits(["step-selected"]);

const historicState = reactive({
  nodes: [],
  edges: [],
  loading: false,
  error: null,
});
const historicDetail = ref(null);
const historicGraphAvailable = ref(true);

const liveCanvas =
  props.source === "live" ? useCanvasPipeline(props.ruleId) : { state: historicState };
const livePipeline =
  props.source === "live"
    ? useLivePipeline()
    : { connectionState: ref("open"), activeRuns: ref([]) };

const state = computed(() => (props.source === "historic" ? historicState : liveCanvas.state));
const connectionState = livePipeline.connectionState;
const activeRuns = livePipeline.activeRuns;

const nodeTypes = { step: markRaw(StepNode) };
const defaultEdgeOptions = { type: "smoothstep", animated: false };
const flowElement = ref(null);
const minimapSize = useCanvasMiniMapSize(flowElement);

watch(
  () => [props.source, props.executionId, props.execution],
  () => {
    if (props.source === "historic") loadHistoricExecution();
  },
  { immediate: true },
);

async function loadHistoricExecution() {
  historicState.loading = true;
  historicState.error = null;
  try {
    const detail = props.execution || (await api.getWorkflowDetail(props.executionId));
    historicDetail.value = detail;
    const graph = detail?.graph || null;
    historicGraphAvailable.value = Boolean(graph);
    if (!graph) {
      historicState.nodes = [];
      historicState.edges = [];
      emit("step-selected", firstTimelineEntry(detail));
      return;
    }

    historicState.nodes = stepsToNodes(
      graph.steps.map((step) => ({
        id: step.id,
        label: step.label,
        step_type: step.step_type,
        enabled: true,
        position_x: step.position_x,
        position_y: step.position_y,
      })),
      Object.fromEntries(
        graph.steps.map((step) => [
          step.step_type,
          { output_ports: step.output_ports?.length ? step.output_ports : ["main"] },
        ]),
      ),
      true,
    );
    historicState.edges = edgesToVueFlow(
      graph.edges.map((edge, index) => ({
        id: index + 1,
        source_step_id: edge.source_step_id,
        source_port: edge.source_port || "main",
        target_step_id: edge.target_step_id,
        target_port: edge.target_port || "main",
      })),
    );
    emit("step-selected", firstTimelineEntry(detail));
  } catch (error) {
    historicState.error = error?.message || "Failed to load execution graph";
    historicGraphAvailable.value = false;
  } finally {
    historicState.loading = false;
  }
}

const runState = computed(
  () =>
    activeRuns.value.find((run) => Number(run.execution_id) === Number(props.executionId)) || null,
);

const liveNodeById = computed(() => {
  const nodes = runState.value?.nodes || [];
  return Object.fromEntries(nodes.map((node) => [String(node.id), node]));
});

const timelineStatusByStep = computed(() => {
  const timeline =
    (props.source === "historic" ? historicDetail.value : props.execution)?.timeline || [];
  const byId = {};
  const byLabel = {};
  const byType = {};
  for (const item of timeline) {
    const status = normalizeStatus(item.status);
    if (item.step_id != null) byId[String(item.step_id)] = status;
    if (item.label) byLabel[item.label] = status;
    if (item.step_type) byType[item.step_type] = status;
  }
  return { byId, byLabel, byType };
});

const activeEdges = computed(() => {
  if (props.source === "historic") {
    return new Set(
      (historicDetail.value?.timeline || [])
        .filter((step) => step.step_id != null && !["skipped", "in_progress"].includes(step.status))
        .map((step) => `${step.step_id}:${step.output_port || "main"}`),
    );
  }
  return runState.value?.active_edges || new Set();
});

const monitorNodes = computed(() =>
  state.value.nodes.map((node) => {
    const liveNode = liveNodeById.value[node.id];
    const step = node.data?.step || {};
    const fallbackStatus =
      timelineStatusByStep.value.byId[node.id] ||
      timelineStatusByStep.value.byLabel[step.label] ||
      timelineStatusByStep.value.byType[step.step_type] ||
      "pending";
    return {
      ...node,
      draggable: false,
      selectable: false,
      connectable: false,
      data: {
        ...node.data,
        readonly: true,
        step: {
          ...step,
          status: liveNode?.status || fallbackStatus,
          elapsed_ms: liveNode?.elapsed_ms ?? step.elapsed_ms ?? null,
          output_port: liveNode?.output_port ?? step.output_port ?? null,
        },
      },
    };
  }),
);

const monitorEdges = computed(() =>
  state.value.edges.map((edge) => {
    const sourceHandle = edge.sourceHandle || "main";
    const isActive = activeEdges.value.has(`${edge.source}:${sourceHandle}`);
    return {
      ...edge,
      animated: props.source === "live" && isActive,
      selectable: false,
      style: {
        ...(edge.style || {}),
        stroke: isActive ? "rgb(var(--v-theme-success))" : "var(--cc-divider-strong)",
        strokeWidth: isActive ? 3 : 1.5,
      },
      labelStyle: {
        ...(edge.labelStyle || {}),
        fill: isActive ? "rgb(var(--v-theme-success))" : "var(--cc-text-2)",
      },
    };
  }),
);

function minimapNodeColor(node) {
  const status = node.data?.step?.status;
  if (status === "running") return "rgb(var(--v-theme-primary))";
  if (status === "succeeded") return "rgb(var(--v-theme-success))";
  if (status === "failed") return "rgb(var(--v-theme-error))";
  return "var(--cc-text-3)";
}

function onNodeClick({ node }) {
  const detail = props.source === "historic" ? historicDetail.value : props.execution;
  const step =
    (detail?.timeline || []).find((item) => String(item.step_id) === String(node?.id)) ||
    (detail?.timeline || []).find((item) => item.label === node?.data?.step?.label) ||
    null;
  emit("step-selected", step);
}

function normalizeStatus(status) {
  if (status === "success") return "succeeded";
  if (status === "in_progress") return "running";
  return status || "pending";
}

function firstTimelineEntry(detail) {
  return detail?.timeline?.[0] || null;
}
</script>

<style scoped>
.cc-pipeline-monitor {
  --cc-pipeline-monitor-dot: color-mix(in srgb, var(--cc-text-3) 42%, transparent);

  position: relative;
  min-height: 420px;
  overflow: hidden;
  border: 1px solid var(--cc-glass-border);
  border-radius: var(--cc-radius-md);
  background: var(--cc-surface-2);
}

.cc-pipeline-monitor__state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 420px;
}

.cc-pipeline-monitor__toolbar {
  position: absolute;
  z-index: 5;
  top: 10px;
  right: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.cc-pipeline-monitor__flow {
  width: 100%;
  height: 420px;
}

.cc-pipeline-monitor__overlay {
  position: absolute;
  z-index: 6;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--cc-bg) 72%, transparent);
  pointer-events: none;
}

.cc-pipeline-monitor :deep(.vue-flow__background) {
  background: var(--cc-surface-2);
}

.cc-pipeline-monitor :deep(.vue-flow__edge-path) {
  stroke-width: 1.5;
}

.cc-pipeline-monitor :deep(.vue-flow__edge.animated .vue-flow__edge-path) {
  stroke-dasharray: 8 5;
}

.cc-pipeline-monitor :deep(.vue-flow__controls) {
  overflow: hidden;
  border: 1px solid var(--cc-glass-border);
  border-radius: var(--cc-radius-sm);
  background: var(--cc-bg-elevated);
  box-shadow: var(--cc-shadow-sm);
}

.cc-pipeline-monitor :deep(.vue-flow__controls-button) {
  width: 20px;
  height: 20px;
  border-bottom: 1px solid var(--cc-divider);
  background: var(--cc-bg-elevated);
  color: var(--cc-text-1);
}

.cc-pipeline-monitor :deep(.vue-flow__controls-button:hover) {
  background: var(--cc-surface-3);
}

.cc-pipeline-monitor :deep(.vue-flow__controls-button svg) {
  fill: currentColor;
  stroke: currentColor;
}

.cc-pipeline-monitor :deep(.vue-flow__minimap) {
  border: 1px solid var(--cc-glass-border);
  border-radius: var(--cc-radius-sm);
  background: var(--cc-bg-elevated);
}
</style>
