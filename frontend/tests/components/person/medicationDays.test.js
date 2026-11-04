import { describe, it, expect } from "vitest";
import { formatDays } from "@/components/person/medicationDays.js";

describe("formatDays", () => {
  it("names a daily dose", () => {
    expect(formatDays([0, 1, 2, 3, 4, 5, 6])).toBe("Every day");
  });

  it("lists other days from Monday", () => {
    expect(formatDays([4, 0])).toBe("Mon, Fri");
  });
});
