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

  it("shows each dose against the schedule", () => {
    const report = {
      medication: {
        doses_taken: 2,
        confirmed_doses: 1,
        inferred_doses: 1,
        doses_scheduled: 3,
        adherence_pct: 50,
        doses: [
          { label: "Morning", dose_time: "08:00", status: "taken" },
          { label: "Lunch", dose_time: "13:00", status: "likely_taken" },
          { label: "Noon", dose_time: "12:00", status: "missed" },
          { label: "Evening", dose_time: "20:30", status: "upcoming" },
        ],
      },
    };
    expect(section(report, "medication").rows).toEqual(
      expect.arrayContaining([
        { label: "8:00 AM Morning", value: "Taken" },
        { label: "1:00 PM Lunch", value: "Likely taken (camera)" },
        { label: "12:00 PM Noon", value: "Missed" },
        { label: "8:30 PM Evening", value: "Upcoming" },
        { label: "Adherence so far", value: "50%" },
      ]),
    );
  });

  it("shows doses beyond the schedule", () => {
    const report = {
      medication: {
        doses_taken: 2,
        doses_scheduled: 1,
        adherence_pct: 100,
        doses: [{ label: "Morning", dose_time: "08:00", status: "taken" }],
        excess_doses: [
          { kind: "extra", taken_at: "2026-11-04T14:10:00Z", confirmed: true },
          { kind: "unscheduled", taken_at: "2026-11-04T18:30:00Z", confirmed: false },
        ],
      },
    };
    const { rows } = section(report, "medication");
    expect(rows.find((r) => r.label.endsWith("Extra dose")).value).toBe("Taken");
    expect(rows.find((r) => r.label.endsWith("Unscheduled dose")).value).toBe(
      "Likely taken (camera)",
    );
  });

  it("says when no schedule is set, and shows no adherence", () => {
    const report = {
      medication: { doses_taken: 1, doses_scheduled: null, adherence_pct: null, doses: [] },
    };
    const { rows } = section(report, "medication");
    expect(rows).toContainEqual({ label: "Schedule", value: "Not set" });
    expect(rows.map((r) => r.label)).not.toContain("Adherence so far");
  });

  it("offers the schedule note even with nothing logged", () => {
    const report = { medication: { doses_taken: 0, doses_scheduled: null, doses: [] } };
    expect(section(report, "medication").rows[0]).toEqual({ label: "Schedule", value: "Not set" });
  });

  it("leaves a section empty when nothing happened", () => {
    expect(section({ exercise: { session_count: 0, total_minutes: 0 } }, "exercise").rows).toEqual(
      [],
    );
  });
});
