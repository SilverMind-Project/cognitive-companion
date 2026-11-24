import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import KioskGate from "@/components/companion/KioskGate.vue";

const AppDialog = {
  name: "AppDialog",
  props: {
    modelValue: Boolean,
    title: String,
    confirmLabel: String,
    persistent: Boolean,
    size: String,
  },
  emits: ["confirm", "update:modelValue"],
  template: `<div v-if="modelValue" class="app-dialog" :data-size="size">
    <slot /><button class="confirm" @click="$emit('confirm')">{{ confirmLabel }}</button></div>`,
};

const stubs = {
  AppDialog,
  "v-btn": { emits: ["click"], template: "<button @click=\"$emit('click')\"><slot /></button>" },
  "v-form": { template: "<form><slot /></form>" },
  "v-text-field": { template: "<input />" },
  "v-switch": { template: "<input type='checkbox' />" },
  "v-select": { template: "<select />" },
};

function state(settingsUnlocked) {
  return {
    isActive: true,
    gateVisible: false,
    settingsUnlocked,
    settings: { kioskEnabled: true, surfaceId: "kitchen-tablet", roomId: 2, pin: "1234" },
    rooms: [],
    roomsLoading: false,
  };
}

describe("KioskGate settings", () => {
  it("uses the shared dialog shell, unlocking first and then saving", async () => {
    const locked = mount(KioskGate, { props: { state: state(false) }, global: { stubs } });
    await locked.find(".kiosk-settings-btn").trigger("click");

    const dialog = locked.findComponent({ name: "AppDialog" });
    expect(dialog.props("title")).toBe("Kiosk settings");
    expect(dialog.props("persistent")).toBe(true);
    expect(dialog.props("confirmLabel")).toBe("Unlock");
    await locked.find(".confirm").trigger("click");
    expect(locked.emitted("unlock-settings")).toBeTruthy();

    const unlocked = mount(KioskGate, { props: { state: state(true) }, global: { stubs } });
    await unlocked.find(".kiosk-settings-btn").trigger("click");
    await unlocked.find(".confirm").trigger("click");
    expect(unlocked.emitted("save-settings")[0][0].surfaceId).toBe("kitchen-tablet");
  });
});

describe("KioskGate screen test", () => {
  it("tests the surface id being entered and shows the result", async () => {
    const unlocked = state(true);
    unlocked.surfaceTest = { status: "offline", message: "No screen is connected as this id." };
    const wrapper = mount(KioskGate, { props: { state: unlocked }, global: { stubs } });
    await wrapper.find(".kiosk-settings-btn").trigger("click");

    await wrapper.find('[data-test="kiosk-test-surface"]').trigger("click");

    expect(wrapper.emitted("test-surface")[0]).toEqual(["kitchen-tablet"]);
    const result = wrapper.find('[data-test="kiosk-test-surface-result"]');
    expect(result.text()).toBe("No screen is connected as this id.");
    expect(result.classes()).toContain("kiosk-surface-test__result--offline");
  });

  it("cannot test before a surface id is entered", async () => {
    const unlocked = state(true);
    unlocked.settings.surfaceId = "";
    const wrapper = mount(KioskGate, { props: { state: unlocked }, global: { stubs } });
    await wrapper.find(".kiosk-settings-btn").trigger("click");

    const button = wrapper.find('[data-test="kiosk-test-surface"]');
    expect(button.attributes("disabled")).toBeDefined();
    await button.trigger("click");
    expect(wrapper.emitted("test-surface")).toBeUndefined();
  });
});
