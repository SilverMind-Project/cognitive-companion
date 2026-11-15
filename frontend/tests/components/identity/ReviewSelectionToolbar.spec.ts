import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";

import ReviewSelectionToolbar from "@/components/identity/ReviewSelectionToolbar.vue";

const stubs = {
  "v-btn": { template: "<button @click=\"$emit('click')\"><slot /></button>", emits: ["click"] },
  "v-chip": { template: "<span><slot /></span>" },
};

function mountBar(props: { active: boolean; selectableCount: number; selectedCount: number }) {
  return mount(ReviewSelectionToolbar, {
    props,
    slots: { default: "<button class='decision'>Decide</button>" },
    global: { stubs },
  });
}

describe("ReviewSelectionToolbar", () => {
  it("shows only the mode switch until selection starts", async () => {
    const wrapper = mountBar({ active: false, selectableCount: 4, selectedCount: 0 });

    expect(wrapper.get("[data-test='select-mode']").text()).toBe("Select several");
    expect(wrapper.find("[data-test='select-all']").exists()).toBe(false);
    expect(wrapper.find(".decision").exists()).toBe(false);

    await wrapper.get("[data-test='select-mode']").trigger("click");
    expect(wrapper.emitted("update:active")?.[0]).toEqual([true]);
  });

  it("offers select all, the count, clear, and the surface's decisions while selecting", async () => {
    const wrapper = mountBar({ active: true, selectableCount: 4, selectedCount: 2 });

    expect(wrapper.get("[data-test='select-all']").text()).toBe("Select all 4");
    expect(wrapper.get("[data-test='selection-count']").text()).toBe("2 selected");
    expect(wrapper.find(".decision").exists()).toBe(true);

    await wrapper.get("[data-test='select-all']").trigger("click");
    await wrapper.get("[data-test='clear-selection']").trigger("click");
    expect(wrapper.emitted("select-all")).toHaveLength(1);
    expect(wrapper.emitted("clear")).toHaveLength(1);
  });

  it("hides select all and clear when they would do nothing", () => {
    const wrapper = mountBar({ active: true, selectableCount: 0, selectedCount: 0 });

    expect(wrapper.find("[data-test='select-all']").exists()).toBe(false);
    expect(wrapper.find("[data-test='clear-selection']").exists()).toBe(false);
  });
});
