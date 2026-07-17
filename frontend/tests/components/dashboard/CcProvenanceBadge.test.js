/**
 * U3-T7: CcProvenanceBadge
 *
 * Verifies:
 * - Each source enum value renders distinctly (different label/icon)
 * - quality value is shown as a percentage
 * - Missing quality renders "unknown", never a fabricated number (D5/rule 15)
 */
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";

const stubComponents = {
  "v-chip": {
    template: '<span data-testid="v-chip" :data-icon="prependIcon"><slot /></span>',
    props: ["prependIcon", "color", "size", "variant", "title"],
  },
  "v-icon": { template: "<i />" },
};

import CcProvenanceBadge from "../../../src/components/dashboard/CcProvenanceBadge.vue";

const SOURCES = ["observation", "transition", "manual_override", "ph_continuation"];

describe("CcProvenanceBadge — source enum", () => {
  it("renders each source with a distinct label", () => {
    const labels = SOURCES.map((src) => {
      const w = mount(CcProvenanceBadge, {
        props: { source: src, quality: 0.8 },
        global: { stubs: stubComponents },
      });
      return w.vm.sourceConfig.label;
    });
    // All labels must be distinct
    const unique = new Set(labels);
    expect(unique.size).toBe(SOURCES.length);
  });

  it("observation source has label 'Observed'", () => {
    const w = mount(CcProvenanceBadge, {
      props: { source: "observation", quality: 0.9 },
      global: { stubs: stubComponents },
    });
    expect(w.vm.sourceConfig.label).toBe("Observed");
  });

  it("transition source has label 'Transit'", () => {
    const w = mount(CcProvenanceBadge, {
      props: { source: "transition", quality: 0.5 },
      global: { stubs: stubComponents },
    });
    expect(w.vm.sourceConfig.label).toBe("Transit");
  });

  it("manual_override source has label 'Manual'", () => {
    const w = mount(CcProvenanceBadge, {
      props: { source: "manual_override", quality: 1.0 },
      global: { stubs: stubComponents },
    });
    expect(w.vm.sourceConfig.label).toBe("Manual");
  });

  it("ph_continuation source has label 'Continuation'", () => {
    const w = mount(CcProvenanceBadge, {
      props: { source: "ph_continuation", quality: 0.7 },
      global: { stubs: stubComponents },
    });
    expect(w.vm.sourceConfig.label).toBe("Continuation");
  });

  it("unknown source falls back to unknown label", () => {
    const w = mount(CcProvenanceBadge, {
      props: { source: null, quality: null },
      global: { stubs: stubComponents },
    });
    expect(w.vm.sourceConfig.label).toBe("Unknown");
  });
});

describe("CcProvenanceBadge — quality display (D5/rule 15)", () => {
  it("renders quality as a percentage when present", () => {
    const w = mount(CcProvenanceBadge, {
      props: { source: "observation", quality: 0.75 },
      global: { stubs: stubComponents },
    });
    expect(w.vm.qualityDisplay).toBe("75%");
  });

  it("renders quality=1.0 as 100%", () => {
    const w = mount(CcProvenanceBadge, {
      props: { source: "observation", quality: 1.0 },
      global: { stubs: stubComponents },
    });
    expect(w.vm.qualityDisplay).toBe("100%");
  });

  it("renders quality=0 as 0%", () => {
    const w = mount(CcProvenanceBadge, {
      props: { source: "observation", quality: 0 },
      global: { stubs: stubComponents },
    });
    expect(w.vm.qualityDisplay).toBe("0%");
  });

  it("renders 'unknown' when quality is null — never fabricates a number", () => {
    const w = mount(CcProvenanceBadge, {
      props: { source: "observation", quality: null },
      global: { stubs: stubComponents },
    });
    expect(w.vm.qualityDisplay).toBe("unknown");
    // Must not be a number string
    expect(w.vm.qualityDisplay).not.toMatch(/^\d+%$/);
  });

  it("renders 'unknown' when quality is undefined", () => {
    const w = mount(CcProvenanceBadge, {
      props: { source: "observation" },
      global: { stubs: stubComponents },
    });
    expect(w.vm.qualityDisplay).toBe("unknown");
  });

  it("high quality (>= 0.8) maps to success color", () => {
    const w = mount(CcProvenanceBadge, {
      props: { source: "observation", quality: 0.9 },
      global: { stubs: stubComponents },
    });
    expect(w.vm.qualityColor).toBe("success");
  });

  it("medium quality (0.5–0.79) maps to warning color", () => {
    const w = mount(CcProvenanceBadge, {
      props: { source: "observation", quality: 0.6 },
      global: { stubs: stubComponents },
    });
    expect(w.vm.qualityColor).toBe("warning");
  });

  it("low quality (< 0.5) maps to error color", () => {
    const w = mount(CcProvenanceBadge, {
      props: { source: "observation", quality: 0.3 },
      global: { stubs: stubComponents },
    });
    expect(w.vm.qualityColor).toBe("error");
  });

  it("null quality maps to default color (never success/warning/error)", () => {
    const w = mount(CcProvenanceBadge, {
      props: { source: "observation", quality: null },
      global: { stubs: stubComponents },
    });
    expect(w.vm.qualityColor).toBe("default");
    expect(["success", "warning", "error"]).not.toContain(w.vm.qualityColor);
  });
});
