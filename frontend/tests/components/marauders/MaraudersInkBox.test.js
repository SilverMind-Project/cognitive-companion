import { describe, it, expect, vi } from "vitest";
import { mount } from "@vue/test-utils";

vi.mock("roughjs", () => {
  const toPaths = vi.fn(() => [{ d: "M10 20 L110 20 L110 70 L10 70 Z" }]);
  const polygon = vi.fn(() => ({}));
  return {
    default: {
      generator: () => ({ polygon, toPaths }),
    },
  };
});

vi.mock("@/composables/useChartTheme.js", () => ({
  ccToken: vi.fn((name) => {
    if (name === "--cc-annotation-ink") return "#2a1d0e";
    return "";
  }),
}));

import MaraudersInkBox from "@/components/marauders/MaraudersInkBox.vue";

function mountBox(props = {}) {
  return mount(MaraudersInkBox, {
    props: { x: 10, y: 20, w: 100, h: 50, ...props },
  });
}

describe("MaraudersInkBox", () => {
  it("renders a <path> element", () => {
    const w = mountBox();
    expect(w.find("path").exists()).toBe(true);
  });

  it("uses the ink token as stroke color by default", () => {
    const w = mountBox();
    expect(w.find("path").attributes("stroke")).toBe("#2a1d0e");
  });

  it("uses the color prop when provided", () => {
    const w = mountBox({ color: "#4ade80" });
    expect(w.find("path").attributes("stroke")).toBe("#4ade80");
  });

  it("fill is none (box is outline only)", () => {
    const w = mountBox();
    expect(w.find("path").attributes("fill")).toBe("none");
  });

  it("path d attribute comes from rough.js generator", () => {
    const w = mountBox();
    expect(w.find("path").attributes("d")).toBe("M10 20 L110 20 L110 70 L10 70 Z");
  });
});
