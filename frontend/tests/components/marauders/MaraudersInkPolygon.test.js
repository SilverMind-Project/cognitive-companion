import { describe, it, expect, vi } from "vitest";
import { mount } from "@vue/test-utils";

// Stub roughjs before component import so happy-dom won't try to use the browser canvas API.
vi.mock("roughjs", () => {
  const toPaths = vi.fn(() => [{ d: "M0 0 L100 0 L50 100 Z" }]);
  const polygon = vi.fn(() => ({}));
  return {
    default: {
      generator: () => ({ polygon, toPaths }),
    },
  };
});

// Stub CSS token reads (no real DOM computed styles in happy-dom).
vi.mock("@/composables/useChartTheme.js", () => ({
  ccToken: vi.fn((name) => {
    if (name === "--cc-annotation-ink") return "#2a1d0e";
    if (name === "--cc-room-fill") return "rgba(91,58,26,0.10)";
    return "";
  }),
}));

import MaraudersInkPolygon from "@/components/marauders/MaraudersInkPolygon.vue";

const TRI = [
  [0, 0],
  [1, 0],
  [0.5, 1],
];

function mountPolygon(props = {}) {
  return mount(MaraudersInkPolygon, {
    props: { points: TRI, canvasW: 100, canvasH: 100, ...props },
  });
}

describe("MaraudersInkPolygon", () => {
  it("renders a <path> element", () => {
    const w = mountPolygon();
    expect(w.find("path").exists()).toBe(true);
  });

  it("uses the ink token as stroke color", () => {
    const w = mountPolygon();
    expect(w.find("path").attributes("stroke")).toBe("#2a1d0e");
  });

  it("uses cc-room-fill token as default fill", () => {
    const w = mountPolygon();
    expect(w.find("path").attributes("fill")).toBe("rgba(91,58,26,0.10)");
  });

  it("uses the fill prop when provided", () => {
    const w = mountPolygon({ fill: "#ff0000" });
    expect(w.find("path").attributes("fill")).toBe("#ff0000");
  });

  it("renders no <text> when label is omitted", () => {
    const w = mountPolygon();
    expect(w.find("text").exists()).toBe(false);
  });

  it("renders a <text> when label is provided", () => {
    const w = mountPolygon({ label: "Kitchen" });
    expect(w.find("text").exists()).toBe(true);
    expect(w.find("text").text()).toBe("Kitchen");
  });

  it("path d attribute comes from rough.js generator", () => {
    const w = mountPolygon();
    expect(w.find("path").attributes("d")).toBe("M0 0 L100 0 L50 100 Z");
  });
});
