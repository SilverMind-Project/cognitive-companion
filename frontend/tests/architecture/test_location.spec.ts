import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const FRONTEND_ROOT = path.resolve(import.meta.dirname, "../..");
const SRC_DIR = path.join(FRONTEND_ROOT, "src");

function findMisplacedTests(dir: string, relBase = ""): string[] {
  const hits: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const rel = relBase ? `${relBase}/${entry.name}` : entry.name;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "__tests__") {
        hits.push(`src/${rel}`);
      } else {
        hits.push(...findMisplacedTests(full, rel));
      }
    } else if (/\.(spec|test)\.[^/]+$/.test(entry.name)) {
      hits.push(`src/${rel}`);
    }
  }
  return hits;
}

describe("frontend test file location (front-end rule 3)", () => {
  it("contains zero spec/test files or __tests__ directories under src/", () => {
    const misplaced = findMisplacedTests(SRC_DIR);
    expect(misplaced).toEqual([]);
  });

  it("pins vitest test.include to tests/**/*.{spec,test}.{js,ts}", () => {
    const viteConfig = fs.readFileSync(path.join(FRONTEND_ROOT, "vite.config.js"), "utf8");
    expect(viteConfig).toContain('include: ["tests/**/*.{spec,test}.{js,ts}"]');
  });
});
