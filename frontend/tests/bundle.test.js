/**
 * U3-T9: Bundle guard
 *
 * Asserts that no source file uses the full `echarts` bundle import.
 * Every chart component must import from 'echarts/core', 'echarts/charts',
 * 'echarts/components', or 'echarts/renderers' sub-paths so tree-shaking
 * can eliminate unused code.
 *
 * Rationale: `import ... from "echarts"` (full bundle) is ~1 MB+ minified.
 * Explicit subpath imports let Rollup/Vite tree-shake to the used modules only.
 */
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

const SRC_DIR = resolve(__dirname, "../src");

/** Recursively collect all .js and .vue files under dir. */
function collectFiles(dir) {
  const entries = readdirSync(dir);
  const files = [];
  for (const entry of entries) {
    const full = join(dir, entry);
    const stat = statSync(full);
    if (stat.isDirectory()) {
      files.push(...collectFiles(full));
    } else if (/\.(js|vue)$/.test(entry)) {
      files.push(full);
    }
  }
  return files;
}

const SRC_FILES = collectFiles(SRC_DIR);

describe("Bundle guard: no full ECharts import", () => {
  it("no src file contains from 'echarts' (full bundle, single quotes)", () => {
    const violations = [];
    for (const file of SRC_FILES) {
      const content = readFileSync(file, "utf-8");
      if (/from\s+['"]echarts['"]/.test(content)) {
        violations.push(file.replace(SRC_DIR, "src"));
      }
    }
    expect(
      violations,
      `Full ECharts import found in: ${violations.join(", ")}. Use explicit subpath imports (echarts/core, echarts/charts, etc).`
    ).toHaveLength(0);
  });

  it('no src file contains require("echarts") full bundle call', () => {
    const violations = [];
    for (const file of SRC_FILES) {
      const content = readFileSync(file, "utf-8");
      if (/require\s*\(\s*['"]echarts['"]\s*\)/.test(content)) {
        violations.push(file.replace(SRC_DIR, "src"));
      }
    }
    expect(violations).toHaveLength(0);
  });

  it("echarts.js registration module uses echarts/core explicit import", () => {
    const echartsJs = readFileSync(
      resolve(SRC_DIR, "components/charts/echarts.js"),
      "utf-8"
    );
    expect(echartsJs).toContain("from \"echarts/core\"");
    expect(echartsJs).toContain("CanvasRenderer");
  });

  it("at least one explicit chart type is registered (LineChart)", () => {
    const echartsJs = readFileSync(
      resolve(SRC_DIR, "components/charts/echarts.js"),
      "utf-8"
    );
    expect(echartsJs).toContain("LineChart");
  });
});
