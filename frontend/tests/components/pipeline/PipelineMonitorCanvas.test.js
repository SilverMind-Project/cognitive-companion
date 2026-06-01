import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { nextTick } from "vue";

const mocks = vi.hoisted(() => ({
  canvasState: {
    nodes: [],
    edges: [],
    loading: false,
    error: null,
  },
  live: {
    connectionState: { __v_isRef: true, value: "open" },
    activeRuns: { __v_isRef: true, value: [] },
  },
  useLivePipeline: vi.fn(),
  getWorkflowDetail: vi.fn(),
}));

vi.mock("@/composables/useCanvasPipeline.js", () => ({
  useCanvasPipeline: () => ({ state: mocks.canvasState, actions: {} }),
  stepsToNodes: (steps, stepMeta = {}, readonly = false) => steps.map((step) => ({
    id: String(step.id),
    type: "step",
    position: { x: step.position_x ?? 0, y: step.position_y ?? 0 },
    data: {
      step,
      outputPorts: stepMeta[step.step_type]?.output_ports ?? ["main"],
      readonly,
    },
  })),
  edgesToVueFlow: (edges) => edges.map((edge, index) => ({
    id: String(edge.id ?? index + 1),
    source: String(edge.source_step_id),
    sourceHandle: edge.source_port,
    target: String(edge.target_step_id),
    targetHandle: edge.target_port,
    label: edge.source_port !== "main" ? edge.source_port : "",
    type: "smoothstep",
    animated: false,
    style: { stroke: "var(--cc-divider-strong)" },
  })),
}));

vi.mock("@/composables/useLivePipeline.js", () => ({
  useLivePipeline: mocks.useLivePipeline,
}));

vi.mock("@/services/api.js", () => ({
  api: {
    getWorkflowDetail: (...args) => mocks.getWorkflowDetail(...args),
  },
}));

vi.mock("@vue-flow/core", () => ({
  VueFlow: {
    name: "VueFlow",
    props: [
      "nodes",
      "edges",
      "nodeTypes",
      "defaultEdgeOptions",
      "fitViewOnInit",
      "nodesDraggable",
      "nodesConnectable",
      "edgesUpdatable",
      "elementsSelectable",
    ],
    emits: ["node-double-click", "node-click"],
    template: `
      <div
        data-testid="vue-flow"
        @dblclick="$emit('node-double-click', { node: nodes[0] })"
        @click="$emit('node-click', { node: nodes[0] })"
      >
        <slot />
      </div>
    `,
  },
}));

vi.mock("@vue-flow/background", () => ({
  Background: { name: "Background", template: '<div data-testid="background" />' },
}));

vi.mock("@vue-flow/controls", () => ({
  Controls: { name: "Controls", template: '<div data-testid="controls" />' },
}));

vi.mock("@vue-flow/minimap", () => ({
  MiniMap: {
    name: "MiniMap",
    props: ["nodeColor", "width", "height", "offsetScale"],
    template: '<div data-testid="minimap" />',
  },
}));

import PipelineMonitorCanvas from "../../../src/components/pipeline/PipelineMonitorCanvas.vue";

const stubs = {
  "v-alert": { template: '<div data-testid="alert"><slot /></div>' },
  "v-chip": {
    props: ["prependIcon"],
    template: '<span data-testid="chip"><slot /></span>',
  },
  "v-progress-circular": { template: '<div data-testid="spinner" />' },
};

function mountMonitor(props = {}) {
  return mount(PipelineMonitorCanvas, {
    props: { ruleId: 1, executionId: 10, ...props },
    global: { stubs },
  });
}

beforeEach(() => {
  mocks.useLivePipeline.mockReset();
  mocks.useLivePipeline.mockImplementation(() => mocks.live);
  mocks.getWorkflowDetail.mockReset();
  mocks.canvasState.nodes = [
    {
      id: "101",
      type: "step",
      position: { x: 10, y: 20 },
      data: {
        step: {
          id: 101,
          label: "Filter",
          step_type: "condition",
          enabled: true,
        },
        outputPorts: ["true", "false"],
        readonly: false,
      },
    },
    {
      id: "102",
      type: "step",
      position: { x: 320, y: 20 },
      data: {
        step: {
          id: 102,
          label: "Notify",
          step_type: "notification",
          enabled: true,
        },
        outputPorts: ["main"],
        readonly: false,
      },
    },
  ];
  mocks.canvasState.edges = [
    {
      id: "1",
      source: "101",
      sourceHandle: "true",
      target: "102",
      targetHandle: "main",
      animated: false,
      style: { stroke: "var(--cc-divider-strong)" },
    },
  ];
  mocks.canvasState.loading = false;
  mocks.canvasState.error = null;
  mocks.live.connectionState.value = "open";
  mocks.live.activeRuns.value = [];
});

describe("PipelineMonitorCanvas", () => {
  it("renders authored nodes and edges read-only", () => {
    const wrapper = mountMonitor();
    const flow = wrapper.findComponent({ name: "VueFlow" });

    expect(flow.props("nodesDraggable")).toBe(false);
    expect(flow.props("nodesConnectable")).toBe(false);
    expect(flow.props("elementsSelectable")).toBe(false);
    expect(flow.props("nodes")[0].data.readonly).toBe(true);
  });

  it("applies running status to the active node", () => {
    mocks.live.activeRuns.value = [
      {
        execution_id: 10,
        nodes: [{ id: "101", status: "running", elapsed_ms: null }],
        edges: [],
        active_edges: new Set(),
      },
    ];

    const wrapper = mountMonitor();
    const node = wrapper.findComponent({ name: "VueFlow" }).props("nodes")[0];

    expect(node.data.step.status).toBe("running");
  });

  it("marks an edge animated once its source port has fired", () => {
    mocks.live.activeRuns.value = [
      {
        execution_id: 10,
        nodes: [],
        edges: [],
        active_edges: new Set(["101:true"]),
      },
    ];

    const wrapper = mountMonitor();
    const edge = wrapper.findComponent({ name: "VueFlow" }).props("edges")[0];

    expect(edge.animated).toBe(true);
    expect(edge.style.stroke).toBe("rgb(var(--v-theme-success))");
  });

  it("shows reconnect badge when the live stream is down", () => {
    mocks.live.connectionState.value = "closed";

    const wrapper = mountMonitor();

    expect(wrapper.find('[data-testid="reconnect-badge"]').exists()).toBe(true);
  });

  it("does not emit open-config on double-click in readonly mode", async () => {
    const wrapper = mountMonitor();

    await wrapper.findComponent({ name: "VueFlow" }).trigger("dblclick");

    expect(wrapper.emitted("open-config")).toBeUndefined();
    expect(wrapper.findComponent({ name: "VueFlow" }).props("nodes")[0].data.readonly).toBe(true);
  });

  it("historic source builds nodes and edges from detail.graph snapshot", async () => {
    mocks.getWorkflowDetail.mockResolvedValue({
      id: 10,
      graph: {
        steps: [
          { id: 201, label: "Snapshot Condition", step_type: "condition", position_x: 40, position_y: 50, output_ports: ["true", "false"] },
          { id: 202, label: "Snapshot Notify", step_type: "notification", position_x: 340, position_y: 50, output_ports: ["main"] },
        ],
        edges: [
          { source_step_id: 201, source_port: "true", target_step_id: 202, target_port: "main" },
        ],
      },
      timeline: [
        { step_id: 201, label: "Snapshot Condition", step_type: "condition", status: "success", output_port: "true" },
        { step_id: 202, label: "Snapshot Notify", step_type: "notification", status: "success", output_port: "main" },
      ],
    });

    const wrapper = mountMonitor({ source: "historic", executionId: 10 });
    await flushPromises();
    await nextTick();

    const flow = wrapper.findComponent({ name: "VueFlow" });
    expect(flow.props("nodes")[0].id).toBe("201");
    expect(flow.props("nodes")[0].position).toEqual({ x: 40, y: 50 });
    expect(flow.props("edges")[0].source).toBe("201");
    expect(mocks.useLivePipeline).not.toHaveBeenCalled();
  });

  it("historic source highlights the executed source port edge without animation", async () => {
    mocks.getWorkflowDetail.mockResolvedValue({
      id: 10,
      graph: {
        steps: [
          { id: 201, label: "Condition", step_type: "condition", output_ports: ["true", "false"] },
          { id: 202, label: "Notify", step_type: "notification", output_ports: ["main"] },
        ],
        edges: [
          { source_step_id: 201, source_port: "true", target_step_id: 202, target_port: "main" },
        ],
      },
      timeline: [
        { step_id: 201, label: "Condition", step_type: "condition", status: "success", output_port: "true" },
      ],
    });

    const wrapper = mountMonitor({ source: "historic", executionId: 10 });
    await flushPromises();
    await nextTick();

    const edge = wrapper.findComponent({ name: "VueFlow" }).props("edges")[0];
    expect(edge.animated).toBe(false);
    expect(edge.style.stroke).toBe("rgb(var(--v-theme-success))");
  });

  it("historic source greys out skipped untaken nodes", async () => {
    mocks.getWorkflowDetail.mockResolvedValue({
      id: 10,
      graph: {
        steps: [
          { id: 201, label: "Condition", step_type: "condition", output_ports: ["true", "false"] },
          { id: 203, label: "Untaken", step_type: "notification", output_ports: ["main"] },
        ],
        edges: [],
      },
      timeline: [
        { step_id: 201, label: "Condition", step_type: "condition", status: "success", output_port: "true" },
        { step_id: 203, label: "Untaken", step_type: "notification", status: "skipped", output_port: "main" },
      ],
    });

    const wrapper = mountMonitor({ source: "historic", executionId: 10 });
    await flushPromises();
    await nextTick();

    const skipped = wrapper.findComponent({ name: "VueFlow" }).props("nodes")[1];
    expect(skipped.data.step.status).toBe("skipped");
  });

  it("historic source shows fallback notice when detail.graph is null", async () => {
    mocks.getWorkflowDetail.mockResolvedValue({
      id: 10,
      graph: null,
      timeline: [],
    });

    const wrapper = mountMonitor({ source: "historic", executionId: 10 });
    await flushPromises();

    expect(wrapper.find('[data-testid="historic-fallback-notice"]').exists()).toBe(true);
  });
});
