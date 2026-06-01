import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const mocks = vi.hoisted(() => ({
  getWorkflowDetail: vi.fn(),
  cancelWorkflow: vi.fn(),
  rerunWorkflow: vi.fn(),
  push: vi.fn(),
}));

vi.mock("@/services/api.js", () => ({
  api: {
    getWorkflowDetail: (...args) => mocks.getWorkflowDetail(...args),
    cancelWorkflow: (...args) => mocks.cancelWorkflow(...args),
    rerunWorkflow: (...args) => mocks.rerunWorkflow(...args),
  },
}));

vi.mock("vue-router", () => ({
  useRouter: () => ({ push: mocks.push }),
}));

vi.mock("@/components/pipeline/PipelineMonitorCanvas.vue", () => ({
  default: {
    name: "PipelineMonitorCanvas",
    emits: ["step-selected"],
    template: '<button data-testid="canvas-node" @click="$emit(\'step-selected\', { step_id: 2, label: \'Notify\', status: \'success\' })">canvas</button>',
  },
}));

vi.mock("@/components/pipeline/StepInspectorPanel.vue", () => ({
  default: {
    name: "StepInspectorPanel",
    props: ["step"],
    template: '<div data-testid="step-panel">{{ step?.label || "" }}</div>',
  },
}));

import ExecutionInspector from "../../../src/components/pipeline/ExecutionInspector.vue";

const DETAIL = {
  id: 44,
  rule_id: 7,
  rule_name: "Morning Check",
  status: "running",
  graph: { steps: [], edges: [] },
  timeline: [{ step_id: 1, label: "Condition", step_type: "condition", status: "success" }],
  can_cancel: true,
  can_rerun: false,
};

const stubs = {
  "v-card": { template: '<section><slot /></section>' },
  "v-card-text": { template: '<div><slot /></div>' },
  "v-card-title": { template: '<div><slot /></div>' },
  "v-card-actions": { template: '<div><slot /></div>' },
  "v-divider": { template: '<hr />' },
  "v-spacer": { template: '<span />' },
  "v-chip": { template: '<span><slot /></span>', props: ["color", "size", "variant"] },
  "v-alert": { template: '<div><slot /></div>', props: ["type", "density", "variant"] },
  "v-progress-circular": { template: '<div />' },
  "v-snackbar": { template: '<div><slot /></div>', props: ["modelValue", "color", "timeout"] },
  "v-dialog": { template: '<div v-if="modelValue"><slot /></div>', props: ["modelValue", "maxWidth", "persistent"] },
  "v-btn": {
    template: '<button :disabled="loading" @click="$emit(\'click\')"><slot />{{ icon || "" }}</button>',
    props: ["color", "variant", "size", "prependIcon", "icon", "loading"],
  },
};

function mountInspector(props = {}) {
  return mount(ExecutionInspector, {
    props: { executionId: 44, source: "historic", ...props },
    global: { stubs },
  });
}

beforeEach(() => {
  mocks.getWorkflowDetail.mockReset();
  mocks.cancelWorkflow.mockReset();
  mocks.rerunWorkflow.mockReset();
  mocks.push.mockReset();
  mocks.getWorkflowDetail.mockResolvedValue({ ...DETAIL });
  mocks.cancelWorkflow.mockResolvedValue({ id: 44, status: "cancelled" });
  mocks.rerunWorkflow.mockResolvedValue({ execution_id: 45, rule_id: 7, status: "running" });
});

describe("ExecutionInspector", () => {
  it("shows Cancel when can_cancel and calls cancelWorkflow after confirm", async () => {
    const wrapper = mountInspector();
    await flushPromises();

    await wrapper.findAll("button").find((button) => button.text().includes("Cancel")).trigger("click");
    await wrapper.findAll("button").find((button) => button.text().includes("Confirm")).trigger("click");
    await flushPromises();

    expect(mocks.cancelWorkflow).toHaveBeenCalledWith(44);
  });

  it("shows Rerun when can_rerun and navigates to the new execution", async () => {
    mocks.getWorkflowDetail.mockResolvedValue({ ...DETAIL, status: "completed", can_cancel: false, can_rerun: true });
    const wrapper = mountInspector();
    await flushPromises();

    await wrapper.findAll("button").find((button) => button.text().includes("Rerun")).trigger("click");
    await flushPromises();

    expect(mocks.rerunWorkflow).toHaveBeenCalledWith(44);
    expect(mocks.push).toHaveBeenCalledWith("/admin/executions?tab=live&execution=45");
  });

  it("selecting a node on the canvas drives the StepInspectorPanel", async () => {
    const wrapper = mountInspector();
    await flushPromises();

    await wrapper.find('[data-testid="canvas-node"]').trigger("click");

    expect(wrapper.find('[data-testid="step-panel"]').text()).toContain("Notify");
  });
});
