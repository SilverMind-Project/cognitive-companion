import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";

const mocks = vi.hoisted(() => ({
  api: { testRunGateGraph: vi.fn() },
  notify: { error: vi.fn() },
}));

vi.mock("@/services/api.js", () => ({ api: mocks.api }));
vi.mock("@/composables/useNotify.js", () => ({ useNotify: () => ({ notify: mocks.notify }) }));

import GateEditorDialog from "@/components/routines/GateEditorDialog.vue";

// Stub AppDialog so we can check props and render the slot inline.
const AppDialogStub = {
  name: "AppDialog",
  template: `<div class="app-dialog-stub" :class="size">
    <slot />
    <button class="close-btn" @click="$emit('update:modelValue', false)">Close</button>
  </div>`,
  props: ["modelValue", "size", "icon", "label", "title", "confirmLabel"],
};

const PipelineCanvasStub = {
  name: "PipelineCanvas",
  props: ["ruleId", "mode"],
  template: `<div class="pipeline-canvas-stub" :data-rule-id="ruleId" :data-mode="mode" />`,
};

const stubs = {
  AppDialog: AppDialogStub,
  PipelineCanvas: PipelineCanvasStub,
  "v-divider": { template: "<hr />" },
  "v-icon": { template: "<i><slot /></i>" },
  "v-text-field": {
    props: ["modelValue", "label"],
    template: `<input :data-label="label" />`,
  },
  "v-select": {
    props: ["modelValue", "items", "label"],
    template: `<select :data-label="label" />`,
  },
  "v-btn": {
    props: ["loading"],
    template: `<button @click="$emit('click')"><slot /></button>`,
  },
  "v-alert": { props: ["type"], template: `<div class="alert" :data-type="type"><slot /></div>` },
};

function mountGateEditorDialog(props) {
  return mount(GateEditorDialog, {
    props: { modelValue: true, gate: {}, ...props },
    global: { stubs, mocks: { $vuetify: { display: { smAndDown: false } } } },
  });
}

describe("GateEditorDialog", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders inside an xl AppDialog", () => {
    const wrapper = mountGateEditorDialog({});
    const appDialog = wrapper.findComponent(AppDialogStub);
    expect(appDialog.exists()).toBe(true);
    expect(appDialog.props("size")).toBe("xl");
    expect(appDialog.props("title")).toBe("Edit Vision Logic");
  });

  it("emits update:modelValue when closed", async () => {
    const wrapper = mountGateEditorDialog({});
    await wrapper.find(".close-btn").trigger("click");
    expect(wrapper.emitted("update:modelValue")[0]).toEqual([false]);
  });

  it("prompts to pick a preset when no gate graph is attached", () => {
    const wrapper = mountGateEditorDialog({ gate: {} });
    expect(wrapper.findComponent(PipelineCanvasStub).exists()).toBe(false);
    expect(wrapper.text()).toContain("Choose a preset first");
  });

  it("hosts the scoped canvas in gate mode when a gate exists", () => {
    const wrapper = mountGateEditorDialog({ gate: { vision: { gate_graph_rule_id: 7 } } });
    const canvas = wrapper.findComponent(PipelineCanvasStub);
    expect(canvas.exists()).toBe(true);
    expect(canvas.props("ruleId")).toBe(7);
    expect(canvas.props("mode")).toBe("gate");
  });

  it("runs a preview and renders the verdict + cost", async () => {
    mocks.api.testRunGateGraph.mockResolvedValue({
      complete: true,
      confidence: 0.9,
      reason: "kettle on hob",
      cost: { model_calls: 1, frames: 3, latency_ms: 42 },
      profile: "confirm",
    });
    const wrapper = mountGateEditorDialog({ gate: { vision: { gate_graph_rule_id: 7 } } });
    const runBtn = wrapper.findAll("button").find((b) => b.text().includes("Run preview"));
    await runBtn.trigger("click");
    await flushPromises();
    expect(mocks.api.testRunGateGraph).toHaveBeenCalledWith(7, expect.any(Object));
    expect(wrapper.text()).toContain("Complete");
    expect(wrapper.text()).toContain("90%");
    expect(wrapper.text()).toContain("1 model call");
  });
});
