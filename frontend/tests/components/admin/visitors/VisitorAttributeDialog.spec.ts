import { describe, it, expect, vi, beforeEach } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";

vi.mock("@/services/modules/identity_targets", async () =>
  (await import("../../../support/reviewVocabulary")).identityTargetsModuleMock([
    {
      identity_id: "resident",
      display_name: "Resident",
      is_active: true,
      is_guest: false,
      face_enrolled: true,
    },
  ]),
);

import VisitorAttributeDialog from "@/components/admin/visitors/VisitorAttributeDialog.vue";
import { useIdentityTargetsStore } from "@/stores/identityTargets";

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
  beforeEach(() => setActivePinia(createPinia()));

  it("asks for an enrolled member, states the server's effect, then submits the choice", async () => {
    const wrapper = mountDialog(3);
    await flushPromises();

    expect(wrapper.find("h3").text()).toBe("Whose faces are these 3 groups?");
    expect(wrapper.find(".pick").attributes("data-enrolled")).toBe("true");
    expect(wrapper.get("[data-test='attribute-effect']").text()).toContain(
      "nothing added to the chosen member's enrollment",
    );
    expect(wrapper.find(".confirm").attributes("disabled")).toBeDefined();

    await wrapper.find(".pick").trigger("click");
    await useIdentityTargetsStore().load();
    // The preview names the member once one is chosen.
    expect(wrapper.get("[data-test='attribute-effect']").text()).toBe(
      "Server: marked as Resident's faces; nothing added to Resident's enrollment.",
    );
    await wrapper.find(".confirm").trigger("click");

    expect(wrapper.emitted("submit")?.[0]).toEqual(["resident"]);
  });

  it("uses the singular title for one group", () => {
    expect(mountDialog(1).find("h3").text()).toBe("Whose faces are these?");
  });
});
