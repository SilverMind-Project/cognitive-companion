/**
 * BboxCanvas M3 marauders mode — ink overlay behavior.
 *
 * The canvas draw path cannot be tested in happy-dom (no canvas2d), so this
 * spec focuses on the SVG ink overlay: it mounts BboxCanvas in marauders mode
 * and asserts that committed boxes are rendered via MaraudersInkBox (and that
 * the overlay is absent in normal mode).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";

vi.mock("roughjs", () => {
  const toPaths = vi.fn(() => [{ d: "M0 0 L100 0 L100 50 L0 50 Z" }]);
  const polygon = vi.fn(() => ({}));
  return {
    default: { generator: () => ({ polygon, toPaths }) },
  };
});

vi.mock("@/composables/useChartTheme.js", () => ({
  ccToken: vi.fn((name) => {
    if (name === "--cc-annotation-ink") return "#2a1d0e";
    return "";
  }),
}));

// BboxTagPopover teleports to body — stub it so tests stay self-contained.
vi.mock("@/components/cts/keyframes/BboxTagPopover.vue", () => ({
  default: {
    name: "BboxTagPopover",
    template: "<div />",
    props: ["position", "identities"],
    emits: ["tag", "delete", "close"],
  },
}));

// happy-dom has no canvas2d — install a minimal stub on HTMLCanvasElement.
HTMLCanvasElement.prototype.getContext = () => ({
  clearRect: vi.fn(),
  strokeRect: vi.fn(),
  fillRect: vi.fn(),
  fillText: vi.fn(),
  measureText: vi.fn(() => ({ width: 50 })),
  setLineDash: vi.fn(),
  beginPath: vi.fn(),
  moveTo: vi.fn(),
  lineTo: vi.fn(),
  stroke: vi.fn(),
});

import BboxCanvas from "@/components/cts/keyframes/BboxCanvas.vue";

const BOXES = [
  { id: "a1", x1: 100, y1: 50, x2: 300, y2: 200, identity_id: null, isNew: false },
  { id: "a2", x1: 400, y1: 100, x2: 600, y2: 300, identity_id: null, isNew: false },
];

function mountCanvas(maraudersMode = false, initialBboxes = []) {
  return mount(BboxCanvas, {
    props: {
      imageUrl: "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7",
      keyframeId: "kf-test",
      initialBboxes,
      identities: [],
      maraudersMode,
    },
    attachTo: document.body,
  });
}

describe("BboxCanvas — M3 marauders ink overlay", () => {
  it("renders no SVG ink overlay when marauders mode is off", async () => {
    const w = mountCanvas(false);
    expect(w.find(".bbox-ink-overlay").exists()).toBe(false);
  });

  it("renders SVG ink overlay when marauders mode is on and image has natural size", async () => {
    const w = mountCanvas(true);
    // Simulate image load to set imageNaturalWidth/Height
    const img = w.find("img").element;
    Object.defineProperty(img, "naturalWidth", { configurable: true, value: 1920 });
    Object.defineProperty(img, "naturalHeight", { configurable: true, value: 1080 });
    await w.find("img").trigger("load");
    await w.vm.$nextTick();

    expect(w.find(".bbox-ink-overlay").exists()).toBe(true);
  });

  it("renders MaraudersInkBox for each committed box in marauders mode", async () => {
    const w = mountCanvas(true, BOXES);
    const img = w.find("img").element;
    Object.defineProperty(img, "naturalWidth", { configurable: true, value: 1920 });
    Object.defineProperty(img, "naturalHeight", { configurable: true, value: 1080 });
    await w.find("img").trigger("load");
    await w.vm.$nextTick();

    const inkBoxes = w.findAllComponents({ name: "MaraudersInkBox" });
    expect(inkBoxes.length).toBe(BOXES.length);
  });

  it("precision rule: no MaraudersInkBox elements when marauders mode is off", async () => {
    const w = mountCanvas(false, BOXES);
    const img = w.find("img").element;
    Object.defineProperty(img, "naturalWidth", { configurable: true, value: 1920 });
    Object.defineProperty(img, "naturalHeight", { configurable: true, value: 1080 });
    await w.find("img").trigger("load");
    await w.vm.$nextTick();

    expect(w.findAllComponents({ name: "MaraudersInkBox" })).toHaveLength(0);
  });
});
