import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import GateVerdictConfig, { stepDefaults } from "@/components/pipeline/steps/GateVerdictConfig.vue";

const stubs = {
  "v-alert": { template: "<div><slot /></div>" },
  "v-text-field": {
    name: "v-text-field",
    props: ["modelValue", "label"],
    emits: ["update:modelValue"],
    template: `<input :data-label="label" :value="modelValue"
      @input="$emit('update:modelValue', $event.target.value)" />`,
  },
  // The shared condition expression widget (reused, not reinvented).
  TemplateInput: {
    name: "TemplateInput",
    props: ["modelValue", "label"],
    emits: ["update:modelValue"],
    template: `<textarea :data-label="label" :value="modelValue"
      @input="$emit('update:modelValue', $event.target.value)" />`,
  },
};

function mountConfig(modelValue = {}) {
  return mount(GateVerdictConfig, {
    props: { modelValue: { ...stepDefaults, ...modelValue }, tab: "general" },
    global: { stubs },
  });
}

describe("GateVerdictConfig", () => {
  it("reuses the condition expression widget for complete_if", () => {
    const wrapper = mountConfig();
    const widget = wrapper.findComponent({ name: "TemplateInput" });
    expect(widget.exists()).toBe(true);
    expect(widget.props("label")).toBe("Complete if (expression)");
  });

  it("emits complete_if edits", async () => {
    const wrapper = mountConfig();
    const expr = wrapper.find("textarea");
    expr.element.value = "steps.llm_call_1.outputs.vision_response.complete";
    await expr.trigger("input");
    const emitted = wrapper.emitted("update:modelValue").at(-1)[0];
    expect(emitted.complete_if).toBe("steps.llm_call_1.outputs.vision_response.complete");
  });

  it("emits confidence_path and min_confidence edits", async () => {
    const wrapper = mountConfig();
    const conf = wrapper.find('[data-label="Confidence path"]');
    conf.element.value = "steps.llm_call_1.outputs.vision_response.confidence";
    await conf.trigger("input");
    expect(wrapper.emitted("update:modelValue").at(-1)[0].confidence_path).toBe(
      "steps.llm_call_1.outputs.vision_response.confidence",
    );

    const minConf = wrapper.find('[data-label="Minimum confidence"]');
    minConf.element.value = "0.8";
    await minConf.trigger("input");
    expect(wrapper.emitted("update:modelValue").at(-1)[0].min_confidence).toBe(0.8);
  });
});
