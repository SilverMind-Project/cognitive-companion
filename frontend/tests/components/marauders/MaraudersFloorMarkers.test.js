import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import { reactive } from "vue";

vi.mock("@/composables/useChartTheme.js", () => ({
  ccToken: vi.fn(() => "#2a1d0e"),
}));

// rough.js is mocked at the useRoughSketch boundary so no real generator runs.
vi.mock("@/composables/useRoughSketch.js", () => ({
  useRoughSketch: () => ({
    state: reactive({}),
    actions: {
      path: vi.fn(() => "M0 0 L5 0 L0 5 Z"),
      seedFrom: vi.fn(() => 123),
    },
  }),
}));

// Stub useFootprintTrail so tests control footstep output.
const mockComputeFootsteps = vi.fn(() => []);
vi.mock("@/composables/useFootprintTrail.js", () => ({
  useFootprintTrail: () => ({
    state: reactive({}),
    actions: { computeFootsteps: mockComputeFootsteps },
  }),
  FOOT_FADE_MS: 6000,
}));

import MaraudersFloorMarkers from "@/components/marauders/MaraudersFloorMarkers.vue";

const DEFAULT_PROPS = {
  markers: [],
  phCount: 0,
  canvasH: 800,
  trails: new Map(),
  nowMs: 1000,
  fpWidth: 10,
  fpHeight: 8,
  fpMpp: 0.1,
  canvasW: 1000,
  reducedMotion: false,
};

function mountLayer(propsOverride = {}) {
  return mount(MaraudersFloorMarkers, {
    props: { ...DEFAULT_PROPS, ...propsOverride },
  });
}

describe("MaraudersFloorMarkers — rendering", () => {
  beforeEach(() => {
    mockComputeFootsteps.mockReset();
    mockComputeFootsteps.mockReturnValue([]);
  });

  it("renders without errors with empty markers", () => {
    const w = mountLayer();
    expect(w.vm).toBeDefined();
  });

  it("renders empty-state text when phCount is 0", () => {
    const w = mountLayer({ phCount: 0 });
    expect(w.find(".layer-empty-text").exists()).toBe(true);
    expect(w.find(".layer-empty-text").text()).toContain("No active tracks");
  });

  it("does not render empty-state text when phCount > 0", () => {
    const ph = { ph_id: "ph1", identity_id: "id1" };
    const w = mountLayer({
      phCount: 1,
      markers: [{ ph, x: 100, y: 100, color: "#f00" }],
    });
    expect(w.find(".layer-empty-text").exists()).toBe(false);
  });

  it("renders an ink head marker per entry in markers (no fetching — data from props)", () => {
    const ph1 = { ph_id: "ph1", identity_id: "id1" };
    const ph2 = { ph_id: "ph2", identity_id: "id2" };
    const markers = [
      { ph: ph1, x: 100, y: 100, color: "#f00" },
      { ph: ph2, x: 200, y: 200, color: "#00f" },
    ];
    const w = mountLayer({ phCount: 2, markers });
    expect(w.findAll("[data-testid='mm-head']").length).toBe(2);
  });

  it("head marker is a muted identity dot with a hand-drawn ink ring (not bright concentric rings)", () => {
    const ph = { ph_id: "ph1", identity_id: "id1" };
    const w = mountLayer({ phCount: 1, markers: [{ ph, x: 100, y: 100, color: "#f00" }] });
    const head = w.find("[data-testid='mm-head']");
    // One muted identity dot (fill-opacity < 1) — not a bright solid marker.
    const circles = head.findAll("circle");
    expect(circles.length).toBe(1);
    expect(circles[0].attributes("fill")).toBe("#f00");
    expect(Number(circles[0].attributes("fill-opacity"))).toBeLessThan(1);
    // Plus a hand-drawn (rough) ink ring path stroked with the ink token.
    const ring = head.find("path");
    expect(ring.exists()).toBe(true);
    expect(ring.attributes("stroke")).toBe("#2a1d0e");
    expect(ring.attributes("fill")).toBe("none");
  });

  it("head marker shows the identity label", () => {
    const ph = { ph_id: "ph1", identity_display_name: "Grandma" };
    const w = mountLayer({ phCount: 1, markers: [{ ph, x: 100, y: 100, color: "#f00" }] });
    expect(w.find(".mm-head-label").text()).toBe("Grandma");
  });

  it("renders the shared asset-backed ink glyph per computed footstep", async () => {
    const ph = { ph_id: "ph1" };
    const markers = [{ ph, x: 100, y: 100, color: "#f00" }];
    const footsteps = [
      { phId: "ph1", x: 80, y: 90, angleDeg: 0, foot: "L", opacity: 0.8, seed: 1, color: "#f00" },
      { phId: "ph1", x: 130, y: 90, angleDeg: 0, foot: "R", opacity: 0.6, seed: 2, color: "#f00" },
    ];
    mockComputeFootsteps.mockReturnValue(footsteps);

    const w = mountLayer({ phCount: 1, markers });
    await w.vm.$nextTick();

    const steps = w.findAll(".mm-footstep");
    expect(steps.length).toBe(footsteps.length);
    expect(steps[0].find("use").attributes("href")).toContain("footstep.svg");
    expect(steps[0].attributes("fill")).toBe("#2a1d0e");
    expect(steps[0].attributes("fill")).not.toBe("#f00");
  });

  it("mirrors alternating right-foot glyphs", async () => {
    const ph = { ph_id: "ph1" };
    const markers = [{ ph, x: 100, y: 100, color: "#f00" }];
    mockComputeFootsteps.mockReturnValue([
      { phId: "ph1", x: 80, y: 90, angleDeg: 0, foot: "L", opacity: 0.8, seed: 1 },
      { phId: "ph1", x: 130, y: 90, angleDeg: 0, foot: "R", opacity: 0.6, seed: 2 },
    ]);

    const w = mountLayer({ phCount: 1, markers });
    await w.vm.$nextTick();

    const steps = w.findAll(".mm-footstep");
    expect(steps[0].find("g").attributes("transform")).toBeUndefined();
    expect(steps[1].find("g").attributes("transform")).toBe("scale(-1 1)");
  });

  it("passes opacity as attribute on footstep group", async () => {
    const ph = { ph_id: "ph1" };
    const markers = [{ ph, x: 100, y: 100, color: "#f00" }];
    const footsteps = [
      {
        phId: "ph1",
        x: 80,
        y: 90,
        angleDeg: 45,
        foot: "L",
        opacity: 0.42,
        seed: 99,
        color: "#f00",
      },
    ];
    mockComputeFootsteps.mockReturnValue(footsteps);

    const w = mountLayer({ phCount: 1, markers });
    await w.vm.$nextTick();

    expect(w.find(".mm-footstep").attributes("opacity")).toBe("0.42");
  });
});

describe("MaraudersFloorMarkers — events", () => {
  beforeEach(() => {
    mockComputeFootsteps.mockReturnValue([]);
  });

  it("emits phClick when the head marker is clicked", async () => {
    const ph = { ph_id: "ph1", identity_id: "id1" };
    const w = mountLayer({
      phCount: 1,
      markers: [{ ph, x: 100, y: 100, color: "#f00" }],
    });
    await w.find("[data-testid='mm-head']").trigger("click");
    expect(w.emitted("phClick")).toBeTruthy();
    expect(w.emitted("phClick")[0][0]).toMatchObject({ ph_id: "ph1" });
  });
});

describe("MaraudersFloorMarkers — reduced motion", () => {
  it("passes reducedMotion to computeFootsteps", () => {
    const ph = { ph_id: "ph1" };
    const markers = [{ ph, x: 100, y: 100, color: "#f00" }];
    mountLayer({ phCount: 1, markers, reducedMotion: true });
    expect(mockComputeFootsteps).toHaveBeenCalledWith(
      expect.anything(),
      expect.anything(),
      expect.any(Number),
      expect.objectContaining({ fpMpp: 0.1 }),
      expect.objectContaining({ reducedMotion: true }),
    );
  });
});
