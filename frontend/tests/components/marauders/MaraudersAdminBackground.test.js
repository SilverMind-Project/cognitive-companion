import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { reactive } from "vue";

const maraudersState = reactive({ enabled: true, reducedMotion: false });

vi.mock("@/composables/useMaraudersMode.js", () => ({
  useMaraudersMode: () => ({
    state: maraudersState,
    actions: { enable: vi.fn(), disable: vi.fn(), toggle: vi.fn() },
  }),
}));

const canvasContext = {
  beginPath: vi.fn(),
  clearRect: vi.fn(),
  closePath: vi.fn(),
  fill: vi.fn(),
  lineTo: vi.fn(),
  moveTo: vi.fn(),
  quadraticCurveTo: vi.fn(),
  setTransform: vi.fn(),
  stroke: vi.fn(),
  fillStyle: "",
  globalAlpha: 1,
  lineCap: "",
  lineJoin: "",
  lineWidth: 1,
  strokeStyle: "",
};

import MaraudersAdminBackground from "@/components/marauders/MaraudersAdminBackground.vue";

const mountedWrappers = [];

function mountBackground() {
  const wrapper = mount(MaraudersAdminBackground);
  mountedWrappers.push(wrapper);
  return wrapper;
}

describe("MaraudersAdminBackground", () => {
  beforeEach(() => {
    maraudersState.reducedMotion = true;
    vi.clearAllMocks();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(canvasContext);
    vi.spyOn(Math, "random").mockReturnValue(0.5);
    vi.stubGlobal("requestAnimationFrame", vi.fn(() => 17));
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
  });

  afterEach(() => {
    mountedWrappers.splice(0).forEach((wrapper) => wrapper.unmount());
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("renders an ink particle canvas without the removed routes or ornaments", () => {
    const wrapper = mountBackground();

    expect(wrapper.find("canvas.ink-network").exists()).toBe(true);
    expect(wrapper.find(".ink-route").exists()).toBe(false);
    expect(wrapper.find(".map-ornament").exists()).toBe(false);
  });

  it("draws connected edges as stable curved double strokes", () => {
    mountBackground();

    expect(canvasContext.quadraticCurveTo).toHaveBeenCalled();
    expect(canvasContext.stroke).toHaveBeenCalled();
    expect(canvasContext.stroke.mock.calls.length).toBeGreaterThan(
      canvasContext.quadraticCurveTo.mock.calls.length,
    );
  });

  it("draws irregular ink particle outlines and fills", () => {
    mountBackground();

    expect(canvasContext.lineTo).toHaveBeenCalled();
    expect(canvasContext.closePath).toHaveBeenCalled();
    expect(canvasContext.fill).toHaveBeenCalled();
  });

  it("keeps the decorative shared footprint glyphs", () => {
    const wrapper = mountBackground();

    expect(wrapper.findAll(".map-footprint")).toHaveLength(6);
    expect(wrapper.findAll(".map-footprint use")).toHaveLength(6);
  });

  it("marks the background as decorative for assistive technology", () => {
    const wrapper = mountBackground();

    expect(wrapper.attributes("aria-hidden")).toBe("true");
    expect(wrapper.find(".decorative-footprints").attributes("focusable")).toBe("false");
  });

  it("renders one static frame and suppresses animation under reduced motion", () => {
    const wrapper = mountBackground();

    expect(wrapper.classes()).toContain("is-reduced-motion");
    expect(requestAnimationFrame).not.toHaveBeenCalled();
    expect(canvasContext.clearRect).toHaveBeenCalled();
  });

  it("starts animation when reduced motion is disabled", async () => {
    const wrapper = mountBackground();

    maraudersState.reducedMotion = false;
    await wrapper.vm.$nextTick();

    expect(requestAnimationFrame).toHaveBeenCalledTimes(1);
  });
});
