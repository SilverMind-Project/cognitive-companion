import { describe, expect, it } from "vitest";
import {
  addRectRegion,
  deleteRegion,
  isValidRegionId,
  rectRegionSummary,
  updateRegionField,
} from "@/components/pipeline/steps/_shared/useRegionList.js";

describe("useRegionList", () => {
  describe("isValidRegionId", () => {
    it("accepts lowercase letters, digits, underscores", () => {
      expect(isValidRegionId("kettle_counter")).toBe(true);
      expect(isValidRegionId("region_1")).toBe(true);
      expect(isValidRegionId("a")).toBe(true);
    });

    it("rejects invalid ids", () => {
      expect(isValidRegionId("Kettle")).toBe(false);
      expect(isValidRegionId("1region")).toBe(false);
      expect(isValidRegionId("has space")).toBe(false);
      expect(isValidRegionId("")).toBe(false);
      expect(isValidRegionId(null)).toBe(false);
      expect(isValidRegionId(undefined)).toBe(false);
    });
  });

  describe("addRectRegion", () => {
    it("appends a default region with a sequential id/name", () => {
      const regions = addRectRegion([]);
      expect(regions).toHaveLength(1);
      expect(regions[0]).toMatchObject({
        id: "region_1",
        name: "Region 1",
        x: 0.1,
        y: 0.1,
        width: 0.3,
        height: 0.3,
      });
    });

    it("does not mutate the input array", () => {
      const input = [{ id: "region_1", name: "Region 1", x: 0, y: 0, width: 1, height: 1 }];
      const result = addRectRegion(input);
      expect(result).not.toBe(input);
      expect(input).toHaveLength(1);
      expect(result).toHaveLength(2);
    });
  });

  describe("deleteRegion", () => {
    it("removes the region at the given index", () => {
      const regions = [{ id: "a" }, { id: "b" }, { id: "c" }];
      const result = deleteRegion(regions, 1);
      expect(result.map((r) => r.id)).toEqual(["a", "c"]);
    });
  });

  describe("updateRegionField", () => {
    it("updates a single field without mutating siblings", () => {
      const regions = [
        { id: "a", name: "A" },
        { id: "b", name: "B" },
      ];
      const result = updateRegionField(regions, 0, "name", "Renamed");
      expect(result[0]).toEqual({ id: "a", name: "Renamed" });
      expect(result[1]).toEqual({ id: "b", name: "B" });
      expect(regions[0].name).toBe("A");
    });
  });

  describe("rectRegionSummary", () => {
    it("formats ratios as percentages", () => {
      const summary = rectRegionSummary({ x: 0.1, y: 0.2, width: 0.3, height: 0.4 });
      expect(summary).toBe("30% wide x 40% tall, at (10%, 20%)");
    });
  });
});
