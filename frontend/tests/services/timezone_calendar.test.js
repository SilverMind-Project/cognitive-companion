import { afterEach, describe, it, expect, vi } from "vitest";
import {
  calendarDateToPicker,
  formatCalendarDate,
  initTimezone,
  pickerToCalendarDate,
  todayInAppTimezone,
} from "@/services/timezone.js";

describe("calendar dates", () => {
  afterEach(() => vi.useRealTimers());

  it("today follows app.timezone, not UTC", () => {
    // 9 PM on Nov 4 in New York is already Nov 5 in UTC.
    vi.useFakeTimers({ now: new Date("2026-11-05T02:00:00Z") });
    initTimezone("America/New_York");
    expect(todayInAppTimezone()).toBe("2026-11-04");
    initTimezone("Asia/Tokyo");
    expect(todayInAppTimezone()).toBe("2026-11-05");
  });

  it("formats a calendar date without moving it", () => {
    initTimezone("America/Los_Angeles");
    expect(formatCalendarDate("2026-11-04")).toBe("Nov 4, 2026");
  });

  it("round-trips through the date picker", () => {
    expect(pickerToCalendarDate(calendarDateToPicker("2026-11-04"))).toBe("2026-11-04");
  });
});
