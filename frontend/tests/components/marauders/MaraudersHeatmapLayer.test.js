import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import MaraudersHeatmapLayer from "@/components/marauders/MaraudersHeatmapLayer.vue";

function makeBin(key, overrides = {}) {
  return {
    key,
    canvasX: 10,
    canvasY: 20,
    canvasSize: 16,
    opacity: 0.2,
    ...overrides,
  };
}

function mountLayer(props = {}) {
  return mount(MaraudersHeatmapLayer, {
    props: {
      bins: [],
      loading: false,
      error: null,
      canvasH: 800,
      ...props,
    },
  });
}

describe("MaraudersHeatmapLayer", () => {
  it("renders one circular stain per bin from props", () => {
    const wrapper = mountLayer({
      bins: [makeBin("low"), makeBin("mid"), makeBin("high")],
    });

    expect(wrapper.findAll(".marauders-heat-stain")).toHaveLength(3);
  });

  it("maps the minimum and maximum normalized weights to the ramp token endpoints", () => {
    const wrapper = mountLayer({
      bins: [
        makeBin("low", { opacity: 0.2 }),
        makeBin("high", { opacity: 1 }),
      ],
    });
    const [low, high] = wrapper.findAll(".marauders-heat-stain");

    expect(low.attributes("fill")).toBe(
      "color-mix(in srgb, var(--cc-heat-ink-low) 100%, var(--cc-heat-ink-high) 0%)",
    );
    expect(high.attributes("fill")).toBe(
      "color-mix(in srgb, var(--cc-heat-ink-low) 0%, var(--cc-heat-ink-high) 100%)",
    );
  });

  it("applies the shared blur filter once to the stain group, not to each bin", () => {
    const wrapper = mountLayer({
      bins: [makeBin("one"), makeBin("two", { opacity: 1 })],
    });

    const filtered = wrapper.findAll("[filter]");
    expect(filtered).toHaveLength(1);
    expect(filtered[0].attributes("filter")).toBe("url(#marauders-heat-blur)");
    for (const stain of wrapper.findAll(".marauders-heat-stain")) {
      expect(stain.attributes("filter")).toBeUndefined();
    }
  });

  it("renders the matching ink-ramp legend when stains are present", () => {
    const wrapper = mountLayer({ bins: [makeBin("one")] });

    expect(wrapper.find("[data-testid='marauders-heat-legend']").exists()).toBe(true);
    expect(wrapper.find(".marauders-heat-legend rect").attributes("fill")).toBe(
      "url(#marauders-heat-ramp)",
    );
    expect(wrapper.text()).toContain("Faint");
    expect(wrapper.text()).toContain("Deep");
  });

  it("shows the themed empty-state prompt when bins are empty", () => {
    const wrapper = mountLayer({ bins: [] });

    expect(wrapper.text()).toContain("Select a person and date range");
    expect(wrapper.find("[data-testid='marauders-heat-legend']").exists()).toBe(false);
  });

  it("shows the error string when bins are empty and an error is set", () => {
    const wrapper = mountLayer({ bins: [], error: "Heatmap unavailable" });

    expect(wrapper.text()).toContain("Heatmap unavailable");
    expect(wrapper.text()).not.toContain("Select a person");
  });

  it("hides the empty state while loading", () => {
    const wrapper = mountLayer({ bins: [], loading: true });

    expect(wrapper.text()).not.toContain("Select a person");
  });

  it("clamps an invalid opacity to the low ramp endpoint", () => {
    const wrapper = mountLayer({
      bins: [makeBin("invalid", { opacity: undefined })],
    });

    expect(wrapper.find(".marauders-heat-stain").attributes("data-ramp-weight")).toBe("0");
  });
});
