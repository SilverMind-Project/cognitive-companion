import { describe, it, expect, vi, beforeEach } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { reactive, ref } from "vue";

vi.mock("@/services/timezone.js", () => ({ formatDateTime: (v: string) => v }));
vi.mock("@/composables/useNotify.js", () => ({ useNotify: () => ({ notify: vi.fn() }) }));
vi.mock("@/composables/useConfirm.js", () => ({
  useConfirm: () => ({
    confirmDialog: ref(false),
    confirmTitle: ref(""),
    confirmText: ref(""),
    confirmLabel: ref("Confirm"),
    cancelLabel: ref("Cancel"),
    confirmColor: ref("error"),
    showConfirm: vi.fn().mockResolvedValue(true),
    require: vi.fn().mockResolvedValue(true),
    onConfirm: vi.fn(),
    onCancel: vi.fn(),
  }),
}));

const { wearablesMock } = vi.hoisted(() => ({ wearablesMock: { value: undefined as unknown } }));
vi.mock("@/composables/useWearables", () => ({
  useWearables: () => wearablesMock.value,
}));

import WearableBindingDialog from "@/components/cts/wearables/WearableBindingDialog.vue";
import WearablesView from "@/views/admin/WearablesView.vue";
import type { WearableDeviceOut } from "@/services/modules/wearables";

const UNBOUND_DEVICE: WearableDeviceOut = {
  id: "22222222-2222-2222-2222-222222222222",
  tag_id: "grandma-clip-1",
  device_kind: "ble_beacon",
  label: "Grandma's clip",
  adapter_id: "ble-home",
  hardware_key: "uuid:1:2",
  is_active: true,
  last_heard_at: null,
  last_battery_fraction: null,
  active_binding: null,
  created_at: "2026-11-19T09:00:00Z",
  updated_at: "2026-11-19T09:00:00Z",
};

function makeWearablesStore() {
  const state = reactive({
    loading: false,
    saving: false,
    forbidden: false,
    error: null as string | null,
    assignments: {
      members: [
        {
          member_id: "sriram",
          member_name: "Sriram",
          devices: [
            {
              device_id: "33333333-3333-3333-3333-333333333333",
              tag_id: "pw5-ble",
              label: "Pixel Watch 5 (BLE)",
              device_kind: "watch" as const,
              adapter_id: "ble-home",
              is_active: true,
              valid_from: "2026-11-19T09:00:00Z",
              consent_recorded_by: "Sriram",
              last_heard_at: null,
              last_battery_fraction: 0.85,
            },
            {
              device_id: "44444444-4444-4444-4444-444444444444",
              tag_id: "pw5-uwb",
              label: "Pixel Watch 5 (UWB)",
              device_kind: "watch" as const,
              adapter_id: "uwb-watch",
              is_active: true,
              valid_from: "2026-11-19T09:00:00Z",
              consent_recorded_by: "Sriram",
              last_heard_at: null,
              last_battery_fraction: 0.85,
            },
          ],
        },
      ],
      unbound_devices: [UNBOUND_DEVICE],
      checked_at: "2026-11-19T10:00:00Z",
    },
    nodes: [],
    floorPlanReady: false,
    floorPlanId: null,
    floorWidthM: null,
    floorHeightM: null,
    floorPlan: null,
    rooms: [],
    bindingHistory: [],
    loadingHistory: false,
    surveyResult: null,
    checkingSurvey: false,
  });

  return {
    state,
    actions: {
      loadAll: vi.fn(),
      addDevice: vi.fn(),
      patchDevice: vi.fn(),
      loadBindingHistory: vi.fn(),
      bindDevice: vi.fn(),
      unbindDevice: vi.fn(),
      addNode: vi.fn(),
      patchNode: vi.fn(),
      removeNode: vi.fn(),
      runSurveyCheck: vi.fn(),
      clearSurvey: vi.fn(),
    },
  };
}

const commonStubs = {
  "v-spacer": { template: "<span />" },
  "v-btn": {
    template: "<button :disabled='disabled' :data-to='to'><slot /></button>",
    props: ["to", "disabled", "loading", "color", "variant"],
  },
  "v-alert": { template: "<div><slot /><slot name='append' /></div>" },
  "v-progress-circular": { template: "<div />" },
  "v-card": { template: "<div><slot /></div>" },
  "v-card-title": { template: "<div><slot /></div>" },
  "v-card-text": { template: "<div><slot /></div>" },
  "v-card-actions": { template: "<div><slot /></div>" },
  "v-dialog": { template: "<div v-if='modelValue'><slot /></div>", props: ["modelValue"] },
  "v-divider": { template: "<hr />" },
  "v-chip": { template: "<span><slot /></span>" },
  "v-table": { template: "<table><slot /></table>" },
  "v-row": { template: "<div><slot /></div>" },
  "v-col": { template: "<div><slot /></div>" },
  "v-text-field": {
    template:
      "<input :value='modelValue' @input='$emit(\"update:modelValue\", $event.target.value)' />",
    props: ["modelValue", "label"],
  },
  "v-select": {
    template:
      "<select :value='modelValue' @change='$emit(\"update:modelValue\", $event.target.value)' />",
    props: ["modelValue", "items"],
  },
  "v-checkbox": {
    template:
      "<input type='checkbox' :checked='modelValue' @change='$emit(\"update:modelValue\", $event.target.checked)' />",
    props: ["modelValue", "label"],
  },
  AppDialog: {
    template: "<div v-if='modelValue'><slot /></div>",
    props: ["modelValue"],
  },
  CcSegmentedToggle: {
    template:
      "<div><button v-for='o in options' :key='o.value' @click='$emit(\"update:modelValue\", o.value)'>{{ o.label }}</button></div>",
    props: ["modelValue", "options"],
  },
  IdentityTargetPicker: {
    template:
      "<input data-test='picker-input' :value='modelValue' @input='$emit(\"update:modelValue\", $event.target.value)' />",
    props: ["modelValue", "label"],
  },
  RfNodeFloorPlanCanvas: { template: "<div data-test='rf-canvas-stub' />" },
};

beforeEach(() => {
  wearablesMock.value = makeWearablesStore();
});

describe("WearablesView", () => {
  it("groups all active devices bound to one member together and triggers quick unbind", async () => {
    const wrapper = mount(WearablesView, { global: { stubs: commonStubs } });
    await flushPromises();

    const store = wearablesMock.value as ReturnType<typeof makeWearablesStore>;
    expect(store.actions.loadAll).toHaveBeenCalledTimes(1);

    const memberCard = wrapper.get("[data-test='member-wearables-sriram']");
    expect(memberCard.text()).toContain("2 devices");
    expect(memberCard.text()).toContain("pw5-ble");
    expect(memberCard.text()).toContain("pw5-uwb");

    await wrapper.get("[data-test='quick-unbind-pw5-ble']").trigger("click");
    expect(store.actions.unbindDevice).toHaveBeenCalledWith("33333333-3333-3333-3333-333333333333");
  });
});

describe("WearableBindingDialog", () => {
  it("requires explicit consent checkbox and consent_recorded_by before enabling bind", async () => {
    const wrapper = mount(WearableBindingDialog, {
      props: {
        modelValue: true,
        device: UNBOUND_DEVICE,
        history: [],
        loadingHistory: false,
        saving: false,
      },
      global: { stubs: commonStubs },
    });

    const submitBtn = () => wrapper.get("[data-test='bind-submit-btn']");
    expect(submitBtn().attributes("disabled")).toBeDefined();

    await wrapper.get("[data-test='bind-member-picker']").setValue("amma");
    await wrapper.get("[data-test='consent-recorded-by']").setValue("Sriram");
    // Still disabled without checking the consent box.
    expect(submitBtn().attributes("disabled")).toBeDefined();

    await wrapper.get("[data-test='consent-checkbox']").setValue(true);
    expect(submitBtn().attributes("disabled")).toBeUndefined();

    await submitBtn().trigger("click");
    expect(wrapper.emitted("bind")).toEqual([
      [
        UNBOUND_DEVICE.id,
        {
          member_id: "amma",
          consent_confirmed: true,
          consent_recorded_by: "Sriram",
        },
      ],
    ]);
  });
});
