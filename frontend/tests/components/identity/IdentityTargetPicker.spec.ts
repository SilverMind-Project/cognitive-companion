import { describe, it, expect, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const api = vi.hoisted(() => ({
  getIdentityTargets: vi.fn().mockResolvedValue({
    targets: [
      {
        identity_id: "resident",
        display_name: "Resident",
        is_active: true,
        is_guest: false,
        face_enrolled: true,
      },
      {
        identity_id: "helper",
        display_name: "Helper",
        is_active: true,
        is_guest: true,
        face_enrolled: false,
      },
    ],
    enrollment_available: true,
    gallery_available: true,
  }),
}));
vi.mock("@/services/modules/identity_targets", () => api);

import IdentityTargetPicker from "@/components/identity/IdentityTargetPicker.vue";

const stubs = {
  "v-alert": { template: "<div class='v-alert'><slot /><slot name='append' /></div>" },
  "v-btn": { template: "<button><slot /></button>" },
  "v-autocomplete": {
    props: ["modelValue", "items", "label", "loading", "disabled"],
    emits: ["update:modelValue"],
    template:
      "<select @change=\"$emit('update:modelValue', $event.target.value)\">" +
      "<option v-for='i in items' :key='i.value' :value='i.value' :disabled='i.props.disabled'>" +
      "{{ i.title }}|{{ i.props.subtitle }}</option></select>",
  },
};

async function mountPicker(props: Record<string, unknown> = {}) {
  const wrapper = mount(IdentityTargetPicker, {
    props: { modelValue: null, ...props },
    global: { stubs },
  });
  await flushPromises();
  return wrapper;
}

describe("IdentityTargetPicker", () => {
  it("offers every active member from the shared list", async () => {
    const wrapper = await mountPicker();

    const options = wrapper.findAll("option");
    expect(options.map((o) => o.text())).toEqual(["Resident|", "Helper|Guest"]);
    expect(options.every((o) => o.attributes("disabled") === undefined)).toBe(true);
  });

  it("disables members without enrolled faces when the decision needs one", async () => {
    const wrapper = await mountPicker({ requireEnrolledFace: true });

    const [resident, helper] = wrapper.findAll("option");
    expect(resident.attributes("disabled")).toBeUndefined();
    expect(helper.attributes("disabled")).toBeDefined();
    expect(helper.text()).toBe("Helper|Guest · No enrolled face photos");
  });

  it("emits the chosen member's id", async () => {
    const wrapper = await mountPicker();

    await wrapper.find("select").setValue("resident");

    expect(wrapper.emitted("update:modelValue")?.[0]).toEqual(["resident"]);
  });
});
