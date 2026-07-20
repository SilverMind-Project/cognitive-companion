import { describe, it, expect } from "vitest";
import {
  falloffStops,
  toSvgPoints,
  FALLOFF_STOP_INNER,
  FALLOFF_OPACITY_INNER,
  FALLOFF_STOP_OUTER,
  FALLOFF_OPACITY_OUTER,
} from "@/components/cts/floor/coverageFalloff.js";

describe("coverageFalloff", () => {
  describe("toSvgPoints", () => {
    it("converts normalised points to viewBox points", () => {
      const poly = [
        [0.1, 0.2],
        [0.5, 0.8],
      ];
      expect(toSvgPoints(poly, 1000, 500)).toBe("100.0,100.0 500.0,400.0");
    });

    it("returns empty string if missing dimensions or polygon", () => {
      expect(toSvgPoints(null, 1000, 500)).toBe("");
      expect(toSvgPoints([], 0, 500)).toBe("");
    });
  });

  describe("falloffStops", () => {
    it("computes gradient centre and radius from anchor and polygon", () => {
      const anchor = { x_norm: 0.5, y_norm: 0.5 };
      // max distance vertex is [1.0, 0.5] -> 0.5 away
      // In pixel space: anchor is (500, 250)
      // vertex [1.0, 0.5] is (1000, 250) -> distance 500
      const poly = [
        [0.5, 0.5],
        [1.0, 0.5],
      ];
      const result = falloffStops(anchor, poly, 1000, 500);

      expect(result.cx).toBe(500);
      expect(result.cy).toBe(250);
      expect(result.r).toBe(500);
      expect(result.stops).toEqual([
        { offset: FALLOFF_STOP_INNER, opacity: FALLOFF_OPACITY_INNER },
        { offset: FALLOFF_STOP_OUTER, opacity: FALLOFF_OPACITY_OUTER },
      ]);
    });

    it("handles degenerate polygon (all vertices at anchor) with non-zero radius", () => {
      const anchor = { x_norm: 0.5, y_norm: 0.5 };
      const poly = [
        [0.5, 0.5],
        [0.5, 0.5],
      ];
      const result = falloffStops(anchor, poly, 1000, 500);

      expect(result.r).toBeGreaterThan(0);
      expect(result.r).toBe(0.1);
    });
  });
});
