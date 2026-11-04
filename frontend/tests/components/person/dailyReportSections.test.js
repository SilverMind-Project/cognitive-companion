import { describe, it, expect } from "vitest";
import {
  formatMinutes,
  reportSections,
  wellnessColor,
} from "@/components/person/dailyReportSections.js";

const section = (report, key) => reportSections(report).find((s) => s.key === key);

describe("formatMinutes", () => {
  it("reads as hours and minutes", () => {
    expect(formatMinutes(45)).toBe("45 min");
    expect(formatMinutes(452)).toBe("7 h 32 min");
    expect(formatMinutes(120)).toBe("2 h");
  });
});

describe("wellnessColor", () => {
  it("uses the backend's 0 to 100 scale", () => {
    expect(wellnessColor(86)).toBe("success");
    expect(wellnessColor(60)).toBe("warning");
    expect(wellnessColor(20)).toBe("error");
  });
});

describe("reportSections", () => {
  it("shows plain labels and units, not field names", () => {
    const rows = section({ sleep: { total_minutes: 452, quality_score: 0.94 } }, "sleep").rows;
    expect(rows).toContainEqual({ label: "Total sleep", value: "7 h 32 min" });
    expect(rows).toContainEqual({ label: "Of 8-hour target", value: "94%" });
  });

  it("lists rooms from the distribution, longest first", () => {
    const report = {
      room_time: { distribution: { Kitchen: 95, Bedroom: 480 }, total_minutes: 575 },
    };
    expect(section(report, "room_time").rows).toEqual([
      { label: "Bedroom", value: "8 h" },
      { label: "Kitchen", value: "1 h 35 min" },
    ]);
  });

  it("never shows the placeholder adherence", () => {
    const report = { medication: { doses_taken: 2, doses_due: 3, adherence_pct: 66.7 } };
    const labels = section(report, "medication").rows.map((r) => r.label);
    expect(labels).toContain("Doses taken");
    expect(labels.join()).not.toMatch(/adherence|due/i);
  });

  it("leaves a section empty when nothing happened", () => {
    expect(section({ exercise: { session_count: 0, total_minutes: 0 } }, "exercise").rows).toEqual(
      [],
    );
  });
});
