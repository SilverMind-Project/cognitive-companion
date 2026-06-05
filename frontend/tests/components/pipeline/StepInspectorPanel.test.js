import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";

import StepInspectorPanel from "../../../src/components/pipeline/StepInspectorPanel.vue";

const stubs = {
  "v-card": { template: "<section><slot /></section>", props: ["variant"] },
  "v-card-title": { template: "<header><slot /></header>" },
  "v-card-text": { template: "<div><slot /></div>" },
  "v-icon": { template: "<i />", props: ["icon"] },
  "v-spacer": { template: "<span />" },
  "v-chip": { template: "<span><slot /></span>", props: ["color", "size", "variant", "prependIcon"] },
  "v-alert": { template: "<div><slot /></div>", props: ["type", "density", "variant"] },
  "v-tabs": { template: "<div><slot /></div>", props: ["modelValue", "density"] },
  "v-tab": { template: "<button><slot /></button>", props: ["value"] },
  "v-window": { template: "<div><slot /></div>", props: ["modelValue"] },
  "v-window-item": { template: "<div><slot /></div>", props: ["value"] },
};

describe("StepInspectorPanel", () => {
  it("surfaces timing, output port, cancellation, and step errors", () => {
    const wrapper = mount(StepInspectorPanel, {
      props: {
        step: {
          step_id: 4,
          label: "Notify caregiver",
          status: "failed",
          elapsed_seconds: 0.125,
          output_port: "failure",
          cancellation_observed: true,
          error: "Webhook timed out",
        },
      },
      global: { stubs },
    });

    expect(wrapper.text()).toContain("125 ms");
    expect(wrapper.text()).toContain("failure");
    expect(wrapper.text()).toContain("Cancellation observed");
    expect(wrapper.text()).toContain("Webhook timed out");
  });
});
