import { describe, it, expect, beforeEach, vi } from "vitest";

// Module-level singleton (gen, _memo) must be fresh per describe block.
// vi.resetModules() achieves this.
let useRoughSketch;

describe("useRoughSketch", () => {
  beforeEach(async () => {
    vi.resetModules();
    ({ useRoughSketch } = await import("@/composables/useRoughSketch.js"));
  });

  const TRI = [[0, 0], [100, 0], [50, 100]];

  it("seedFrom returns a stable unsigned 32-bit integer for the same input", () => {
    const { actions } = useRoughSketch();
    const s1 = actions.seedFrom("room-42");
    const s2 = actions.seedFrom("room-42");
    expect(s1).toBe(s2);
    expect(Number.isInteger(s1)).toBe(true);
    expect(s1).toBeGreaterThanOrEqual(0);
  });

  it("seedFrom returns different values for different inputs", () => {
    const { actions } = useRoughSketch();
    expect(actions.seedFrom("room-1")).not.toBe(actions.seedFrom("room-2"));
  });

  it("path returns a non-empty SVG d string for a triangle", () => {
    const { actions } = useRoughSketch();
    const seed = actions.seedFrom("tri");
    const d = actions.path(TRI, { seed });
    expect(typeof d).toBe("string");
    expect(d.length).toBeGreaterThan(0);
    expect(d).toMatch(/^M/);
  });

  it("path is deterministic: same points + seed → identical d string", () => {
    const { actions } = useRoughSketch();
    const seed = actions.seedFrom("stable");
    const d1 = actions.path(TRI, { seed });
    const d2 = actions.path(TRI, { seed });
    expect(d1).toBe(d2);
  });

  it("path differs between different seeds (same points)", () => {
    const { actions } = useRoughSketch();
    const d1 = actions.path(TRI, { seed: 1 });
    const d2 = actions.path(TRI, { seed: 99 });
    expect(d1).not.toBe(d2);
  });

  it("memoizes: two calls with identical inputs return the same string reference", () => {
    const { actions } = useRoughSketch();
    const seed = actions.seedFrom("memo-test");
    const d1 = actions.path(TRI, { seed });
    const d2 = actions.path(TRI, { seed });
    expect(d1).toBe(d2);
  });

  it("path changes when points change (different geometry = different d)", () => {
    const { actions } = useRoughSketch();
    const seed = 7;
    const d1 = actions.path([[0, 0], [100, 0], [50, 100]], { seed });
    const d2 = actions.path([[0, 0], [200, 0], [100, 200]], { seed });
    expect(d1).not.toBe(d2);
  });

  it("returns { state, actions } shape", () => {
    const sketch = useRoughSketch();
    expect(sketch).toHaveProperty("state");
    expect(sketch).toHaveProperty("actions");
    expect(typeof sketch.actions.path).toBe("function");
    expect(typeof sketch.actions.seedFrom).toBe("function");
  });
});
