<template>
  <div class="cc-pipeline-canvas">
    <div v-if="state.loading" class="cc-pipeline-canvas__state">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <v-alert
      v-else-if="state.error"
      type="error"
      density="compact"
      variant="tonal"
      class="ma-4"
    >
      {{ state.error }}
    </v-alert>

    <template v-else>
      <div class="cc-pipeline-canvas__toolbar">
        <v-btn
          size="small"
          variant="outlined"
          prepend-icon="mdi-auto-fix"
          @click="autoArrange"
        >
          Auto-arrange
        </v-btn>
        <v-btn
          color="primary"
          variant="flat"
          size="small"
          prepend-icon="mdi-plus"
          @click="paletteOpen = true"
        >
          Add Step
        </v-btn>
      </div>

      <VueFlow
        ref="flowElement"
        :nodes="state.nodes"
        :edges="state.edges"
        :node-types="nodeTypes"
        :default-edge-options="defaultEdgeOptions"
        :fit-view-on-init="true"
        :zoom-on-double-click="false"
        class="cc-pipeline-canvas__flow"
        @connect="actions.addEdge"
        @edges-change="onEdgesChange"
        @nodes-change="onNodesChange"
        @node-context-menu="onNodeContextMenu"
        @node-click="closeContextMenu"
        @pane-click="closeContextMenu"
        @node-drag-stop="actions.onNodeDragStop"
        @node-double-click="onNodeDoubleClick"
      >
        <Background
          variant="dots"
          :gap="20"
          :size="1.35"
          color="var(--cc-pipeline-canvas-dot)"
        />
        <Controls />
        <MiniMap
          :node-color="minimapNodeColor"
          :width="minimapSize.width"
          :height="minimapSize.height"
          :offset-scale="0"
        />
      </VueFlow>
    </template>

    <CanvasContextMenu
      :visible="contextMenu.visible"
      :x="contextMenu.x"
      :y="contextMenu.y"
      :step-id="contextMenu.stepId"
      :enabled="contextMenu.enabled"
      @edit="openConfigForStepId"
      @toggle="toggleStepEnabled"
      @delete="confirmAndRemove"
    />

    <StepPalette v-model="paletteOpen" @select="onStepSelected" />
    <StepConfigDialog
      v-model="configOpen"
      :step="editingStep"
      :all-steps="allSteps"
      @save="onStepSaved"
    />

    <v-dialog v-model="confirmDialog" max-width="400" persistent>
      <v-card rounded="xl">
        <v-card-title>{{ confirmTitle }}</v-card-title>
        <v-card-text>{{ confirmText }}</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="onCancel">{{ cancelLabel }}</v-btn>
          <v-btn :color="confirmColor" variant="flat" @click="onConfirm">
            {{ confirmLabel }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { computed, markRaw, nextTick, reactive, ref } from "vue";
import { VueFlow, useVueFlow } from "@vue-flow/core";
import { Background } from "@vue-flow/background";
import { Controls } from "@vue-flow/controls";
import { MiniMap } from "@vue-flow/minimap";
import { api } from "@/services/api.js";
import { useConfirm } from "@/composables/useConfirm.js";
import { useNotify } from "@/composables/useNotify.js";
import { useCanvasPipeline } from "@/composables/useCanvasPipeline.js";
import CanvasContextMenu from "./CanvasContextMenu.vue";
import StepConfigDialog from "./StepConfigDialog.vue";
import StepPalette from "./StepPalette.vue";
import { applyDagreLayout } from "./canvasLayout.js";
import StepNode from "./nodes/StepNode.vue";
import { useCanvasMiniMapSize } from "./useCanvasMiniMapSize.js";
import "@vue-flow/core/dist/style.css";
import "@vue-flow/controls/dist/style.css";
import "@vue-flow/minimap/dist/style.css";

const props = defineProps({
  ruleId: { type: Number, required: true },
});

const emit = defineEmits(["updated"]);
const { notify } = useNotify();
const { state, actions } = useCanvasPipeline(props.ruleId);
const { fitView } = useVueFlow();
const {
  confirmDialog,
  confirmTitle,
  confirmText,
  confirmLabel,
  cancelLabel,
  confirmColor,
  require: confirmRequire,
  onConfirm,
  onCancel,
} = useConfirm();

const nodeTypes = { step: markRaw(StepNode) };
const defaultEdgeOptions = { type: "smoothstep", animated: false };
const flowElement = ref(null);
const minimapSize = useCanvasMiniMapSize(flowElement);
const paletteOpen = ref(false);
const configOpen = ref(false);
const editingStep = ref(null);
const contextMenu = reactive({
  visible: false,
  x: 0,
  y: 0,
  stepId: null,
  enabled: true,
});

const allSteps = computed(() => state.nodes.map((node) => node.data.step));

function minimapNodeColor(node) {
  return node.data?.step?.enabled ? "rgb(var(--v-theme-primary))" : "var(--cc-text-3)";
}

function openConfigForNode(node) {
  if (!node?.data?.step || node.data.readonly) return;
  editingStep.value = { ...node.data.step };
  configOpen.value = true;
}

function onNodeDoubleClick(payload) {
  closeContextMenu();
  if (!payload?.node) {
    notify.error("Unable to open step editor: node details were not provided.");
    return;
  }
  openConfigForNode(payload.node);
}

function nodeByStepId(stepId) {
  return state.nodes.find((node) => node.id === String(stepId));
}

function openConfigForStepId(stepId) {
  const node = nodeByStepId(stepId);
  closeContextMenu();
  openConfigForNode(node);
}

function closeContextMenu() {
  contextMenu.visible = false;
}

function onNodeContextMenu(payload) {
  const event = payload?.event ?? payload;
  const node = payload?.node;
  event?.preventDefault?.();
  if (!node?.data?.step || node.data.readonly) return;

  contextMenu.visible = true;
  contextMenu.x = event?.clientX ?? 0;
  contextMenu.y = event?.clientY ?? 0;
  contextMenu.stepId = node.data.step.id;
  contextMenu.enabled = Boolean(node.data.step.enabled);
}

function onEdgesChange(changes) {
  for (const change of changes) {
    if (change.type === "remove") {
      actions.removeEdge(change.id);
    }
  }
}

function onNodesChange(changes) {
  for (const change of changes) {
    if (change.type === "remove") {
      confirmAndRemove(change.id);
    }
  }
}

async function confirmAndRemove(stepId) {
  closeContextMenu();
  const ok = await confirmRequire(
    "Delete this step? Connected edges will also be removed.",
    { confirmText: "Delete" },
  );
  if (!ok) return;

  const removed = await actions.removeNode(Number(stepId));
  if (removed) emit("updated");
}

async function toggleStepEnabled(stepId) {
  const node = nodeByStepId(stepId);
  if (!node?.data?.step) return;
  closeContextMenu();

  try {
    const updatedStep = await api.updateRuleStep(props.ruleId, Number(stepId), {
      enabled: !node.data.step.enabled,
    });
    actions.refreshNodeData(updatedStep);
    await actions.load();
    emit("updated");
  } catch (error) {
    notify.error(`Failed to update step: ${error.message || error}`);
  }
}

async function autoArrange() {
  const arranged = applyDagreLayout(state.nodes, state.edges);
  state.nodes = arranged;
  const saved = await actions.batchSavePositions(arranged);
  await nextTick();
  fitView({ padding: 0.2 });
  if (saved) emit("updated");
}

async function onStepSelected(stepType) {
  try {
    await api.addRuleStep(props.ruleId, {
      step_type: stepType,
      enabled: true,
      config_json: {},
      position_x: 100 + state.nodes.length * 320,
      position_y: 200,
    });
    await actions.load();
    emit("updated");
  } catch (error) {
    notify.error(`Failed to add step: ${error.message || error}`);
  }
}

async function onStepSaved(data) {
  if (!editingStep.value) return;
  try {
    const updatedStep = await api.updateRuleStep(props.ruleId, editingStep.value.id, {
      step_type: editingStep.value.step_type,
      label: data.label,
      config_json: data.config_json,
    });
    actions.refreshNodeData(updatedStep);
    await actions.load();
    emit("updated");
  } catch (error) {
    notify.error(`Failed to save step: ${error.message || error}`);
  } finally {
    editingStep.value = null;
  }
}
</script>

<style scoped>
.cc-pipeline-canvas {
  --cc-pipeline-canvas-dot: color-mix(in srgb, var(--cc-text-3) 42%, transparent);

  position: relative;
  width: 100%;
  height: min(70vh, 720px);
  min-height: 560px;
  overflow: hidden;
  border: 1px solid var(--cc-glass-border);
  border-radius: var(--cc-radius-lg);
  background: var(--cc-bg);
}

.cc-pipeline-canvas__state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

.cc-pipeline-canvas__flow {
  width: 100%;
  height: 100%;
}

.cc-pipeline-canvas__toolbar {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 8px;
}

.cc-pipeline-canvas :deep(.vue-flow__background) {
  background: var(--cc-bg);
}

.cc-pipeline-canvas :deep(.vue-flow__edge-path) {
  stroke: var(--cc-divider-strong);
  stroke-width: 2;
}

.cc-pipeline-canvas :deep(.vue-flow__edge-textbg) {
  fill: var(--cc-bg-elevated);
}

.cc-pipeline-canvas :deep(.vue-flow__controls) {
  overflow: hidden;
  border: 1px solid var(--cc-glass-border);
  border-radius: var(--cc-radius-md);
  background: var(--cc-bg-elevated);
  box-shadow: var(--cc-shadow-sm);
}

.cc-pipeline-canvas :deep(.vue-flow__controls-button) {
  width: 20px;
  height: 20px;
  border-bottom: 1px solid var(--cc-divider);
  background: var(--cc-bg-elevated);
  color: var(--cc-text-1);
}

.cc-pipeline-canvas :deep(.vue-flow__controls-button:hover) {
  background: var(--cc-surface-3);
}

.cc-pipeline-canvas :deep(.vue-flow__controls-button svg) {
  fill: currentColor;
  stroke: currentColor;
}

.cc-pipeline-canvas :deep(.vue-flow__minimap) {
  border: 1px solid var(--cc-glass-border);
  border-radius: var(--cc-radius-md);
  background: var(--cc-bg-elevated);
  box-shadow: var(--cc-shadow-sm);
}
</style>
