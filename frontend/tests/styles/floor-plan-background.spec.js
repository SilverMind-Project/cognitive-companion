import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const themeCss = readFileSync(resolve(process.cwd(), "src/styles/theme.css"), "utf8");

describe("floor-plan background treatment", () => {
  it("uses one theme-independent opacity token with a shared utility", () => {
    expect(themeCss).toMatch(/--cc-floor-plan-background-opacity:\s*0\.55/);
    expect(themeCss).toMatch(
      /\.cc-floor-plan-background-image\s*\{[\s\S]*?opacity:\s*var\(--cc-floor-plan-background-opacity\)/,
    );
  });
});
