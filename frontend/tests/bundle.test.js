/**
 * U3-T9: ECharts registration checks.
 *
 * The "no full bundle import" half of this guard (no `from "echarts"`, no
 * `require("echarts")`) is now enforced by eslint.config.js's
 * no-restricted-imports / no-restricted-syntax rules -- those fire at
 * edit time, not just at test time, so they replace the equivalent checks
 * that used to live here. What remains below is not lint-expressible: "this
 * specific file must contain these specific registration calls" is a content
 * assertion, not a syntax restriction.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve as resolvePath } from "node:path";
import { fileURLToPath } from "node:url";

const SRC_DIR = resolvePath(fileURLToPath(import.meta.url), "../../src");

describe("ECharts registration module", () => {
  it("uses the echarts/core explicit import and registers CanvasRenderer", () => {
    const echartsJs = readFileSync(resolvePath(SRC_DIR, "components/charts/echarts.js"), "utf-8");
    expect(echartsJs).toContain('from "echarts/core"');
    expect(echartsJs).toContain("CanvasRenderer");
  });

  it("registers at least one explicit chart type (LineChart)", () => {
    const echartsJs = readFileSync(resolvePath(SRC_DIR, "components/charts/echarts.js"), "utf-8");
    expect(echartsJs).toContain("LineChart");
  });
});
