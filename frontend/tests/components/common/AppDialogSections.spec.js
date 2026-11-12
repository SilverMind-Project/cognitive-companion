import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import AppDialogSections from "@/components/common/AppDialogSections.vue";

const SECTIONS = [
  { key: "general", label: "General", icon: "mdi-cog", description: "Name and stream." },
  { key: "geometry", label: "Geometry", icon: "mdi-angle-acute", error: true },
];

const stubs = {
  "v-tabs": {
    name: "v-tabs",
    props: ["modelValue", "direction"],
    emits: ["update:modelValue"],
    template: "<div class='tabs'><slot /></div>",
  },
  "v-tab": {
    name: "v-tab",
    props: ["value", "prependIcon"],
    template: "<button class='tab'><slot /></button>",
  },
  "v-window": { name: "v-window", props: ["modelValue"], template: "<div><slot /></div>" },
  "v-window-item": { props: ["value"], template: "<div class='pane'><slot /></div>" },
  "v-divider": { props: ["vertical"], template: "<hr />" },
  "v-icon": { template: "<span class='attention'><slot /></span>" },
};

function mountSections(props = {}) {
  return mount(AppDialogSections, {
    props: { sections: SECTIONS, modelValue: "general", ...props },
    slots: {
      "section-general": "<div>General fields</div>",
      "section-geometry": "<div>Geometry fields</div>",
    },
    global: { stubs },
  });
}

describe("AppDialogSections", () => {
  it("renders one nav tab and one pane per section with its description", () => {
    const wrapper = mountSections();
    expect(wrapper.findAll(".tab").map((t) => t.text())).toEqual([
      "General",
      expect.stringContaining("Geometry"),
    ]);
    expect(wrapper.findAll(".pane")).toHaveLength(2);
    expect(wrapper.text()).toContain("Name and stream.");
    expect(wrapper.text()).toContain("Geometry fields");
  });

  it("flags a section that needs attention", () => {
    const wrapper = mountSections();
    const tabs = wrapper.findAll(".tab");
    expect(tabs[0].find(".attention").exists()).toBe(false);
    expect(tabs[1].find(".attention").exists()).toBe(true);
  });

  it("puts the nav beside the content, or above it when compact", () => {
    expect(mountSections().findComponent({ name: "v-tabs" }).props("direction")).toBe("vertical");
    expect(
      mountSections({ compact: true }).findComponent({ name: "v-tabs" }).props("direction"),
    ).toBe("horizontal");
  });

  it("emits the chosen section", async () => {
    const wrapper = mountSections();
    await wrapper.findComponent({ name: "v-tabs" }).vm.$emit("update:modelValue", "geometry");
    expect(wrapper.emitted("update:modelValue")[0]).toEqual(["geometry"]);
  });
});
