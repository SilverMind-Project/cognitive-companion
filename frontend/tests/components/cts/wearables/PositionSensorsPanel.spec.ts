import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import PositionSensorsPanel from "@/components/cts/wearables/PositionSensorsPanel.vue";
import type { PositionSensorOut } from "@/services/modules/wearables";

const SENSOR: PositionSensorOut = {
  id: "55555555-5555-5555-5555-555555555555",
  sensor_id: "radar-bathroom-1",
  label: "Bathroom radar",
  modality: "mmwave_radar",
  room_id: 4,
  room_name: "Bathroom",
  x_norm: 0.8,
  y_norm: 0.5,
  x_m: 8,
  y_m: 2.5,
  yaw_deg: null,
  calibration_residual_m: 0.1,
  is_active: true,
  created_at: "2026-11-25T09:00:00Z",
  updated_at: "2026-11-25T09:00:00Z",
};

const stubs = {
  "v-alert": { template: "<div><slot /></div>" },
  "v-card": { template: "<div><slot /></div>" },
  "v-card-title": { template: "<div><slot /></div>" },
  "v-card-subtitle": { template: "<div><slot /></div>" },
  "v-spacer": { template: "<span />" },
  "v-table": { template: "<table><slot /></table>" },
  "v-row": { template: "<div><slot /></div>" },
  "v-col": { template: "<div><slot /></div>" },
  "v-btn": {
    template: "<button :disabled='disabled' @click='$emit(\"click\")'><slot /></button>",
    props: ["disabled"],
    emits: ["click"],
  },
  "v-switch": {
    template:
      "<input type='checkbox' :checked='modelValue' @change='$emit(\"update:modelValue\", $event.target.checked)' />",
    props: ["modelValue"],
  },
  "v-text-field": {
    template:
      "<input :value='modelValue' @input='$emit(\"update:modelValue\", $event.target.value)' />",
    props: ["modelValue"],
  },
  "v-select": {
    template:
      "<select :value='modelValue' @change='$emit(\"update:modelValue\", Number($event.target.value) || $event.target.value)'><option v-for='i in items' :key='i.id ?? i.value' :value='i.id ?? i.value'>{{ i.name ?? i.title }}</option></select>",
    props: ["modelValue", "items"],
  },
  AppDialog: {
    template:
      "<div v-if='modelValue'><slot /><button data-test='app-dialog-confirm' :disabled='confirmDisabled' @click='$emit(\"confirm\")' /></div>",
    props: ["modelValue", "confirmDisabled"],
  },
};

function mountPanel(overrides: Record<string, unknown> = {}) {
  return mount(PositionSensorsPanel, {
    props: {
      sensors: [SENSOR],
      rooms: [{ id: 4, name: "Bathroom" }] as never,
      floorPlanReady: true,
      floorWidthM: 10,
      floorHeightM: 5,
      saving: false,
      ...overrides,
    },
    global: { stubs },
  });
}

describe("PositionSensorsPanel", () => {
  it("lists sensors with room, floor-frame yaw, and residual", () => {
    const wrapper = mountPanel();
    const row = wrapper.get("[data-test='position-sensor-row']");
    expect(row.text()).toContain("radar-bathroom-1");
    expect(row.text()).toContain("Bathroom");
    expect(row.text()).toContain("Floor frame");
    expect(row.text()).toContain("0.10 m");
  });

  it("converts the entered metres to normalized plan coordinates on create", async () => {
    const wrapper = mountPanel();
    await wrapper.get("[data-test='add-position-sensor']").trigger("click");
    await wrapper.get("[data-test='new-sensor-label']").setValue("Bedroom radar");
    await wrapper.get("[data-test='new-sensor-id']").setValue("radar-bedroom-1");
    await wrapper.get("[data-test='new-sensor-room']").setValue("4");
    await wrapper.get("[data-test='new-sensor-x']").setValue("5");
    await wrapper.get("[data-test='new-sensor-y']").setValue("2.5");
    await wrapper.get("[data-test='new-sensor-yaw']").setValue("90");
    await wrapper.get("[data-test='app-dialog-confirm']").trigger("click");

    const emitted = wrapper.emitted("create-sensor");
    expect(emitted).toBeDefined();
    const [body] = emitted![0];
    expect(body).toMatchObject({
      sensor_id: "radar-bedroom-1",
      label: "Bedroom radar",
      room_id: 4,
      x_norm: 0.5,
      y_norm: 0.5,
      yaw_deg: 90,
      is_active: true,
    });
  });

  it("refuses an invalid sensor id", async () => {
    const wrapper = mountPanel();
    await wrapper.get("[data-test='add-position-sensor']").trigger("click");
    await wrapper.get("[data-test='new-sensor-label']").setValue("Radar");
    await wrapper.get("[data-test='new-sensor-id']").setValue("Sensor:Radar");
    await wrapper.get("[data-test='new-sensor-room']").setValue("4");
    expect(wrapper.get("[data-test='app-dialog-confirm']").attributes("disabled")).toBeDefined();
  });

  it("disables registration without a floor-plan scale", () => {
    const wrapper = mountPanel({ floorPlanReady: false });
    expect(wrapper.find("[data-test='position-sensors-no-floor-plan']").exists()).toBe(true);
    expect(wrapper.get("[data-test='add-position-sensor']").attributes("disabled")).toBeDefined();
  });

  it("emits an active toggle", async () => {
    const wrapper = mountPanel();
    await wrapper.get("[data-test='position-sensor-active-radar-bathroom-1']").setValue(false);
    expect(wrapper.emitted("update-sensor")).toEqual([[SENSOR.id, { is_active: false }]]);
  });

  it("refuses out-of-range yaw and treats whitespace yaw as floor frame null", async () => {
    const wrapper = mountPanel();
    await wrapper.get("[data-test='add-position-sensor']").trigger("click");
    await wrapper.get("[data-test='new-sensor-label']").setValue("Hall radar");
    await wrapper.get("[data-test='new-sensor-id']").setValue("radar-hall-1");
    await wrapper.get("[data-test='new-sensor-room']").setValue("4");
    await wrapper.get("[data-test='new-sensor-yaw']").setValue("180");
    expect(wrapper.get("[data-test='app-dialog-confirm']").attributes("disabled")).toBeDefined();

    await wrapper.get("[data-test='new-sensor-yaw']").setValue("   ");
    expect(wrapper.get("[data-test='app-dialog-confirm']").attributes("disabled")).toBeUndefined();
    await wrapper.get("[data-test='app-dialog-confirm']").trigger("click");
    const emitted = wrapper.emitted("create-sensor");
    expect(emitted).toBeDefined();
    expect(emitted![0][0].yaw_deg).toBeNull();
  });

  it("edits an existing sensor and emits update-sensor", async () => {
    const wrapper = mountPanel();
    await wrapper.get("[data-test='position-sensor-edit-radar-bathroom-1']").trigger("click");
    await wrapper.get("[data-test='new-sensor-label']").setValue("Primary Bathroom Radar");
    await wrapper.get("[data-test='new-sensor-yaw']").setValue("-90");
    await wrapper.get("[data-test='app-dialog-confirm']").trigger("click");

    const emitted = wrapper.emitted("update-sensor");
    expect(emitted).toEqual([
      [
        SENSOR.id,
        {
          label: "Primary Bathroom Radar",
          modality: "mmwave_radar",
          room_id: 4,
          x_norm: 0.8,
          y_norm: 0.5,
          yaw_deg: -90,
          calibration_residual_m: 0.1,
        },
      ],
    ]);
  });
});
