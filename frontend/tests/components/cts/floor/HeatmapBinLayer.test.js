import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import HeatmapBinLayer from "@/components/cts/floor/HeatmapBinLayer.vue";

function makeBin(key, overrides = {}) {
  return { key, canvasX: 10, canvasY: 20, canvasSize: 15, opacity: 0.7, ...overrides };
}

function mountLayer(props) {
  return mount(HeatmapBinLayer, {
    props: { canvasH: 800, loading: false, error: null, ...props },
    attachTo: document.body,
  });
}

describe("HeatmapBinLayer", () => {
  it("renders one rect per bin", () => {
    const bins = [makeBin("1"), makeBin("2"), makeBin("3")];
    const wrapper = mountLayer({ bins });
    expect(wrapper.findAll("rect")).toHaveLength(3);
    wrapper.unmount();
  });

  it("sets x, y, width, height, opacity from bin data", () => {
    const bin = makeBin("b1", { canvasX: 5, canvasY: 10, canvasSize: 20, opacity: 0.45 });
    const wrapper = mountLayer({ bins: [bin] });
    const rect = wrapper.find("rect");
    expect(rect.attributes("x")).toBe("5");
    expect(rect.attributes("y")).toBe("10");
    expect(rect.attributes("width")).toBe("20");
    expect(rect.attributes("height")).toBe("20");
    expect(Number(rect.attributes("opacity"))).toBeCloseTo(0.45, 2);
    wrapper.unmount();
  });

  it("shows default empty-state prompt when bins is empty, not loading, and no error", () => {
    const wrapper = mountLayer({ bins: [], loading: false, error: null });
    expect(wrapper.text()).toContain("Select a person and date range");
    wrapper.unmount();
  });

  it("shows error message instead of default prompt when error is set", () => {
    const wrapper = mountLayer({ bins: [], loading: false, error: "Request timed out" });
    expect(wrapper.text()).toContain("Request timed out");
    expect(wrapper.text()).not.toContain("Select a person");
    wrapper.unmount();
  });

  it("hides empty-state text while loading (loading spinner shown elsewhere)", () => {
    const wrapper = mountLayer({ bins: [], loading: true, error: null });
    expect(wrapper.text()).not.toContain("Select a person");
    wrapper.unmount();
  });

  it("hides empty-state text when bins are present", () => {
    const wrapper = mountLayer({ bins: [makeBin("x")] });
    expect(wrapper.text()).not.toContain("Select a person");
    wrapper.unmount();
  });

  it("computes emptyFontSize from canvasH (non-zero positive value)", () => {
    const wrapper = mountLayer({ bins: [], loading: false, canvasH: 500 });
    const textEl = wrapper.find("text");
    expect(textEl.exists()).toBe(true);
    expect(Number(textEl.attributes("font-size"))).toBeGreaterThan(0);
    wrapper.unmount();
  });
});
