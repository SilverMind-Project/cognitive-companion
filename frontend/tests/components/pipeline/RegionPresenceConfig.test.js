import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";

vi.mock("@/services/api.js", () => ({ api: { getSampleImage: vi.fn() } }));
vi.mock("@/composables/useNotify.js", () => ({
  useNotify: () => ({ notify: { error: vi.fn(), success: vi.fn(), warning: vi.fn() } }),
}));

import RegionPresenceConfig, {
  stepDefaults,
} from "@/components/pipeline/steps/RegionPresenceConfig.vue";

const stubs = {
  "v-row": { template: "<div><slot /></div>" },
  "v-col": { template: "<div><slot /></div>" },
  "v-spacer": { template: "<div></div>" },
  "v-select": {
    props: ["modelValue", "items"],
    emits: ["update:modelValue"],
    template: `<select class="v-select" />`,
  },
  "v-combobox": {
    props: ["modelValue"],
    emits: ["update:modelValue"],
    template: `<input class="v-combobox" />`,
  },
  "v-text-field": {
    props: ["modelValue", "label"],
    emits: ["update:modelValue"],
    template: `<input class="v-text-field" :data-label="label" :value="modelValue" @input="$emit('update:modelValue', $event.target.value)" />`,
  },
  "v-textarea": {
    props: ["modelValue", "errorMessages"],
    emits: ["update:modelValue", "blur"],
    template: `<div><textarea class="v-textarea" :value="modelValue" @input="$emit('update:modelValue', $event.target.value)" @blur="$emit('blur')" /><div class="error-messages">{{ errorMessages }}</div></div>`,
  },
  "v-btn": {
    template: `<button class="v-btn" @click="$emit('click', $event)"><slot /></button>`,
  },
  "v-card": { template: `<div class="v-card"><slot /></div>` },
  "v-chip": { template: `<span class="v-chip"><slot /></span>` },
  "v-divider": { template: `<hr />` },
  "v-icon": { template: `<i class="v-icon" />` },
  "v-slider": { props: ["modelValue"], template: `<input type="range" class="v-slider" />` },
  ImageCropCanvas: {
    name: "ImageCropCanvas",
    props: ["imageUrl", "regions", "selectedIndex"],
    emits: ["update:regions", "select-region"],
    template: `<div class="image-crop-canvas" />`,
  },
};

function mountConfig(modelValue, tab = "regions") {
  return mount(RegionPresenceConfig, {
    props: { modelValue: { ...stepDefaults, ...modelValue }, tab },
    global: { stubs },
  });
}

describe("RegionPresenceConfig", () => {
  it("renders an existing rect region and excludes polygon regions from the canvas", () => {
    const wrapper = mountConfig({
      regions: [
        { id: "kettle_counter", name: "Kettle counter", x: 0.1, y: 0.1, width: 0.3, height: 0.3 },
        {
          id: "stove",
          name: "Stove",
          points: [
            [0.5, 0],
            [1, 0],
            [1, 1],
          ],
        },
      ],
    });

    const nameField = wrapper.find('.v-text-field[data-label="Name"]');
    expect(nameField.attributes("value")).toBe("Kettle counter");
    const canvas = wrapper.findComponent({ name: "ImageCropCanvas" });
    expect(canvas.props("regions")).toHaveLength(1);
    expect(canvas.props("regions")[0].id).toBe("kettle_counter");
  });

  it("adding a rect region appends a default region and preserves polygon regions", async () => {
    const polygon = {
      id: "stove",
      name: "Stove",
      points: [
        [0.5, 0],
        [1, 0],
        [1, 1],
      ],
    };
    const wrapper = mountConfig({ regions: [polygon] });

    const addButton = wrapper.findAll(".v-btn").find((b) => b.text().includes("Add Rect Region"));
    await addButton.trigger("click");

    const emitted = wrapper.emitted("update:modelValue");
    const nextRegions = emitted[emitted.length - 1][0].regions;
    expect(nextRegions).toHaveLength(2);
    expect(nextRegions.find((r) => r.id === "stove")).toEqual(polygon);
    expect(nextRegions.find((r) => r.id === "region_1")).toMatchObject({ name: "Region 1" });
  });

  it("commits valid polygon JSON and merges it with rect regions", async () => {
    const rect = {
      id: "kettle_counter",
      name: "Kettle counter",
      x: 0,
      y: 0,
      width: 0.3,
      height: 0.3,
    };
    const wrapper = mountConfig({ regions: [rect] });

    const textarea = wrapper.find(".v-textarea");
    const newPolygon = [
      {
        id: "stove",
        name: "Stove",
        points: [
          [0.5, 0],
          [1, 0],
          [1, 1],
        ],
      },
    ];
    await textarea.setValue(JSON.stringify(newPolygon));
    await textarea.trigger("blur");

    const emitted = wrapper.emitted("update:modelValue");
    const nextRegions = emitted[emitted.length - 1][0].regions;
    expect(nextRegions).toEqual([rect, ...newPolygon]);
  });

  it("rejects invalid polygon JSON without emitting", async () => {
    const wrapper = mountConfig({ regions: [] });
    const textarea = wrapper.find(".v-textarea");

    await textarea.setValue("not json");
    await textarea.trigger("blur");

    expect(wrapper.emitted("update:modelValue")).toBeFalsy();
    expect(wrapper.find(".error-messages").text()).toBe("Invalid JSON");
  });

  it("rejects a polygon with fewer than 3 points", async () => {
    const wrapper = mountConfig({ regions: [] });
    const textarea = wrapper.find(".v-textarea");

    await textarea.setValue(
      JSON.stringify([
        {
          id: "bad",
          name: "Bad",
          points: [
            [0, 0],
            [1, 1],
          ],
        },
      ]),
    );
    await textarea.trigger("blur");

    expect(wrapper.emitted("update:modelValue")).toBeFalsy();
    expect(wrapper.find(".error-messages").text()).toContain("needs at least 3 points");
  });

  it("options tab emits detections_key updates", async () => {
    const wrapper = mountConfig({}, "options");
    const detectionsKeyField = wrapper.find('.v-text-field[data-label="Detections Key"]');
    await detectionsKeyField.setValue("steps.scene_analysis_1.outputs.scene_detections");

    const emitted = wrapper.emitted("update:modelValue");
    expect(emitted[emitted.length - 1][0].detections_key).toBe(
      "steps.scene_analysis_1.outputs.scene_detections",
    );
  });
});
