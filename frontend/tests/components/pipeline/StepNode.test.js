import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";

vi.mock("@vue-flow/core", () => ({
  Position: { Left: "left", Right: "right" },
  Handle: {
    name: "Handle",
    props: ["id", "type", "position", "connectable"],
    template: `
      <div
        class="mock-handle"
        :data-id="id"
        :data-type="type"
        :data-position="position"
        :data-connectable="String(connectable)"
      />
    `,
  },
}));

import StepNode from "../../../src/components/pipeline/nodes/StepNode.vue";

const stubs = {
  "v-icon": { props: ["color"], template: '<span data-testid="icon"><slot /></span>' },
  "v-chip": { props: ["color", "variant", "prependIcon"], template: '<span class="mock-chip"><slot /></span>' },
};

function makeStep(overrides = {}) {
  return {
    id: 10,
    step_type: "notification",
    label: "notify_family",
    enabled: true,
    config_json: { alert_level: "warning", message_template: "Kitchen motion detected" },
    ...overrides,
  };
}

function mountNode({
  step = makeStep(),
  outputPorts = ["main"],
  readonly = false,
  mountOptions = {},
} = {}) {
  return mount(StepNode, {
    props: { data: { step, outputPorts, readonly } },
    global: { stubs },
    ...mountOptions,
  });
}

describe("StepNode", () => {
  it("renders step display name and label", () => {
    const wrapper = mountNode();
    expect(wrapper.text()).toContain("Notification");
    expect(wrapper.text()).toContain("notify_family");
  });

  it("renders one output handle for a main-only step", () => {
    const wrapper = mountNode({ outputPorts: ["main"] });
    const handles = wrapper.findAll(".mock-handle");
    expect(handles.filter((handle) => handle.attributes("data-type") === "source")).toHaveLength(1);
    expect(wrapper.find(".step-node__port-label").exists()).toBe(false);
  });

  it("renders true and false output handles for a condition step", () => {
    const wrapper = mountNode({
      step: makeStep({ step_type: "condition", config_json: { expression: "x > 1" } }),
      outputPorts: ["true", "false"],
    });
    const sourceIds = wrapper
      .findAll(".mock-handle")
      .filter((handle) => handle.attributes("data-type") === "source")
      .map((handle) => handle.attributes("data-id"));
    expect(sourceIds).toEqual(["true", "false"]);
    expect(wrapper.text()).toContain("true");
    expect(wrapper.text()).toContain("false");
  });

  it("lets double-click bubble to the Vue Flow node wrapper", async () => {
    const attachTo = document.createElement("div");
    document.body.appendChild(attachTo);
    const wrapper = mountNode({ mountOptions: { attachTo } });
    const onDoubleClick = vi.fn();
    wrapper.element.parentElement.addEventListener("dblclick", onDoubleClick);

    await wrapper.trigger("dblclick");

    expect(onDoubleClick).toHaveBeenCalledOnce();
    wrapper.unmount();
    attachTo.remove();
  });

  it("applies disabled styling when step is disabled", () => {
    const wrapper = mountNode({ step: makeStep({ enabled: false }) });
    expect(wrapper.classes()).toContain("step-node--disabled");
  });

  it("readonly mode disables handles", () => {
    const wrapper = mountNode({ readonly: true });
    for (const handle of wrapper.findAll(".mock-handle")) {
      expect(handle.attributes("data-connectable")).toBe("false");
    }
  });

  it("readonly mode applies status styling", () => {
    const wrapper = mountNode({ readonly: true, step: makeStep({ status: "running" }) });
    expect(wrapper.classes()).toContain("step-node--status-running");
  });
});
