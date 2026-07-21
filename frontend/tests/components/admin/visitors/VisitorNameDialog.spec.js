import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";

import VisitorNameDialog from "@/components/admin/visitors/VisitorNameDialog.vue";

const stubs = {
  AppDialog: {
    template:
      "<div><slot /><button class='confirm' @click=\"$emit('confirm')\" :disabled='confirmDisabled'>Confirm</button></div>",
    props: ["modelValue", "confirmDisabled", "confirmLoading"],
    emits: ["update:modelValue", "confirm"],
  },
  "v-text-field": {
    template:
      "<div><input :value='modelValue' @input=\"$emit('update:modelValue', $event.target.value)\" /><span class='err'>{{ (errorMessages || []).join(',') }}</span></div>",
    props: ["modelValue", "errorMessages", "label"],
    emits: ["update:modelValue"],
  },
};

function mountDialog(props = {}) {
  return mount(VisitorNameDialog, {
    props: { modelValue: true, saving: false, ...props },
    global: { stubs },
  });
}

describe("VisitorNameDialog", () => {
  it("auto-suggests a slug person_id from the name", async () => {
    const wrapper = mountDialog();

    const inputs = wrapper.findAll("input");
    await inputs[0].setValue("Nurse Priya");

    expect(inputs[1].element.value).toBe("nurse-priya");
  });

  it("does not overwrite a manually edited person_id", async () => {
    const wrapper = mountDialog();
    const inputs = wrapper.findAll("input");

    await inputs[1].setValue("custom-id");
    await inputs[0].setValue("Nurse Priya");

    expect(inputs[1].element.value).toBe("custom-id");
  });

  it("rejects an invalid person_id (uppercase, spaces)", async () => {
    const wrapper = mountDialog();
    const inputs = wrapper.findAll("input");

    await inputs[0].setValue("Nurse Priya");
    await inputs[1].setValue("Nurse Priya!");

    const errs = wrapper.findAll(".err");
    expect(errs[1].text()).toContain("Lowercase letters");
  });

  it("requires a non-empty name", () => {
    const wrapper = mountDialog();

    const errs = wrapper.findAll(".err");
    expect(errs[0].text()).toContain("required");
  });

  it("emits submit with name and personId on confirm when valid", async () => {
    const wrapper = mountDialog();
    const inputs = wrapper.findAll("input");
    await inputs[0].setValue("Nurse Priya");

    await wrapper.find(".confirm").trigger("click");

    expect(wrapper.emitted("submit")[0]).toEqual([
      { name: "Nurse Priya", personId: "nurse-priya" },
    ]);
  });

  it("resets fields each time the dialog reopens", async () => {
    const wrapper = mountDialog({ modelValue: false });
    let inputs = wrapper.findAll("input");
    await inputs[0].setValue("Leftover Name");

    await wrapper.setProps({ modelValue: true });
    inputs = wrapper.findAll("input");

    expect(inputs[0].element.value).toBe("");
    expect(inputs[1].element.value).toBe("");
  });
});
