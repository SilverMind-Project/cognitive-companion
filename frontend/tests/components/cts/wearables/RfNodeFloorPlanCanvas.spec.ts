import { describe, it, expect, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { computed } from "vue";

vi.mock("@/services/timezone.js", () => ({ formatDateTime: (v: string) => `FMT:${v}` }));
vi.mock("@/composables/useChartTheme.js", () => ({
  useChartTheme: () => ({ chartTheme: computed(() => ({})) }),
}));

import RfNodeFloorPlanCanvas from "@/components/cts/wearables/RfNodeFloorPlanCanvas.vue";
import type { RfNodeOut } from "@/services/modules/wearables";

const stubs = {
  "v-card": { template: "<div><slot /></div>" },
  "v-card-title": { template: "<div><slot /></div>" },
  "v-card-text": { template: "<div><slot /></div>" },
  "v-divider": { template: "<hr />" },
  "v-icon": { template: "<i />" },
  "v-row": { template: "<div><slot /></div>" },
  "v-col": { template: "<div><slot /></div>" },
  "v-btn": {
    template:
      "<button :disabled='disabled' :data-to='to' @click='$emit(\"click\")'><slot /></button>",
    props: ["to", "disabled", "loading"],
  },
  "v-text-field": {
    template:
      "<input :value='modelValue' @input='$emit(\"update:modelValue\", $event.target.value)' />",
    props: ["modelValue", "disabled", "label", "hint", "placeholder"],
  },
  "v-select": {
    template:
      "<select :value='modelValue' @change='$emit(\"update:modelValue\", $event.target.value)'><option v-for='it in items' :key='it.value ?? it' :value='it.value ?? it'>{{ it.title ?? it }}</option></select>",
    props: ["modelValue", "items", "label"],
  },
  "v-alert": {
    template: "<div class='v-alert' :data-type='type'><slot /></div>",
    props: ["type"],
  },
};

const SAMPLE_NODE: RfNodeOut = {
  id: "11111111-1111-1111-1111-111111111111",
  anchor_id: "node-lr-1",
  label: "Living Room BLE",
  adapter_id: "ble-home",
  node_role: "receiver",
  technology: "ble_rssi",
  room_id: 1,
  room_name: "Living Room",
  x_norm: 0.25,
  y_norm: 0.5,
  x_m: 2.5,
  y_m: 4.0,
  z_m: 1.2,
  is_active: true,
  placement_residual_m: null,
  firmware_version: "ESPresense 3.3.2",
  last_heard_at: "2026-11-21T14:00:00Z",
  last_heard_age_s: 12.0,
  uwb_address_hex: null,
  uwb_channel: null,
  uwb_preamble_index: null,
  created_at: "2026-11-19T10:00:00Z",
  updated_at: "2026-11-19T10:00:00Z",
};

describe("RfNodeFloorPlanCanvas", () => {
  it("renders a blocking empty state linking to floor plan when plan or scale is missing", () => {
    const wrapper = mount(RfNodeFloorPlanCanvas, {
      props: {
        floorPlanReady: false,
        floorPlanUrl: null,
        floorWidthM: null,
        floorHeightM: null,
        nodes: [],
        rooms: [],
        saving: false,
        surveyResult: null,
        checkingSurvey: false,
      },
      global: { stubs },
    });

    expect(wrapper.find("[data-test='no-floor-plan']").exists()).toBe(true);
    expect(wrapper.get("[data-test='go-floor-plan-btn']").attributes("data-to")).toBe(
      "/admin/tracking?panel=live-floor",
    );
    expect(wrapper.find("[data-test='rf-floor-svg']").exists()).toBe(false);
  });

  it("updates normalized coordinates when dragging a placed RF node", async () => {
    const wrapper = mount(RfNodeFloorPlanCanvas, {
      props: {
        floorPlanReady: true,
        floorPlanUrl: "https://example.test/floor.png",
        floorWidthM: 10,
        floorHeightM: 8,
        nodes: [SAMPLE_NODE],
        rooms: [],
        saving: false,
        surveyResult: null,
        checkingSurvey: false,
      },
      global: { stubs },
    });

    const svgEl = wrapper.get("[data-test='rf-floor-svg']").element as SVGSVGElement;
    vi.spyOn(svgEl, "getBoundingClientRect").mockReturnValue({
      left: 0,
      top: 0,
      width: 200,
      height: 100,
      right: 200,
      bottom: 100,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    });

    await wrapper.get("[data-test='rf-node-marker-node-lr-1']").trigger("mousedown");
    await wrapper
      .get("[data-test='rf-floor-svg']")
      .trigger("mousemove", { clientX: 120, clientY: 30 });
    await wrapper.get("[data-test='rf-floor-svg']").trigger("mouseup");

    const emitted = wrapper.emitted("update-node");
    expect(emitted).toBeTruthy();
    expect(emitted?.[0]).toEqual([SAMPLE_NODE.id, { x_norm: 0.6, y_norm: 0.3 }]);
  });

  it("renders a warning when tape-distance survey check exceeds tolerance", () => {
    const wrapper = mount(RfNodeFloorPlanCanvas, {
      props: {
        floorPlanReady: true,
        floorPlanUrl: "https://example.test/floor.png",
        floorWidthM: 10,
        floorHeightM: 8,
        nodes: [SAMPLE_NODE],
        rooms: [],
        saving: false,
        surveyResult: {
          x_m: 2.5,
          y_m: 4.0,
          z_m: 1.2,
          tolerance_m: 0.2,
          max_discrepancy_m: 0.45,
          warning: true,
          checks: [],
        },
        checkingSurvey: false,
      },
      global: { stubs },
    });

    const alert = wrapper.get("[data-test='survey-result-alert']");
    expect(alert.attributes("data-type")).toBe("warning");
    expect(alert.text()).toContain("0.45 m");
  });

  it("displays firmware_version and formatted last_heard_at for a selected node and submits edits", async () => {
    const wrapper = mount(RfNodeFloorPlanCanvas, {
      props: {
        floorPlanReady: true,
        floorPlanUrl: "https://example.test/floor.png",
        floorWidthM: 10,
        floorHeightM: 8,
        nodes: [SAMPLE_NODE],
        rooms: [],
        saving: false,
        surveyResult: null,
        checkingSurvey: false,
      },
      global: { stubs },
    });

    await wrapper.get("[data-test='rf-node-marker-node-lr-1']").trigger("click");

    const fwInput = wrapper.get("[data-test='node-firmware-version']");
    expect((fwInput.element as HTMLInputElement).value).toBe("ESPresense 3.3.2");

    const lastHeard = wrapper.get("[data-test='node-last-heard']");
    expect(lastHeard.text()).toContain("FMT:2026-11-21T14:00:00Z");

    await fwInput.setValue("ESPresense 3.3.3");
    await wrapper.get("[data-test='save-node-btn']").trigger("click");

    const emitted = wrapper.emitted("update-node");
    expect(emitted).toBeTruthy();
    expect(emitted?.[0]?.[0]).toBe(SAMPLE_NODE.id);
    expect((emitted?.[0]?.[1] as { firmware_version?: string | null }).firmware_version).toBe(
      "ESPresense 3.3.3",
    );
  });
});
