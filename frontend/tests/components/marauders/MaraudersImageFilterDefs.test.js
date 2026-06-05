import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import MaraudersImageFilterDefs from "@/components/marauders/MaraudersImageFilterDefs.vue";

describe("MaraudersImageFilterDefs", () => {
  it("defines gentle and strong painterly filters with the required primitive chain", () => {
    const wrapper = mount(MaraudersImageFilterDefs);

    for (const id of ["#marauders-paint", "#marauders-paint-strong"]) {
      const filter = wrapper.find(id);
      expect(filter.exists()).toBe(true);
      expect(filter.find("feGaussianBlur").exists()).toBe(true);
      expect(filter.find("feColorMatrix").exists()).toBe(true);
      expect(filter.find("feComponentTransfer").exists()).toBe(true);
      expect(filter.find("feTurbulence").exists()).toBe(true);
      expect(filter.find("feDisplacementMap").exists()).toBe(true);
    }
  });

  it("defines one reusable heat blur filter", () => {
    const wrapper = mount(MaraudersImageFilterDefs);

    expect(wrapper.findAll("#marauders-heat-blur")).toHaveLength(1);
    expect(wrapper.find("#marauders-heat-blur feGaussianBlur").exists()).toBe(true);
  });

  it("defines a legend gradient using the heat-ramp tokens", () => {
    const wrapper = mount(MaraudersImageFilterDefs);
    const stops = wrapper.findAll("#marauders-heat-ramp stop");

    expect(stops).toHaveLength(2);
    expect(stops[0].attributes("stop-color")).toBe("var(--cc-heat-ink-low)");
    expect(stops[1].attributes("stop-color")).toBe("var(--cc-heat-ink-high)");
  });

  it("is hidden from assistive technology and layout", () => {
    const wrapper = mount(MaraudersImageFilterDefs);

    expect(wrapper.attributes("aria-hidden")).toBe("true");
    expect(wrapper.attributes("width")).toBe("0");
    expect(wrapper.attributes("height")).toBe("0");
  });
});
