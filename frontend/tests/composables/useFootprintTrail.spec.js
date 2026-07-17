import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("roughjs", () => {
  const toPaths = vi.fn(() => [{ d: "M0 0 L1 0 Z" }]);
  const polygon = vi.fn(() => ({}));
  return { default: { generator: () => ({ polygon, toPaths }) } };
});

vi.mock("@/composables/useChartTheme.js", () => ({
  ccToken: vi.fn(() => ""),
}));

let computeFootsteps;

const BASE_CANVAS = {
  fpWidth: 10, // 10 px floor plan image
  fpHeight: 8,
  fpMpp: 0.1, // 0.1 m/px → 1 m × 0.8 m total floor
  canvasW: 1000,
  canvasH: 800,
};

// 0.35 m stride → 35 px in canvas units (with 10px fpWidth × 0.1 mpp = 1 m total → 35 px per 0.35 m)
// stride_px = (0.35 / (10 * 0.1)) * 1000 = 350 px

beforeEach(async () => {
  vi.resetModules();
  ({ computeFootsteps } = await import("@/composables/useFootprintTrail.js").then((m) => ({
    computeFootsteps: m.useFootprintTrail().actions.computeFootsteps,
  })));
});

describe("useFootprintTrail — placement", () => {
  it("returns empty array for empty trails map", () => {
    const trails = new Map();
    const colors = new Map();
    expect(computeFootsteps(trails, colors, Date.now(), BASE_CANVAS)).toEqual([]);
  });

  it("returns empty for a single-point trail (no segment to walk)", () => {
    const now = Date.now();
    const trails = new Map([["ph1", [{ x: 0, y: 0, t: now }]]]);
    const colors = new Map([["ph1", "#ff0000"]]);
    const steps = computeFootsteps(trails, colors, now, BASE_CANVAS);
    expect(steps.length).toBe(0);
  });

  it("produces footsteps at stride spacing for a straight trail", () => {
    const now = Date.now();
    // 2 m straight trail along X axis → 200 px at canvas scale
    // stride_px = (0.35 / 1) * 1000 = 350 px — too short for 200 px trail
    // Use a longer trail: 2.1 m → 2100 px; stride_px=350 → ~6 steps
    const longTrail = [
      { x: 0, y: 0.4, t: now - 5000 },
      { x: 2.1, y: 0.4, t: now - 1000 },
    ];
    const trails = new Map([["ph1", longTrail]]);
    const colors = new Map([["ph1", "#ff0000"]]);
    const steps = computeFootsteps(trails, colors, now, BASE_CANVAS);
    expect(steps.length).toBeGreaterThan(0);
    // All steps belong to ph1
    expect(steps.every((s) => s.phId === "ph1")).toBe(true);
    // Alternating L/R
    const feet = steps.map((s) => s.foot);
    for (let i = 1; i < feet.length; i++) {
      expect(feet[i]).not.toBe(feet[i - 1]);
    }
  });

  it("orients the foot glyph along the travel direction (toe leads)", () => {
    const now = Date.now();
    // Straight trail along +X axis.
    const trail = [
      { x: 0, y: 0.4, t: now - 4000 },
      { x: 2.1, y: 0.4, t: now - 1000 },
    ];
    const trails = new Map([["ph1", trail]]);
    const colors = new Map([["ph1", "#00ff00"]]);
    const steps = computeFootsteps(trails, colors, now, BASE_CANVAS);
    expect(steps.length).toBeGreaterThan(0);
    // The glyph's toe points along local -y; SVG rotate(a) maps (0,-1) to
    // (sin a, -cos a). For +X travel that rotated forward must be ~(1, 0).
    for (const step of steps) {
      const a = (step.angleDeg * Math.PI) / 180;
      const fwdX = Math.sin(a);
      const fwdY = -Math.cos(a);
      expect(fwdX).toBeCloseTo(1, 5);
      expect(fwdY).toBeCloseTo(0, 5);
    }
  });

  it("orients the foot glyph for +Y (downward) travel", () => {
    const now = Date.now();
    // Straight trail along +Y axis.
    const trail = [
      { x: 0.4, y: 0, t: now - 4000 },
      { x: 0.4, y: 0.8, t: now - 1000 },
    ];
    const trails = new Map([["ph1", trail]]);
    const colors = new Map([["ph1", "#00ff00"]]);
    const steps = computeFootsteps(trails, colors, now, BASE_CANVAS);
    expect(steps.length).toBeGreaterThan(0);
    for (const step of steps) {
      const a = (step.angleDeg * Math.PI) / 180;
      const fwdX = Math.sin(a);
      const fwdY = -Math.cos(a);
      expect(fwdX).toBeCloseTo(0, 5);
      expect(fwdY).toBeCloseTo(1, 5);
    }
  });

  it("returns no steps when phId is not in colorsByPh", () => {
    const now = Date.now();
    const trail = [
      { x: 0, y: 0, t: now - 1000 },
      { x: 2, y: 0, t: now },
    ];
    const trails = new Map([["ph1", trail]]);
    const colors = new Map(); // ph1 not in colors → skip
    expect(computeFootsteps(trails, colors, now, BASE_CANVAS)).toEqual([]);
  });

  it("returns empty when canvas params are missing", () => {
    const now = Date.now();
    const trails = new Map([
      [
        "ph1",
        [
          { x: 0, y: 0, t: now - 1000 },
          { x: 1, y: 0, t: now },
        ],
      ],
    ]);
    const colors = new Map([["ph1", "#f00"]]);
    const result = computeFootsteps(trails, colors, now, {
      fpWidth: null,
      fpHeight: null,
      fpMpp: null,
      canvasW: 1000,
      canvasH: 800,
    });
    expect(result).toEqual([]);
  });
});

describe("useFootprintTrail — fade", () => {
  it("fresh footstep has opacity near 1", () => {
    const now = Date.now();
    const trail = [
      { x: 0, y: 0.4, t: now - 200 },
      { x: 2.1, y: 0.4, t: now - 50 },
    ];
    const trails = new Map([["ph1", trail]]);
    const colors = new Map([["ph1", "#f00"]]);
    const steps = computeFootsteps(trails, colors, now, BASE_CANVAS);
    if (steps.length > 0) {
      const newest = steps[steps.length - 1];
      expect(newest.opacity).toBeGreaterThan(0.8);
    }
  });

  it("footstep older than FOOT_FADE_MS is dropped (opacity 0)", () => {
    const now = Date.now();
    // Trail starts 10 s ago — well beyond FOOT_FADE_MS (6000 ms).
    const trail = [
      { x: 0, y: 0.4, t: now - 10_000 },
      { x: 2.1, y: 0.4, t: now - 9_000 },
    ];
    const trails = new Map([["ph1", trail]]);
    const colors = new Map([["ph1", "#f00"]]);
    const steps = computeFootsteps(trails, colors, now, BASE_CANVAS);
    // All steps have age > FOOT_FADE_MS and should be filtered out.
    expect(steps.length).toBe(0);
  });

  it("opacity decreases monotonically with age", () => {
    const now = Date.now();
    // Long trail: old end at 5500 ms ago (near fade boundary), fresh end at 100 ms ago
    const trail = [
      { x: 0, y: 0.4, t: now - 5500 },
      { x: 2.1, y: 0.4, t: now - 100 },
    ];
    const trails = new Map([["ph1", trail]]);
    const colors = new Map([["ph1", "#f00"]]);
    const steps = computeFootsteps(trails, colors, now, BASE_CANVAS);
    if (steps.length > 1) {
      // Steps are ordered old→new; opacity should increase (old is fainter)
      for (let i = 1; i < steps.length; i++) {
        expect(steps[i].opacity).toBeGreaterThanOrEqual(steps[i - 1].opacity - 0.01);
      }
    }
  });
});

describe("useFootprintTrail — caps", () => {
  it("caps per-person steps at 12", () => {
    const now = Date.now();
    // Very long trail to generate many steps
    const trail = [
      { x: 0, y: 0.4, t: now - 5000 },
      { x: 7.0, y: 0.4, t: now - 50 },
    ];
    const trails = new Map([["ph1", trail]]);
    const colors = new Map([["ph1", "#f00"]]);
    const steps = computeFootsteps(trails, colors, now, BASE_CANVAS);
    expect(steps.length).toBeLessThanOrEqual(12);
  });

  it("global cap of 120 limits total footsteps across all PHs", () => {
    const now = Date.now();
    const trails = new Map();
    const colors = new Map();
    // 20 PHs, each with a long trail
    for (let i = 0; i < 20; i++) {
      const id = `ph${i}`;
      trails.set(id, [
        { x: 0, y: i * 0.04, t: now - 5000 },
        { x: 7.0, y: i * 0.04, t: now - 50 },
      ]);
      colors.set(id, "#f00");
    }
    const steps = computeFootsteps(trails, colors, now, BASE_CANVAS);
    expect(steps.length).toBeLessThanOrEqual(120);
  });
});

describe("useFootprintTrail — seed stability", () => {
  it("same inputs produce same seeds across calls (no per-frame boil)", () => {
    const now = Date.now();
    const trail = [
      { x: 0, y: 0.4, t: now - 3000 },
      { x: 2.1, y: 0.4, t: now - 100 },
    ];
    const trails = new Map([["ph1", trail]]);
    const colors = new Map([["ph1", "#f00"]]);
    const steps1 = computeFootsteps(trails, colors, now, BASE_CANVAS);
    const steps2 = computeFootsteps(trails, colors, now, BASE_CANVAS);
    expect(steps1.length).toBe(steps2.length);
    for (let i = 0; i < steps1.length; i++) {
      expect(steps1[i].seed).toBe(steps2[i].seed);
    }
  });

  it("every footstep has a numeric seed", () => {
    const now = Date.now();
    const trail = [
      { x: 0, y: 0.4, t: now - 3000 },
      { x: 2.1, y: 0.4, t: now - 100 },
    ];
    const trails = new Map([["ph1", trail]]);
    const colors = new Map([["ph1", "#f00"]]);
    const steps = computeFootsteps(trails, colors, now, BASE_CANVAS);
    for (const step of steps) {
      expect(typeof step.seed).toBe("number");
      expect(Number.isFinite(step.seed)).toBe(true);
    }
  });
});

describe("useFootprintTrail — reduced motion", () => {
  it("reduced motion: returns steps at constant opacity (no fade math)", () => {
    const now = Date.now();
    // Trail where steps would normally be nearly faded out
    const trail = [
      { x: 0, y: 0.4, t: now - 5800 },
      { x: 2.1, y: 0.4, t: now - 5500 },
    ];
    const trails = new Map([["ph1", trail]]);
    const colors = new Map([["ph1", "#f00"]]);
    const steps = computeFootsteps(trails, colors, now, BASE_CANVAS, { reducedMotion: true });
    // With reduced motion, old steps are not filtered by fade — they use constant opacity
    if (steps.length > 0) {
      for (const s of steps) {
        expect(s.opacity).toBeGreaterThan(0.5); // constant, not near-zero
      }
    }
  });

  it("reduced motion: caps at REDUCED_MOTION_N (5) per person", () => {
    const now = Date.now();
    const trail = [
      { x: 0, y: 0.4, t: now - 5000 },
      { x: 7.0, y: 0.4, t: now - 100 },
    ];
    const trails = new Map([["ph1", trail]]);
    const colors = new Map([["ph1", "#f00"]]);
    const steps = computeFootsteps(trails, colors, now, BASE_CANVAS, { reducedMotion: true });
    expect(steps.length).toBeLessThanOrEqual(5);
  });
});
