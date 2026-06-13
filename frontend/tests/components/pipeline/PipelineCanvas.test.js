import { describe, expect, it, beforeEach, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";

const mocks = vi.hoisted(() => ({
  state: {
    nodes: [],
    edges: [],
    loading: false,
    error: null,
    stepMeta: {},
  },
  actions: {
    load: vi.fn(),
    onNodeDragStop: vi.fn(),
    addEdge: vi.fn(),
    removeEdge: vi.fn(),
    removeNode: vi.fn(),
    batchSavePositions: vi.fn(),
    refreshNodeData: vi.fn(),
  },
  api: {
    addRuleStep: vi.fn(),
    updateRuleStep: vi.fn(),
  },
  notify: {
    error: vi.fn(),
  },
  fitView: vi.fn(),
  screenToFlowCoordinate: vi.fn(({ x, y }) => ({ x, y })),
  onNodesInitialized: vi.fn(),
}));

vi.mock("@/composables/useCanvasPipeline.js", () => ({
  useCanvasPipeline: () => ({ state: mocks.state, actions: mocks.actions }),
}));

vi.mock("@/services/api.js", () => ({
  api: mocks.api,
}));

vi.mock("@/composables/useNotify.js", () => ({
  useNotify: () => ({ notify: mocks.notify }),
}));

vi.mock("@vue-flow/core", () => ({
  useVueFlow: () => ({
    fitView: mocks.fitView,
    screenToFlowCoordinate: mocks.screenToFlowCoordinate,
    onNodesInitialized: mocks.onNodesInitialized,
  }),
  VueFlow: {
    name: "VueFlow",
    props: [
      "nodes",
      "edges",
      "nodeTypes",
      "defaultEdgeOptions",
      "fitViewOnInit",
      "zoomOnDoubleClick",
      "minZoom",
      "maxZoom",
    ],
    emits: [
      "connect",
      "edges-change",
      "nodes-change",
      "node-context-menu",
      "node-click",
      "pane-click",
      "node-double-click",
      "node-drag-stop",
    ],
    template: `
      <div
        data-testid="vue-flow"
        @dblclick="$emit('node-double-click', { node: nodes[0] })"
        @mouseup="$emit('node-drag-stop', { node: nodes[0] })"
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

import PipelineCanvas from "../../../src/components/pipeline/PipelineCanvas.vue";

const stubs = {
  "v-alert": { template: '<div data-testid="alert"><slot /></div>' },
  "v-btn": {
    props: ["prependIcon", "variant", "color"],
    template: '<button data-testid="button" :data-icon="prependIcon" @click="$emit(\'click\', $event)"><slot /></button>',
  },
  "v-card": { template: '<section><slot /></section>' },
  "v-card-title": { template: '<h3><slot /></h3>' },
  "v-card-text": { template: '<div><slot /></div>' },
  "v-card-actions": { template: '<div><slot /></div>' },
  "v-dialog": {
    props: ["modelValue"],
    template: '<div v-if="modelValue" data-testid="confirm-dialog"><slot /></div>',
  },
  "v-divider": { template: "<hr />" },
  "v-list": { template: "<div><slot /></div>" },
  "v-list-item": {
    props: ["title", "prependIcon", "color"],
    template: '<button data-testid="menu-item" @click="$emit(\'click\', $event)">{{ title }}</button>',
  },
  "v-progress-circular": { template: '<div data-testid="spinner" />' },
  "v-progress-linear": { template: '<div data-testid="refresh-bar" />' },
  "v-icon": { template: "<i><slot /></i>" },
  "v-spacer": { template: "<span />" },
  StepPalette: {
    props: ["modelValue"],
    emits: ["update:modelValue", "select"],
    template: `
      <div v-if="modelValue" data-testid="palette">
        <button data-testid="select-step" @click="$emit('select', 'notification')">select</button>
      </div>
    `,
  },
  StepConfigDialog: {
    props: ["modelValue", "step", "allSteps"],
    emits: ["update:modelValue", "save"],
    template: `
      <div v-if="modelValue" data-testid="config-dialog">
        <button data-testid="save-step" @click="$emit('save', { label: 'notify_family', config_json: { message_template: 'hi' } })">save</button>
      </div>
    `,
  },
};

function seedState(overrides = {}) {
  mocks.state.nodes = [
    {
      id: "1",
      type: "step",
      position: { x: 0, y: 0 },
      data: {
        step: {
          id: 1,
          step_type: "notification",
          label: "notify",
          enabled: true,
          config_json: {},
        },
        outputPorts: ["main"],
        readonly: false,
      },
    },
  ];
  mocks.state.edges = [];
  mocks.state.loading = false;
  mocks.state.error = null;
  Object.assign(mocks.state, overrides);
}

function mountCanvas() {
  return mount(PipelineCanvas, {
    props: { ruleId: 42 },
    global: { stubs },
  });
}

function buttonWithText(wrapper, text) {
  return wrapper
    .findAll('[data-testid="button"]')
    .find((button) => button.text().includes(text));
}

beforeEach(() => {
  vi.clearAllMocks();
  seedState();
  mocks.actions.load.mockResolvedValue();
  mocks.actions.addEdge.mockResolvedValue(true);
  mocks.actions.removeEdge.mockResolvedValue(true);
  mocks.actions.removeNode.mockResolvedValue(true);
  mocks.actions.batchSavePositions.mockResolvedValue(true);
  mocks.api.addRuleStep.mockResolvedValue({ id: 2 });
  mocks.api.updateRuleStep.mockResolvedValue({
    id: 1,
    step_type: "notification",
    label: "notify_family",
    enabled: true,
    config_json: { message_template: "hi" },
  });
});

describe("PipelineCanvas", () => {
  it("renders nodes from composable state through Vue Flow", () => {
    const wrapper = mountCanvas();
    expect(wrapper.find('[data-testid="vue-flow"]').exists()).toBe(true);
    expect(wrapper.findComponent({ name: "VueFlow" }).props("nodes")).toHaveLength(1);
  });

  it("shows loading spinner while fetching", () => {
    seedState({ loading: true });
    const wrapper = mountCanvas();
    expect(wrapper.find('[data-testid="spinner"]').exists()).toBe(true);
  });

  it("shows error alert on API failure", () => {
    seedState({ error: "Failed to load pipeline" });
    const wrapper = mountCanvas();
    expect(wrapper.find('[data-testid="alert"]').text()).toContain("Failed to load pipeline");
  });

  it("opens StepConfigDialog on node double-click", async () => {
    const wrapper = mountCanvas();
    await wrapper.find('[data-testid="vue-flow"]').trigger("dblclick");
    expect(wrapper.find('[data-testid="config-dialog"]').exists()).toBe(true);
  });

  it("disables viewport double-click zoom so node double-click edits are deterministic", () => {
    const wrapper = mountCanvas();
    expect(wrapper.findComponent({ name: "VueFlow" }).props("zoomOnDoubleClick")).toBe(false);
  });

  it("opens StepPalette when Add Step is clicked", async () => {
    const wrapper = mountCanvas();
    await buttonWithText(wrapper, "Add Step").trigger("click");
    expect(wrapper.find('[data-testid="palette"]').exists()).toBe(true);
  });

  it("forwards node drag-stop to the composable action", async () => {
    const wrapper = mountCanvas();
    await wrapper.find('[data-testid="vue-flow"]').trigger("mouseup");
    expect(mocks.actions.onNodeDragStop).toHaveBeenCalledWith({ node: mocks.state.nodes[0] });
  });

  it("does not send order in the addRuleStep payload", async () => {
    const wrapper = mountCanvas();
    await buttonWithText(wrapper, "Add Step").trigger("click");
    await wrapper.find('[data-testid="select-step"]').trigger("click");
    await flushPromises();

    expect(mocks.api.addRuleStep).toHaveBeenCalledWith(42, expect.not.objectContaining({ order: expect.anything() }));
    expect(mocks.api.addRuleStep).toHaveBeenCalledWith(42, expect.objectContaining({
      step_type: "notification",
      position_x: expect.any(Number),
      position_y: expect.any(Number),
    }));
  });

  it("saves step config through the existing update endpoint", async () => {
    const wrapper = mountCanvas();
    await wrapper.find('[data-testid="vue-flow"]').trigger("dblclick");
    await wrapper.find('[data-testid="save-step"]').trigger("click");
    await flushPromises();

    expect(mocks.api.updateRuleStep).toHaveBeenCalledWith(42, 1, {
      step_type: "notification",
      label: "notify_family",
      config_json: { message_template: "hi" },
    });
    expect(mocks.actions.refreshNodeData).toHaveBeenCalled();
  });

  it("fires addEdge action when connect event emitted", () => {
    const wrapper = mountCanvas();

    wrapper.findComponent({ name: "VueFlow" }).vm.$emit("connect", {
      source: "1",
      sourceHandle: "main",
      target: "2",
      targetHandle: "main",
    });

    expect(mocks.actions.addEdge).toHaveBeenCalledWith({
      source: "1",
      sourceHandle: "main",
      target: "2",
      targetHandle: "main",
    });
  });

  it("fires removeEdge action when edges-change remove emitted", () => {
    const wrapper = mountCanvas();

    wrapper.findComponent({ name: "VueFlow" }).vm.$emit("edges-change", [
      { type: "remove", id: "edge-1" },
    ]);

    expect(mocks.actions.removeEdge).toHaveBeenCalledWith("edge-1");
  });

  it("shows confirm dialog before removeNode", async () => {
    const wrapper = mountCanvas();

    wrapper.findComponent({ name: "VueFlow" }).vm.$emit("nodes-change", [
      { type: "remove", id: "1" },
    ]);
    await flushPromises();

    expect(wrapper.find('[data-testid="confirm-dialog"]').text()).toContain("Delete this step?");
    expect(mocks.actions.removeNode).not.toHaveBeenCalled();
  });

  it("does not remove node if user cancels confirm", async () => {
    const wrapper = mountCanvas();

    wrapper.findComponent({ name: "VueFlow" }).vm.$emit("nodes-change", [
      { type: "remove", id: "1" },
    ]);
    await flushPromises();
    await buttonWithText(wrapper, "Cancel").trigger("click");
    await flushPromises();

    expect(mocks.actions.removeNode).not.toHaveBeenCalled();
  });

  it("removes node after confirmation", async () => {
    const wrapper = mountCanvas();

    wrapper.findComponent({ name: "VueFlow" }).vm.$emit("nodes-change", [
      { type: "remove", id: "1" },
    ]);
    await flushPromises();
    await buttonWithText(wrapper, "Delete").trigger("click");
    await flushPromises();

    expect(mocks.actions.removeNode).toHaveBeenCalledWith(1);
  });

  it("calls autoArrange and batchSavePositions when auto-arrange button clicked", async () => {
    const wrapper = mountCanvas();

    await buttonWithText(wrapper, "Auto-arrange").trigger("click");
    await flushPromises();

    expect(mocks.actions.batchSavePositions).toHaveBeenCalledWith(mocks.state.nodes);
    expect(mocks.fitView).toHaveBeenCalledWith({ padding: 0.2 });
  });

  it("shows context menu and toggles step enabled state", async () => {
    const wrapper = mountCanvas();

    wrapper.findComponent({ name: "VueFlow" }).vm.$emit("node-context-menu", {
      event: { clientX: 40, clientY: 80, preventDefault: vi.fn() },
      node: mocks.state.nodes[0],
    });
    await flushPromises();
    await wrapper
      .findAll('[data-testid="menu-item"]')
      .find((item) => item.text() === "Disable")
      .trigger("click");
    await flushPromises();

    expect(mocks.api.updateRuleStep).toHaveBeenCalledWith(42, 1, { enabled: false });
  });
});
