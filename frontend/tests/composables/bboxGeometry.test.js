import { describe, expect, it } from "vitest";
import {
  applyCornerDrag,
  clamp01,
  hitTestRect,
  normalizeRect,
} from "@/composables/bboxGeometry.js";

const RECT = { x1: 100, y1: 100, x2: 200, y2: 160 };

describe("bboxGeometry", () => {
  it("clamp01 bounds to [0,1]", () => {
    expect(clamp01(-0.5)).toBe(0);
    expect(clamp01(0.4)).toBe(0.4);
    expect(clamp01(2)).toBe(1);
  });

  it("normalizeRect orders inverted corners", () => {
    expect(normalizeRect({ x1: 200, y1: 160, x2: 100, y2: 100 })).toEqual(RECT);
  });

  it("hitTestRect detects corners within the handle radius", () => {
    expect(hitTestRect(100, 100, RECT)).toBe("nw");
    expect(hitTestRect(200, 100, RECT)).toBe("ne");
    expect(hitTestRect(200, 160, RECT)).toBe("se");
    expect(hitTestRect(100, 160, RECT)).toBe("sw");
  });

  it("hitTestRect returns 'move' for the interior and null outside", () => {
    expect(hitTestRect(150, 130, RECT)).toBe("move");
    expect(hitTestRect(300, 300, RECT)).toBeNull();
  });

  it("hitTestRect prefers corners over the interior", () => {
    // A point at the corner is inside the box too, but the corner wins.
    expect(hitTestRect(101, 101, RECT)).toBe("nw");
  });

  it("applyCornerDrag moves the whole rect", () => {
    expect(applyCornerDrag(RECT, "move", 10, 5)).toEqual({
      x1: 110,
      y1: 105,
      x2: 210,
      y2: 165,
    });
  });

  it("applyCornerDrag resizes only the dragged corner", () => {
    expect(applyCornerDrag(RECT, "se", 20, 10)).toEqual({
      x1: 100,
      y1: 100,
      x2: 220,
      y2: 170,
    });
    expect(applyCornerDrag(RECT, "nw", -10, -10)).toEqual({
      x1: 90,
      y1: 90,
      x2: 200,
      y2: 160,
    });
  });

  it("applyCornerDrag does not mutate the input rect", () => {
    const input = { ...RECT };
    applyCornerDrag(input, "se", 5, 5);
    expect(input).toEqual(RECT);
  });
});
