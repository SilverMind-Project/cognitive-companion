import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { useCanvasZoom } from "@/composables/useCanvasZoom.js";

describe("useCanvasZoom", () => {
  let zoom;

  beforeEach(() => {
    zoom = useCanvasZoom();
  });

  afterEach(() => {
    zoom.actions.reset();
  });

  it("has default zoom of 1 and zero pan", () => {
    expect(zoom.state.zoom).toBe(1);
    expect(zoom.state.panX).toBe(0);
    expect(zoom.state.panY).toBe(0);
  });

  it("containerToLocal returns identity at default zoom/pan", () => {
    const { x, y } = zoom.containerToLocal(100, 200);
    expect(x).toBe(100);
    expect(y).toBe(200);
  });

  it("containerToLocal accounts for pan", () => {
    zoom.state.panX = 50;
    zoom.state.panY = -30;
    const { x, y } = zoom.containerToLocal(100, 200);
    expect(x).toBeCloseTo(50);
    expect(y).toBeCloseTo(230);
  });

  it("containerToLocal accounts for zoom", () => {
    zoom.state.zoom = 2;
    const { x, y } = zoom.containerToLocal(100, 200);
    expect(x).toBeCloseTo(50);
    expect(y).toBeCloseTo(100);
  });

  it("containerToLocal accounts for both pan and zoom", () => {
    zoom.state.panX = 20;
    zoom.state.panY = 10;
    zoom.state.zoom = 2;
    const { x, y } = zoom.containerToLocal(100, 200);
    expect(x).toBeCloseTo(40);
    expect(y).toBeCloseTo(95);
  });

  describe("onWheel", () => {
    function fakeEvent(deltaY, clientX, clientY) {
      return {
        preventDefault: vi.fn(),
        deltaY,
        clientX,
        clientY,
        currentTarget: {
          getBoundingClientRect: () => ({ left: 0, top: 0, width: 800, height: 600 }),
        },
      };
    }

    it("zooms in on scroll up", () => {
      zoom.actions.onWheel(fakeEvent(-100, 400, 300));
      expect(zoom.state.zoom).toBeGreaterThan(1);
    });

    it("zooms out on scroll down", () => {
      zoom.actions.onWheel(fakeEvent(100, 400, 300));
      expect(zoom.state.zoom).toBeLessThan(1);
    });

    it("respects minZoom", () => {
      zoom.state.zoom = 0.21;
      zoom.actions.onWheel(fakeEvent(100, 400, 300));
      expect(zoom.state.zoom).toBeGreaterThanOrEqual(0.2);
    });

    it("respects maxZoom", () => {
      zoom.state.zoom = 5.99;
      zoom.actions.onWheel(fakeEvent(-100, 100, 100));
      expect(zoom.state.zoom).toBeLessThanOrEqual(6);
    });
  });

  describe("startPan", () => {
    function fireMouseMove(clientX, clientY) {
      window.dispatchEvent(new MouseEvent("mousemove", { clientX, clientY }));
    }
    function fireMouseUp() {
      window.dispatchEvent(new MouseEvent("mouseup"));
    }

    it("sets didPan false and does not move on click (no movement)", () => {
      zoom.actions.startPan({ button: 0, clientX: 100, clientY: 100, preventDefault: vi.fn() });
      fireMouseUp();
      expect(zoom.state.didPan).toBe(false);
      expect(zoom.state.panX).toBe(0);
    });

    it("sets didPan true and pans after threshold", () => {
      zoom.actions.startPan({ button: 0, clientX: 100, clientY: 100, preventDefault: vi.fn() });
      // Move just under threshold
      fireMouseMove(102, 101);
      expect(zoom.state.didPan).toBe(false);
      // Move past threshold
      fireMouseMove(104, 100);
      expect(zoom.state.didPan).toBe(true);
      expect(zoom.state.panX).toBe(4);
      fireMouseUp();
    });

    it("does not start on right-click", () => {
      zoom.actions.startPan({ button: 2, clientX: 100, clientY: 100, preventDefault: vi.fn() });
      fireMouseMove(120, 100);
      expect(zoom.state.didPan).toBe(false);
      fireMouseUp();
    });
  });

  it("reset returns to defaults", () => {
    zoom.state.zoom = 3;
    zoom.state.panX = 100;
    zoom.state.panY = -50;
    zoom.actions.reset();
    expect(zoom.state.zoom).toBe(1);
    expect(zoom.state.panX).toBe(0);
    expect(zoom.state.panY).toBe(0);
  });

  it("transformStyle produces valid CSS", () => {
    const style = zoom.state.transformStyle;
    expect(style).toContain("transform:");
    expect(style).toContain("scale(1)");
    expect(style).toContain("transform-origin: 0 0");
  });

  it("custom options are respected", () => {
    const z = useCanvasZoom({ minZoom: 0.5, maxZoom: 3, wheelStep: 0.15 });
    expect(z.state.zoom).toBe(1);
  });

  describe("zoomIn / zoomOut", () => {
    function fakeContainer() {
      return { getBoundingClientRect: () => ({ left: 0, top: 0, width: 800, height: 600 }) };
    }

    it("zoomIn increases zoom", () => {
      zoom.actions.zoomIn(fakeContainer());
      expect(zoom.state.zoom).toBeGreaterThan(1);
    });

    it("zoomOut decreases zoom", () => {
      zoom.actions.zoomOut(fakeContainer());
      expect(zoom.state.zoom).toBeLessThan(1);
    });

    it("zoomIn/zoomOut work without container", () => {
      zoom.actions.zoomIn(null);
      expect(zoom.state.zoom).toBeGreaterThan(1);
      zoom.actions.zoomOut(null);
      expect(zoom.state.zoom).toBeCloseTo(1, 1);
    });
  });
});
