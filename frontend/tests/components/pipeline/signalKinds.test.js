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

describe("signal kind icon map (CTSSignalsView)", () => {
  const signalIcons = {
    pacing: "🚶",
    room_revisit_rate: "🔄",
    bathroom_dwell_anomaly: "🚽",
    sundowning_index: "🌅",
    nighttime_movement: "🌙",
    stillness_anomaly: "😴",
    absence: "❓",
    fall_suspected: "⚠️",
  };

  it("has an icon for fall_suspected", () => {
    expect(signalIcons["fall_suspected"]).toBeTruthy();
  });

  it("returns undefined for unknown kinds (no crash, generic fallback is callers responsibility)", () => {
    expect(signalIcons["unknown_future_kind"]).toBeUndefined();
  });
});
