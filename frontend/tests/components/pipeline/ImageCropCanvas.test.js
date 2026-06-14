import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";

// Mock 2D canvas context.
const mockCtx = {
  clearRect: vi.fn(),
  drawImage: vi.fn(),
  strokeRect: vi.fn(),
  fillRect: vi.fn(),
  fillText: vi.fn(),
  measureText: vi.fn(() => ({ width: 40 })),
  setLineDash: vi.fn(),
  strokeStyle: "",
  fillStyle: "",
  lineWidth: 0,
  font: "",
};
HTMLCanvasElement.prototype.getContext = vi.fn(() => mockCtx);
HTMLCanvasElement.prototype.getBoundingClientRect = () => ({
  left: 0,
  top: 0,
  width: 280,
  height: 140,
  right: 280,
  bottom: 140,
});

// Theme mode is mocked: the canvas test does not exercise the Vuetify theme
// wiring, only the canvas behaviour. `mmState` is flipped per test.
const mmState = { enabled: false, reducedMotion: false };
vi.mock("@/composables/useMaraudersMode.js", () => ({
  useMaraudersMode: () => ({
    state: mmState,
    actions: { enable: vi.fn(), disable: vi.fn(), toggle: vi.fn() },
  }),
}));

const inkStub = {
  name: "MaraudersInkBox",
  props: ["x", "y", "w", "h", "seedKey"],
  template: '<path class="ink-box" />',
};

import ImageCropCanvas from "@/components/pipeline/steps/_shared/ImageCropCanvas.vue";

async function mountLoaded(regions = []) {
  const wrapper = mount(ImageCropCanvas, {
    props: { imageUrl: "https://example.com/frame.jpg", regions, selectedIndex: -1 },
    global: { stubs: { "v-icon": { template: "<i />" }, MaraudersInkBox: inkStub } },
  });
  const img = wrapper.find("img").element;
  Object.defineProperty(img, "naturalWidth", { value: 1000, configurable: true });
  Object.defineProperty(img, "naturalHeight", { value: 500, configurable: true });
  Object.defineProperty(img, "clientWidth", { value: 280, configurable: true });
  Object.defineProperty(img, "clientHeight", { value: 140, configurable: true });
  await wrapper.find("img").trigger("load");
  return wrapper;
}

describe("ImageCropCanvas", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mmState.enabled = false;
  });
  afterEach(() => {
    mmState.enabled = false;
  });

  it("does NOT create a region on a bare click (down/up, no drag)", async () => {
    const wrapper = await mountLoaded();
    const canvas = wrapper.find("canvas");
    await canvas.trigger("mousedown", { clientX: 100, clientY: 50 });
    await canvas.trigger("mouseup", { clientX: 100, clientY: 50 });
    expect(wrapper.emitted("update:regions")).toBeFalsy();
  });

  it("ignores a sub-threshold drag (smaller than the minimum size)", async () => {
    const wrapper = await mountLoaded();
    const canvas = wrapper.find("canvas");
    await canvas.trigger("mousedown", { clientX: 100, clientY: 50 });
    await canvas.trigger("mousemove", { clientX: 103, clientY: 52 });
    await canvas.trigger("mouseup", { clientX: 103, clientY: 52 });
    expect(wrapper.emitted("update:regions")).toBeFalsy();
  });

  it("creates a non-degenerate region on a real drag", async () => {
    const wrapper = await mountLoaded();
    const canvas = wrapper.find("canvas");
    await canvas.trigger("mousedown", { clientX: 50, clientY: 30 });
    await canvas.trigger("mousemove", { clientX: 50, clientY: 30 });
    await canvas.trigger("mousemove", { clientX: 200, clientY: 120 });
    await canvas.trigger("mouseup", { clientX: 200, clientY: 120 });

    const events = wrapper.emitted("update:regions");
    expect(events).toBeTruthy();
    const regions = events[events.length - 1][0];
    expect(regions).toHaveLength(1);
    const r = regions[0];
    expect(r.width).toBeGreaterThan(0);
    expect(r.height).toBeGreaterThan(0);
    expect(r.x + r.width).toBeLessThanOrEqual(1);
    expect(r.y + r.height).toBeLessThanOrEqual(1);
  });

  it("selects a region when clicking inside it", async () => {
    const regions = [{ id: "r1", name: "R1", x: 0.1, y: 0.1, width: 0.5, height: 0.5 }];
    const wrapper = await mountLoaded(regions);
    const canvas = wrapper.find("canvas");
    await canvas.trigger("mousedown", { clientX: 90, clientY: 50 });
    await canvas.trigger("mouseup", { clientX: 90, clientY: 50 });
    expect(wrapper.emitted("select-region")?.[0]).toEqual([0]);
    expect(wrapper.emitted("update:regions")).toBeFalsy();
  });

  it("renders committed regions as hand-drawn ink boxes in Marauder's mode", async () => {
    mmState.enabled = true;
    const regions = [
      { id: "r1", name: "R1", x: 0.1, y: 0.1, width: 0.3, height: 0.3 },
      { id: "r2", name: "R2", x: 0.5, y: 0.5, width: 0.2, height: 0.2 },
    ];
    const wrapper = await mountLoaded(regions);
    expect(wrapper.find("svg.crop-ink-overlay").exists()).toBe(true);
    expect(wrapper.findAll(".ink-box")).toHaveLength(2);
  });

  it("does not render the ink overlay in the default theme", async () => {
    const wrapper = await mountLoaded([
      { id: "r1", name: "R1", x: 0.1, y: 0.1, width: 0.3, height: 0.3 },
    ]);
    expect(wrapper.find("svg.crop-ink-overlay").exists()).toBe(false);
    expect(wrapper.findAll(".ink-box")).toHaveLength(0);
  });
});
