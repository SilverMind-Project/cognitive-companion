import { describe, it, expect, vi } from "vitest";
import { mount } from "@vue/test-utils";

vi.mock("@/composables/useChartTheme.js", () => ({
  ccToken: vi.fn(() => "#2a1d0e"),
}));

import MaraudersAmbientLayer, {
  MARAUDERS_AMBIENT,
} from "@/components/marauders/MaraudersAmbientLayer.vue";

// A realistic clock value so several gait beats have already occurred.
const DEFAULT_PROPS = { canvasW: 1000, canvasH: 800, nowMs: 100000, reducedMotion: false };

function mountLayer(propsOverride = {}) {
  return mount(MaraudersAmbientLayer, { props: { ...DEFAULT_PROPS, ...propsOverride } });
}

describe("MaraudersAmbientLayer — distinctness contract", () => {
  it("MARAUDERS_AMBIENT constant is exported (one-flag disable-able)", () => {
    expect(typeof MARAUDERS_AMBIENT).toBe("boolean");
  });

  it("stamps a short trail of 4 paw prints (four at a time)", () => {
    if (!MARAUDERS_AMBIENT) return;
    const w = mountLayer();
    expect(w.findAll(".ambient-paw").length).toBe(4);
  });

  it("renders no <text> elements — ambient paws never carry a name label", () => {
    if (!MARAUDERS_AMBIENT) return;
    const w = mountLayer();
    expect(w.find("text").exists()).toBe(false);
  });

  it("paws are faint (very low opacity, never near opaque real footprints)", () => {
    if (!MARAUDERS_AMBIENT) return;
    const w = mountLayer();
    for (const paw of w.findAll(".ambient-paw")) {
      const opacity = parseFloat(paw.attributes("opacity") || "1");
      expect(opacity).toBeLessThanOrEqual(0.22);
    }
  });

  it("prints fade by age — newest is the most opaque", () => {
    if (!MARAUDERS_AMBIENT) return;
    const w = mountLayer();
    const opacities = w.findAll(".ambient-paw").map((p) => parseFloat(p.attributes("opacity")));
    // Rendered newest-first; opacity should be non-increasing down the trail.
    for (let i = 1; i < opacities.length; i++) {
      expect(opacities[i]).toBeLessThanOrEqual(opacities[i - 1]);
    }
  });

  it("uses paw-print glyphs (ellipse + circles), not the footstep sole path", () => {
    if (!MARAUDERS_AMBIENT) return;
    const w = mountLayer();
    expect(w.find("ellipse").exists()).toBe(true);
    expect(w.find("circle").exists()).toBe(true);
    expect(w.findAll(".ambient-paw path").length).toBe(0);
  });
});

describe("MaraudersAmbientLayer — motion", () => {
  it("the creature walks as the nowMs clock advances (newest print moves)", () => {
    if (!MARAUDERS_AMBIENT) return;
    const a = mountLayer({ nowMs: 100000 });
    const b = mountLayer({ nowMs: 106000 }); // several gait beats later

    const ta = a.find(".ambient-paw").attributes("transform");
    const tb = b.find(".ambient-paw").attributes("transform");
    expect(ta).not.toBe(tb);
  });

  it("is static under reduced motion (clock advance does not move paws)", () => {
    if (!MARAUDERS_AMBIENT) return;
    const a = mountLayer({ nowMs: 100000, reducedMotion: true });
    const b = mountLayer({ nowMs: 106000, reducedMotion: true });

    const ta = a.find(".ambient-paw").attributes("transform");
    const tb = b.find(".ambient-paw").attributes("transform");
    expect(ta).toBe(tb);
  });

  it("renders nothing until canvas dimensions are known", () => {
    if (!MARAUDERS_AMBIENT) return;
    const w = mountLayer({ canvasW: 0, canvasH: 0 });
    expect(w.findAll(".ambient-paw").length).toBe(0);
  });
});
