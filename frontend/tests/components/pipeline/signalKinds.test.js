import { describe, expect, it } from "vitest";
import { knownSignalKinds } from "@/components/pipeline/steps/index.js";

describe("knownSignalKinds", () => {
  it("includes fall_suspected", () => {
    expect(knownSignalKinds).toContain("fall_suspected");
  });

  it("includes all legacy kinds", () => {
    const legacy = [
      "bathroom_dwell_anomaly",
      "pacing",
      "nighttime_movement",
      "stillness_anomaly",
      "absence",
      "sundowning_index",
    ];
    for (const kind of legacy) {
      expect(knownSignalKinds).toContain(kind);
    }
  });

  it("has no duplicate entries", () => {
    expect(new Set(knownSignalKinds).size).toBe(knownSignalKinds.length);
  });
});
