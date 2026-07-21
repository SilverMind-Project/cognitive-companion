import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const maraudersCss = readFileSync(resolve(process.cwd(), "src/styles/marauders.css"), "utf8");
const keyframesView = readFileSync(
  resolve(process.cwd(), "src/views/admin/CTSKeyframesView.vue"),
  "utf8",
);
const adjacencyView = readFileSync(
  resolve(process.cwd(), "src/views/admin/CTSAdjacencyView.vue"),
  "utf8",
);
// moved the floor-plan <img> out of CTSCalibrationView.vue into its own pane component.
const calibrationFloorPlanPane = readFileSync(
  resolve(process.cwd(), "src/components/cts/calibration/FloorPlanPickerPane.vue"),
  "utf8",
);
// also decomposed CTSFloorPlanView.vue: the raster/SVG background images that
// used to live in one file are now spread across its mode-panel components.
const floorPlanUploadPanel = readFileSync(
  resolve(process.cwd(), "src/components/cts/floor/FloorPlanUploadPanel.vue"),
  "utf8",
);
const coverageCameraMap = readFileSync(
  resolve(process.cwd(), "src/components/cts/floor/CoverageCameraMap.vue"),
  "utf8",
);
const heatmapModePanel = readFileSync(
  resolve(process.cwd(), "src/components/cts/floor/HeatmapModePanel.vue"),
  "utf8",
);
const liveFloorCanvas = readFileSync(
  resolve(process.cwd(), "src/components/cts/floor/LiveFloorCanvas.vue"),
  "utf8",
);
const editRoomsPanel = readFileSync(
  resolve(process.cwd(), "src/components/cts/floor/EditRoomsPanel.vue"),
  "utf8",
);
const floorPlanPanelFiles = [
  floorPlanUploadPanel,
  coverageCameraMap,
  heatmapModePanel,
  liveFloorCanvas,
  editRoomsPanel,
];

describe("Marauders painterly image wiring", () => {
  it("scopes the global filter to the Marauders theme with an opt-out", () => {
    expect(maraudersCss).toContain(".v-theme--ccMarauders img:not(.marauders-no-paint)");
    expect(maraudersCss).toContain('filter: url("#marauders-paint") sepia(0.12)');
    expect(maraudersCss).toContain(".marauders-no-paint img");
  });

  it("opts floor-plan raster and SVG backgrounds out of painting", () => {
    const totalOccurrences = floorPlanPanelFiles.reduce(
      (n, file) => n + (file.match(/marauders-no-paint/g)?.length ?? 0),
      0,
    );
    expect(totalOccurrences).toBeGreaterThanOrEqual(7);
    expect(floorPlanUploadPanel).toMatch(/floor-plan-preview marauders-no-paint/);
    expect(coverageCameraMap).toMatch(
      /coverage-fp-img cc-floor-plan-background-image marauders-no-paint/,
    );
    expect(heatmapModePanel).toMatch(
      /<image[\s\S]*?class="cc-floor-plan-background-image marauders-no-paint"/,
    );
    expect(liveFloorCanvas).toMatch(
      /<image[\s\S]*?class="cc-floor-plan-background-image marauders-no-paint"/,
    );
    expect(adjacencyView).toMatch(/:src="floorPlanUrl"[\s\S]*?class="marauders-no-paint"/);
    expect(calibrationFloorPlanPane).toMatch(/:src="floorPlanUrl"[\s\S]*?marauders-no-paint/);
  });

  it("keeps representative content images eligible for the global filter", () => {
    expect(keyframesView).toMatch(/<v-img[\s\S]*?class="keyframe-image"/);
    expect(keyframesView).not.toMatch(/keyframe-image marauders-no-paint/);
  });
});
