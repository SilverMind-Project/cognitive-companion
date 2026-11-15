import { describe, it, expect, vi } from "vitest";
import { mount } from "@vue/test-utils";

const targetsApi = vi.hoisted(() => ({
  getIdentityTargets: vi.fn().mockResolvedValue({
    targets: [],
    enrollment_available: true,
    gallery_available: true,
  }),
}));
vi.mock("@/services/modules/identity_targets", () => targetsApi);

import VisitorNameDialog from "@/components/admin/visitors/VisitorNameDialog.vue";
import { useIdentityTargetsStore } from "@/stores/identityTargets";

const stubs = {
  AppDialog: {
    template:
      "<div><slot /><button class='confirm' @click=\"$emit('confirm')\" :disabled='confirmDisabled'>Confirm</button></div>",
    props: ["modelValue", "confirmDisabled", "confirmLoading"],
    emits: ["update:modelValue", "confirm"],
  },
  "v-alert": { template: "<div class='v-alert'><slot /><slot name='append' /></div>" },
  "v-btn": { template: "<button class='v-btn' @click=\"$emit('click')\"><slot /></button>" },
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

  it("warns, blocks naming, and offers attribution when the person is already enrolled", async () => {
    useIdentityTargetsStore().targets = [
      { identity_id: "resident", display_name: "Resident", is_active: true, is_guest: false },
    ];
    const wrapper = mountDialog();
    const inputs = wrapper.findAll("input");

    await inputs[0].setValue("Resident");

    const warning = wrapper.get("[data-test='already-enrolled']");
    expect(warning.text()).toContain("Resident is already in the household");
    expect(wrapper.get(".confirm").attributes("disabled")).toBeDefined();
    await warning.get(".v-btn").trigger("click");
    expect(wrapper.emitted("attribute")[0]).toEqual(["resident"]);
  });

  it("only warns when the name matches but the chosen id is new", async () => {
    useIdentityTargetsStore().targets = [
      { identity_id: "resident", display_name: "Resident", is_active: true, is_guest: false },
    ];
    const wrapper = mountDialog();
    const inputs = wrapper.findAll("input");

    await inputs[0].setValue("Resident");
    await inputs[1].setValue("resident-two");

    expect(wrapper.find("[data-test='already-enrolled']").exists()).toBe(true);
    expect(wrapper.get(".confirm").attributes("disabled")).toBeUndefined();
  });

  it("loads the household list each time it opens", async () => {
    targetsApi.getIdentityTargets.mockClear();
    const wrapper = mountDialog({ modelValue: false });
    await wrapper.setProps({ modelValue: true });
    expect(targetsApi.getIdentityTargets).toHaveBeenCalledTimes(1);
  });
});
