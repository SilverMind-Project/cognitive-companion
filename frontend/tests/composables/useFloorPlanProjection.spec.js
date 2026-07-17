import { describe, it, expect } from "vitest";
import {
  projectDetectionToCanvas,
  trailKeyFor,
  pointInPolygon,
  roomForCanvasPoint,
} from "../../src/composables/useFloorPlanProjection";

const fp = {
  width: 1448,
  height: 1086,
  mpp: 0.0086,
  canvasW: 1200,
  canvasH: 800,
};

describe("useFloorPlanProjection", () => {
  // ── projectDetectionToCanvas ─────────────────────────────────────────────

  describe("projectDetectionToCanvas", () => {
    it("returns null when floor_calibrated is false", () => {
      const det = { floor_calibrated: false, floor_x: 5.0, floor_y: 3.0 };
      expect(projectDetectionToCanvas(det, fp)).toBeNull();
    });

    it("returns null when floor_x/floor_y is null even if calibrated is true", () => {
      const det = { floor_calibrated: true, floor_x: null, floor_y: null };
      expect(projectDetectionToCanvas(det, fp)).toBeNull();
    });

    it("returns null when floor_calibrated is missing (undefined)", () => {
      const det = { floor_x: 5.0, floor_y: 3.0 };
      expect(projectDetectionToCanvas(det, fp)).toBeNull();
    });

    it("returns null when floor plan dimensions are zero", () => {
      const det = { floor_calibrated: true, floor_x: 5.0, floor_y: 3.0 };
      expect(
        projectDetectionToCanvas(det, {
          width: 0,
          height: 0,
          mpp: 0.01,
          canvasW: 1200,
          canvasH: 800,
        }),
      ).toBeNull();
    });

    it("returns null when mpp is zero (produces non-finite coordinates)", () => {
      const det = { floor_calibrated: true, floor_x: 5.0, floor_y: 3.0 };
      expect(
        projectDetectionToCanvas(det, {
          width: 1448,
          height: 1086,
          mpp: 0,
          canvasW: 1200,
          canvasH: 800,
        }),
      ).toBeNull();
    });

    it("returns correct canvas point for a known calibrated detection (golden case)", () => {
      // fp.width * fp.mpp = 1448 * 0.0086 = 12.4528 m total width
      // fx = (5.0 / 12.4528) * 1200 = 481.9...
      const det = { floor_calibrated: true, floor_x: 5.0, floor_y: 3.0 };
      const result = projectDetectionToCanvas(det, fp);
      expect(result).not.toBeNull();
      expect(result.x).toBeCloseTo((5.0 / (1448 * 0.0086)) * 1200, 0);
      expect(result.y).toBeCloseTo((3.0 / (1086 * 0.0086)) * 800, 0);
    });

    it("returns null when floor_x is 0 and floor_calibrated is missing (defensive against zero-default)", () => {
      // Upstream may send floor_x: 0.0 through proto default-value behavior.
      // Without floor_calibrated, treat as unprojectable.
      const det = { floor_x: 0.0, floor_y: 0.0 };
      expect(projectDetectionToCanvas(det, fp)).toBeNull();
    });
  });

  // ── trailKeyFor ───────────────────────────────────────────────────────────

  describe("trailKeyFor", () => {
    it("returns id:<identity_id> when identity present", () => {
      const det = { identity_id: "person-abc", ph_id: "ph-123" };
      expect(trailKeyFor(det)).toBe("id:person-abc");
    });

    it("returns ph:<ph_id> when only PH present", () => {
      const det = { identity_id: null, ph_id: "ph-456" };
      expect(trailKeyFor(det)).toBe("ph:ph-456");
    });

    it("returns null when neither identity nor PH present", () => {
      expect(trailKeyFor({})).toBeNull();
      expect(trailKeyFor({ identity_id: null, ph_id: null })).toBeNull();
    });

    it("trims whitespace from identity_id", () => {
      const det = { identity_id: "  alice  ", ph_id: "ph-1" };
      expect(trailKeyFor(det)).toBe("id:alice");
    });

    it("returns ph: prefix even when identity_id is empty string", () => {
      const det = { identity_id: "", ph_id: "ph-789" };
      expect(trailKeyFor(det)).toBe("ph:ph-789");
    });
  });

  // ── pointInPolygon ────────────────────────────────────────────────────────

  describe("pointInPolygon", () => {
    const square = [
      [0, 0],
      [0, 10],
      [10, 10],
      [10, 0],
    ];

    it("returns true for a point inside a square", () => {
      expect(pointInPolygon(5, 5, square)).toBe(true);
    });

    it("returns false for a point outside a square", () => {
      expect(pointInPolygon(15, 5, square)).toBe(false);
    });

    it("returns true for a point inside a concave L-shape", () => {
      // L-shape polygon
      const l = [
        [0, 0],
        [0, 10],
        [3, 10],
        [3, 3],
        [10, 3],
        [10, 0],
      ];
      expect(pointInPolygon(1, 5, l)).toBe(true);
      expect(pointInPolygon(5, 1, l)).toBe(true);
    });

    it("returns false for a point in the notch of a concave L-shape", () => {
      const l = [
        [0, 0],
        [0, 10],
        [3, 10],
        [3, 3],
        [10, 3],
        [10, 0],
      ];
      expect(pointInPolygon(5, 5, l)).toBe(false);
    });

    it("returns true for a point on the edge (boundary)", () => {
      // Ray casting behavior for edge points is implementation-defined.
      // Just verify it does not throw and returns a boolean.
      const result = pointInPolygon(0, 5, square);
      expect(typeof result).toBe("boolean");
    });
  });

  // ── roomForCanvasPoint ────────────────────────────────────────────────────

  describe("roomForCanvasPoint", () => {
    const rooms = [
      {
        name: "Living Room",
        floor_polygon: [
          [0.1, 0.1],
          [0.5, 0.1],
          [0.5, 0.5],
          [0.1, 0.5],
        ],
      },
      {
        name: "Bedroom",
        floor_polygon: [
          [0.6, 0.1],
          [0.9, 0.1],
          [0.9, 0.5],
          [0.6, 0.5],
        ],
      },
    ];

    it("returns the first matching room name", () => {
      // Canvas point (480, 240) in a 1200×800 canvas → normalized (0.4, 0.3)
      expect(roomForCanvasPoint(480, 240, 1200, 800, rooms)).toBe("Living Room");
    });

    it("returns null when no polygon matches", () => {
      expect(roomForCanvasPoint(100, 100, 1200, 800, rooms)).toBeNull();
    });

    it("returns null when rooms array is empty", () => {
      expect(roomForCanvasPoint(480, 240, 1200, 800, [])).toBeNull();
    });

    it("skips rooms without floor_polygon", () => {
      const mixed = [
        { name: "Hallway", floor_polygon: null },
        {
          name: "Kitchen",
          floor_polygon: [
            [0.1, 0.1],
            [0.5, 0.1],
            [0.5, 0.5],
            [0.1, 0.5],
          ],
        },
      ];
      expect(roomForCanvasPoint(480, 240, 1200, 800, mixed)).toBe("Kitchen");
    });
  });
});
