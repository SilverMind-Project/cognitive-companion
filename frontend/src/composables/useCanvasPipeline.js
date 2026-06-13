import { reactive } from "vue";
import { api } from "@/services/api.js";
import { useNotify } from "@/composables/useNotify.js";

export const POSITION_SAVE_DEBOUNCE_MS = 800;

export function useCanvasPipeline(ruleId) {
  const { notify } = useNotify();

  const state = reactive({
    nodes: [],
    edges: [],
    loading: false,
    // `ready` flips true after the first successful load and never resets.
    // The canvas uses it to distinguish the initial fetch (full-screen spinner)
    // from background refreshes (subtle top progress bar) so VueFlow stays
    // mounted and the viewport is preserved across mutations.
    ready: false,
    error: null,
    stepMeta: {},
  });

  let saveTimer = null;

  async function loadMeta() {
    try {
      const types = await api.getStepTypes();
      state.stepMeta = Object.fromEntries(types.map((type) => [type.type_name, type]));
    } catch {
      state.stepMeta = {};
    }
  }

  async function load() {
    state.loading = true;
    state.error = null;
    try {
      const [steps, edges] = await Promise.all([
        api.getRuleSteps(ruleId),
        api.getRuleEdges(ruleId),
      ]);
      state.nodes = stepsToNodes(steps, state.stepMeta);
      state.edges = edgesToVueFlow(edges);
      state.ready = true;
    } catch (error) {
      state.error = error.message || "Failed to load pipeline";
    } finally {
      state.loading = false;
    }
  }

  function onNodeDragStop({ node }) {
    if (!node) return;
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(() => savePosition(node), POSITION_SAVE_DEBOUNCE_MS);
  }

  async function savePosition(node) {
    try {
      await api.updateRuleStepPosition(ruleId, Number(node.id), {
        position_x: node.position.x,
        position_y: node.position.y,
      });
    } catch (error) {
      notify.error(`Position save failed: ${error.message || error}`);
    }
  }

  function edgePayloads(edges = state.edges) {
    return edges.map((edge) => ({
      source_step_id: Number(edge.source),
      source_port: edge.sourceHandle || "main",
      target_step_id: Number(edge.target),
      target_port: edge.targetHandle || "main",
    }));
  }

  function outputPortsForNode(node) {
    if (!node) return ["main"];
    // Use length checks rather than `??`: an empty array is a valid object but
    // signals "no declared ports", so we must fall through to the next source
    // instead of returning `[]` (which would reject every connection).
    const fromNode = node.data?.outputPorts;
    if (fromNode?.length) return fromNode;
    const fromMeta = state.stepMeta[node.data?.step?.step_type]?.output_ports;
    if (fromMeta?.length) return fromMeta;
    return ["main"];
  }

  function validateConnection(connection) {
    const source = String(connection.source ?? "");
    const target = String(connection.target ?? "");
    const sourcePort = connection.sourceHandle || "main";
    const targetPort = connection.targetHandle || "main";
    const sourceNode = state.nodes.find((node) => node.id === source);

    if (source && source === target) {
      return "Cannot connect a step to itself.";
    }
    if (
      state.edges.some(
        (edge) => edge.source === source && (edge.sourceHandle || "main") === sourcePort,
      )
    ) {
      return "This output port is already connected.";
    }
    if (!outputPortsForNode(sourceNode).includes(sourcePort)) {
      return `Output port "${sourcePort}" is not valid for this step.`;
    }
    if (targetPort !== "main") {
      return "Pipeline steps only accept connections on the main input.";
    }
    return null;
  }

  async function addEdge(connection) {
    const validationError = validateConnection(connection);
    if (validationError) {
      notify.error(validationError);
      return false;
    }

    const newEdge = {
      source_step_id: Number(connection.source),
      source_port: connection.sourceHandle || "main",
      target_step_id: Number(connection.target),
      target_port: connection.targetHandle || "main",
    };

    try {
      await api.replaceRuleEdges(ruleId, [...edgePayloads(), newEdge]);
      await load();
      return true;
    } catch (error) {
      notify.error(`Connection invalid: ${error.message || error}`);
      return false;
    }
  }

  async function removeEdge(edgeId) {
    const remaining = state.edges.filter((edge) => edge.id !== String(edgeId));
    try {
      await api.replaceRuleEdges(ruleId, edgePayloads(remaining));
      await load();
      return true;
    } catch (error) {
      notify.error(`Remove edge failed: ${error.message || error}`);
      return false;
    }
  }

  async function removeNode(stepId) {
    try {
      await api.deleteRuleStep(ruleId, Number(stepId));
      await load();
      return true;
    } catch (error) {
      notify.error(`Delete step failed: ${error.message || error}`);
      return false;
    }
  }

  async function batchSavePositions(nodeList) {
    const positions = nodeList.map((node) => ({
      step_id: Number(node.id),
      position_x: node.position.x,
      position_y: node.position.y,
    }));

    try {
      await api.batchUpdateStepPositions(ruleId, positions);
      return true;
    } catch (error) {
      notify.error(`Position save failed: ${error.message || error}`);
      return false;
    }
  }

  function refreshNodeData(updatedStep) {
    const idx = state.nodes.findIndex((node) => node.id === String(updatedStep.id));
    if (idx === -1) return;
    state.nodes[idx] = {
      ...state.nodes[idx],
      data: {
        ...state.nodes[idx].data,
        step: updatedStep,
      },
    };
  }

  loadMeta().then(load);

  return {
    state,
    actions: {
      load,
      loadMeta,
      onNodeDragStop,
      addEdge,
      removeEdge,
      removeNode,
      batchSavePositions,
      refreshNodeData,
    },
  };
}

export function stepsToNodes(steps, stepMeta = {}, readonly = false) {
  return steps.map((step) => ({
    id: String(step.id),
    type: "step",
    position: { x: step.position_x ?? 0, y: step.position_y ?? 0 },
    data: {
      step,
      outputPorts: stepMeta[step.step_type]?.output_ports ?? ["main"],
      readonly,
    },
  }));
}

export function edgesToVueFlow(edges) {
  return edges.map((edge) => ({
    id: String(edge.id),
    source: String(edge.source_step_id),
    sourceHandle: edge.source_port,
    target: String(edge.target_step_id),
    targetHandle: edge.target_port,
    label: edge.source_port !== "main" ? edge.source_port : "",
    type: "smoothstep",
    animated: false,
    style: { stroke: "var(--cc-divider-strong)" },
    labelStyle: {
      fill: "var(--cc-text-2)",
      fontFamily: "var(--cc-font-mono)",
      fontSize: 11,
    },
  }));
}
