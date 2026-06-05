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
  started_at: "2026-05-29T10:00:00Z",
  completed_at: null,
  trigger_summary: "Manual trigger",
  cooloff_triggered: false,
  error: null,
  graph: { steps: [], edges: [] },
  timeline: [{
    step_id: 1,
    label: "Condition",
    step_type: "condition",
    status: "success",
    resolved_config: { expression: "true" },
    outputs: { matched: true },
  }],
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
  "v-list": { template: '<ul><slot /></ul>', props: ["density"] },
  "v-list-item": { template: '<li><slot name="prepend" /><slot /><slot name="append" /></li>' },
  "v-list-item-title": { template: '<span><slot /></span>' },
  "v-list-item-subtitle": { template: '<span><slot /></span>' },
  "v-progress-circular": { template: '<div />' },
  "v-snackbar": { template: '<div><slot /></div>', props: ["modelValue", "color", "timeout"] },
  "v-dialog": { template: '<div v-if="modelValue"><slot /></div>', props: ["modelValue", "maxWidth", "persistent"] },
  "v-btn": {
    inheritAttrs: false,
    emits: ["click"],
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
    expect(mocks.push).toHaveBeenCalledWith({
      name: "admin-executions",
      query: { tab: "live", execution: 45, rule_id: 7 },
    });
  });

  it("selecting a node on the canvas drives the StepInspectorPanel", async () => {
    const wrapper = mountInspector();
    await flushPromises();

    await wrapper.find('[data-testid="canvas-node"]').trigger("click");

    expect(wrapper.find('[data-testid="step-panel"]').text()).toContain("Notify");
  });

  it("shows execution metadata, errors, and cool-off state", async () => {
    mocks.getWorkflowDetail.mockResolvedValue({
      ...DETAIL,
      status: "failed",
      completed_at: "2026-05-29T10:01:05Z",
      error: "Notification delivery failed",
      cooloff_triggered: true,
      can_cancel: false,
      can_rerun: true,
    });
    const wrapper = mountInspector();
    await flushPromises();

    expect(wrapper.text()).toContain("Manual trigger");
    expect(wrapper.text()).toContain("Duration 1m 5s");
    expect(wrapper.find('[data-testid="execution-error"]').text()).toContain("Notification delivery failed");
    expect(wrapper.find('[data-testid="cooloff-alert"]').exists()).toBe(true);
  });

  it("copies resolved configs and outputs for all timeline steps", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    const wrapper = mountInspector();
    await flushPromises();

    await wrapper.findAll("button").find((button) => button.text().includes("Copy data")).trigger("click");
    await flushPromises();

    expect(writeText).toHaveBeenCalledOnce();
    const copied = JSON.parse(writeText.mock.calls[0][0]);
    expect(copied["steps.Condition.resolved_config"]).toEqual({ expression: "true" });
    expect(copied["steps.Condition.outputs"]).toEqual({ matched: true });
  });

  it("polls active live executions and allows polling to be paused", async () => {
    vi.useFakeTimers();
    const wrapper = mountInspector({ source: "live" });
    await vi.runAllTicks();
    await Promise.resolve();

    expect(wrapper.vm.polling).toBe(true);
    await wrapper.findAll("button").find((button) => button.text().includes("Pause")).trigger("click");
    expect(wrapper.vm.polling).toBe(false);

    wrapper.unmount();
    vi.useRealTimers();
  });
});
