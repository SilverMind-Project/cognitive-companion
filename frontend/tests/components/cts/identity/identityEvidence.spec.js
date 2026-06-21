import { describe, it, expect } from "vitest";
import { sourceBadge, confidenceLabel, identityLabel } from "@/components/cts/identity/identityEvidence.js";

describe("identityEvidence formatters", () => {
  it("labels operator, conflict, calibrated/uncalibrated ArcFace, ReID, and prior", () => {
    expect(sourceBadge({ authority: "operator" }).label).toBe("Operator");
    expect(sourceBadge({ conflict: true }).label).toBe("Conflict");
    expect(sourceBadge({ decision_source: "face", authority: "arcface_authority" }).label).toBe("ArcFace");
    expect(sourceBadge({ decision_source: "face", authority: "weak" }).label).toBe("ArcFace / Uncalibrated");
    expect(sourceBadge({ decision_source: "reid" }).label).toBe("ReID");
    expect(sourceBadge({ decision_source: "temporal_prior" }).label).toBe("Prior");
  });

  it("conflict takes precedence over operator", () => {
    expect(sourceBadge({ authority: "operator", conflict: true }).label).toBe("Conflict");
  });

  it("shows Verified for operator authority, never a number", () => {
    expect(confidenceLabel({ authority: "operator", calibrated_confidence: 0.9 })).toBe("Verified");
  });

  it("shows calibrated confidence as a percent, dash when absent", () => {
    expect(confidenceLabel({ calibrated_confidence: 0.83 })).toBe("83%");
    expect(confidenceLabel({ calibrated_confidence: null })).toBe("—");
  });

  it("resolves a display name from targets, falling back to Unknown", () => {
    const targets = [{ identity_id: "amma", display_name: "Amma" }];
    expect(identityLabel("amma", targets)).toBe("Amma");
    expect(identityLabel(null, targets)).toBe("Unknown");
    expect(identityLabel("ghost", targets)).toBe("ghost");
  });
});
