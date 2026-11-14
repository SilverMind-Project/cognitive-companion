import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import OverlapGroupSuggestions from "@/components/cts/OverlapGroupSuggestions.vue";

const stubs = {
  "v-card": { template: "<section><slot /></section>" },
  "v-card-title": { template: "<div><slot /></div>" },
  "v-card-subtitle": { template: "<div><slot /></div>" },
  "v-list": { template: "<ul><slot /></ul>" },
  "v-list-item": { template: "<li><slot /><slot name='append' /></li>" },
  "v-list-item-title": { template: "<span><slot /></span>" },
  "v-list-item-subtitle": { template: "<span><slot /></span>" },
  "v-btn": { emits: ["click"], template: "<button @click=\"$emit('click')\"><slot /></button>" },
};

const names = { "cam-a": "Living room", "cam-b": "Corridor" };

function mountWith(groups) {
  return mount(OverlapGroupSuggestions, {
    props: { suggestions: { groups, uncalibrated_camera_ids: [] }, cameraNames: names },
    global: { stubs },
  });
}

describe("OverlapGroupSuggestions", () => {
  it("lists undeclared suggestions by camera name and coverage", () => {
    const wrapper = mountWith([{ camera_ids: ["cam-a", "cam-b"], iou: 0.31, declared: false }]);

    const row = wrapper.find("[data-testid='overlap-suggestion-cam-a-cam-b']");
    expect(row.text()).toContain("Living room, Corridor");
    expect(row.text()).toContain("31% shared coverage");
  });

  it("emits the camera ids when a suggestion is used", async () => {
    const wrapper = mountWith([{ camera_ids: ["cam-a", "cam-b"], iou: 0.31, declared: false }]);

    await wrapper.find("button").trigger("click");

    expect(wrapper.emitted("use")).toEqual([[["cam-a", "cam-b"]]]);
  });

  it("renders nothing when every suggestion is already declared", () => {
    const wrapper = mountWith([{ camera_ids: ["cam-a", "cam-b"], iou: 0.31, declared: true }]);
    expect(wrapper.find("[data-testid='overlap-suggestions']").exists()).toBe(false);
  });
});
