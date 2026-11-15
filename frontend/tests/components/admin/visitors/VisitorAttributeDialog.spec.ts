import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";

import VisitorAttributeDialog from "@/components/admin/visitors/VisitorAttributeDialog.vue";

const stubs = {
  AppDialog: {
    props: ["modelValue", "title", "confirmDisabled", "confirmLoading"],
    emits: ["update:modelValue", "confirm"],
    template:
      "<div><h3>{{ title }}</h3><slot />" +
      "<button class='confirm' :disabled='confirmDisabled' @click=\"$emit('confirm')\">OK</button></div>",
  },
  IdentityTargetPicker: {
    props: { modelValue: { type: String, default: null }, requireEnrolledFace: Boolean },
    emits: ["update:modelValue"],
    template:
      "<button class='pick' :data-enrolled='requireEnrolledFace' @click=\"$emit('update:modelValue', 'resident')\">pick</button>",
  },
};

function mountDialog(count = 1) {
  return mount(VisitorAttributeDialog, {
    props: { modelValue: true, count, saving: false },
    global: { stubs },
  });
}

describe("VisitorAttributeDialog", () => {
  it("asks for an enrolled member, states that nothing is enrolled, then submits the choice", async () => {
    const wrapper = mountDialog(3);

    expect(wrapper.find("h3").text()).toBe("Whose faces are these 3 groups?");
    expect(wrapper.find(".pick").attributes("data-enrolled")).toBe("true");
    expect(wrapper.get("[data-test='attribute-effect']").text()).toContain(
      "Nothing is added to their enrollment",
    );
    expect(wrapper.find(".confirm").attributes("disabled")).toBeDefined();

    await wrapper.find(".pick").trigger("click");
    await wrapper.find(".confirm").trigger("click");

    expect(wrapper.emitted("submit")?.[0]).toEqual(["resident"]);
  });

  it("uses the singular title for one group", () => {
    expect(mountDialog(1).find("h3").text()).toBe("Whose faces are these?");
  });
});
