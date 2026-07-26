import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import SignalEmitConfig, { stepDefaults } from "@/components/pipeline/steps/SignalEmitConfig.vue";

const stubs = {
  "v-select": {
    name: "v-select",
    props: ["modelValue", "items", "label"],
    emits: ["update:modelValue"],
    template: '<select :data-label="label"></select>',
  },
  "v-row": { template: "<div><slot /></div>" },
  "v-col": { template: "<div><slot /></div>" },
  "v-text-field": {
    props: ["modelValue", "label"],
    template: '<input :data-label="label" />',
  },
  "v-checkbox": {
    props: ["modelValue", "label"],
    template: '<input type="checkbox" :data-label="label" />',
  },
  TemplateInput: {
    name: "TemplateInput",
    props: ["modelValue", "label"],
    template: '<textarea :data-label="label"></textarea>',
  },
};

function mountConfig(modelValue = {}) {
  return mount(SignalEmitConfig, {
    props: { modelValue: { ...stepDefaults, ...modelValue }, tab: "general" },
    global: { stubs },
  });
}

describe("SignalEmitConfig", () => {
  it("offers every CC-local signal kind, mirroring backend.services.cts.signal_config.CC_LOCAL_SIGNAL_KINDS", () => {
    const wrapper = mountConfig();
    const kindSelect = wrapper.findComponent({ name: "v-select" });
    expect(kindSelect.props("items")).toEqual([
      "inferred_dwell_exceeded",
      "tea_intent_suspected",
      "hygiene_routine_missed",
    ]);
  });
});
