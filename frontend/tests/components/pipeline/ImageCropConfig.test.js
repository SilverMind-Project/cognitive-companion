import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";

vi.mock("@/services/api.js", () => ({ api: { getSampleImage: vi.fn() } }));
vi.mock("@/composables/useNotify.js", () => ({
  useNotify: () => ({ notify: { error: vi.fn(), success: vi.fn(), warning: vi.fn() } }),
}));

import ImageCropConfig from "@/components/pipeline/steps/ImageCropConfig.vue";

const stubs = {
  "v-row": { template: "<div><slot /></div>" },
  "v-col": { template: "<div><slot /></div>" },
  "v-spacer": { template: "<div></div>" },
  "v-select": {
    props: ["modelValue", "items"],
    template: `<select class="v-select" />`,
  },
  "v-combobox": { props: ["modelValue"], template: `<input class="v-combobox" />` },
  "v-text-field": {
    props: ["modelValue", "label"],
    emits: ["update:modelValue"],
    template: `<input class="v-text-field" :data-label="label" :value="modelValue" @input="$emit('update:modelValue', $event.target.value)" />`,
  },
  "v-btn": {
    template: `<button class="v-btn" @click="$emit('click', $event)"><slot /></button>`,
  },
  "v-card": { template: `<div class="v-card"><slot /></div>` },
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
  return mount(ImageCropConfig, {
    props: { modelValue, tab },
    global: { stubs },
  });
}

describe("ImageCropConfig", () => {
  it("renders existing regions from modelValue", () => {
    const wrapper = mountConfig({
      regions: [{ id: "region_1", name: "Region 1", x: 0.1, y: 0.1, width: 0.3, height: 0.3 }],
    });
    const nameField = wrapper.find('.v-text-field[data-label="Name"]');
    expect(nameField.attributes("value")).toBe("Region 1");
    expect(wrapper.text()).toContain("30% wide x 30% tall, at (10%, 10%)");
  });

  it("adding a region emits an appended default rect region", async () => {
    const wrapper = mountConfig({ regions: [] });
    const addButton = wrapper.findAll(".v-btn").find((b) => b.text().includes("Add Region"));
    await addButton.trigger("click");

    const emitted = wrapper.emitted("update:modelValue");
    expect(emitted).toBeTruthy();
    const nextRegions = emitted[emitted.length - 1][0].regions;
    expect(nextRegions).toHaveLength(1);
    expect(nextRegions[0]).toMatchObject({ id: "region_1", name: "Region 1" });
  });

  it("deleting a region removes it without mutating the original array", async () => {
    const regions = [
      { id: "region_1", name: "Region 1", x: 0.1, y: 0.1, width: 0.3, height: 0.3 },
      { id: "region_2", name: "Region 2", x: 0.4, y: 0.4, width: 0.2, height: 0.2 },
    ];
    const wrapper = mountConfig({ regions });
    const deleteButtons = wrapper.findAll(".v-btn").filter((b) => b.html().includes("mdi-delete"));
    await deleteButtons[0].trigger("click");

    const emitted = wrapper.emitted("update:modelValue");
    const nextRegions = emitted[emitted.length - 1][0].regions;
    expect(nextRegions.map((r) => r.id)).toEqual(["region_2"]);
    expect(regions).toHaveLength(2);
  });

  it("editing the ID field updates that region only", async () => {
    const regions = [{ id: "region_1", name: "Region 1", x: 0.1, y: 0.1, width: 0.3, height: 0.3 }];
    const wrapper = mountConfig({ regions });
    const idField = wrapper.find('.v-text-field[data-label="ID"]');
    await idField.setValue("kettle_counter");

    const emitted = wrapper.emitted("update:modelValue");
    const nextRegions = emitted[emitted.length - 1][0].regions;
    expect(nextRegions[0].id).toBe("kettle_counter");
  });
});
