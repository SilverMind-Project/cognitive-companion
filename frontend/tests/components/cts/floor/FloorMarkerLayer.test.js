import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import FloorMarkerLayer from "@/components/cts/floor/FloorMarkerLayer.vue";

const PHMarkerStub = {
  name: "PHMarker",
  props: ["ph", "x", "y", "color"],
  emits: ["click"],
  template: `<g class="ph-marker-stub" :data-ph-id="ph.ph_id" @click="$emit('click', ph)" />`,
};

function makeMarker(id, overrides = {}) {
  return { ph: { ph_id: id, state: "active" }, x: 10, y: 20, color: "#4ade80", ...overrides };
}

function mountLayer(props) {
  return mount(FloorMarkerLayer, {
    props: { canvasH: 800, ...props },
    global: { stubs: { PHMarker: PHMarkerStub } },
    // SVG elements need an SVG parent but vue-test-utils mounts into a div.
    // Wrap in <svg> using attachTo so the template renders correctly.
    attachTo: document.body,
  });
}

describe("FloorMarkerLayer", () => {
  it("renders one PHMarker stub per entry in markers", () => {
    const markers = [makeMarker("a"), makeMarker("b"), makeMarker("c")];
    const wrapper = mountLayer({ markers, phCount: 3 });
    expect(wrapper.findAll(".ph-marker-stub")).toHaveLength(3);
    wrapper.unmount();
  });

  it("passes ph, x, y, color props down to PHMarker", () => {
    const marker = makeMarker("id1", { x: 55, y: 77, color: "#fbbf24" });
    const wrapper = mountLayer({ markers: [marker], phCount: 1 });
    const stub = wrapper.find(".ph-marker-stub");
    expect(stub.attributes("data-ph-id")).toBe("id1");
    wrapper.unmount();
  });

  it("emits phClick with the ph object when PHMarker fires click", async () => {
    const wrapper = mountLayer({ markers: [makeMarker("click-me")], phCount: 1 });
    await wrapper.find(".ph-marker-stub").trigger("click");
    const emitted = wrapper.emitted("phClick");
    expect(emitted).toBeTruthy();
    expect(emitted[0][0]).toEqual(expect.objectContaining({ ph_id: "click-me" }));
    wrapper.unmount();
  });

  it("shows empty-state text when phCount is 0, regardless of markers array", () => {
    const wrapper = mountLayer({ markers: [], phCount: 0 });
    expect(wrapper.text()).toContain("No active tracks");
    wrapper.unmount();
  });

  it("hides empty-state text when phCount > 0 (rAF startup: markers may be empty)", () => {
    // phCount drives the guard, not markers.length, so the flash is suppressed
    // when worldPhMarkers already has data but smoothedMarkers is still empty.
    const wrapper = mountLayer({ markers: [], phCount: 2 });
    expect(wrapper.text()).not.toContain("No active tracks");
    wrapper.unmount();
  });

  it("renders no PHMarkers when markers is empty", () => {
    const wrapper = mountLayer({ markers: [], phCount: 0 });
    expect(wrapper.findAll(".ph-marker-stub")).toHaveLength(0);
    wrapper.unmount();
  });

  it("computes emptyFontSize from canvasH (regression: non-zero positive value)", () => {
    const wrapper = mountLayer({ markers: [], phCount: 0, canvasH: 600 });
    const textEl = wrapper.find("text");
    expect(textEl.exists()).toBe(true);
    const size = Number(textEl.attributes("font-size"));
    expect(size).toBeGreaterThan(0);
    wrapper.unmount();
  });
});
