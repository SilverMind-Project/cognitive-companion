/**
 * R4 anti-regression guard: forbids direct localStorage auth and raw fetch()
 * in CTS components and views.
 *
 * Rule 17: frontend must use services/api.js and the CTS wrappers (cts.js,
 * cts_ph.js). localStorage.getItem("cc_api_key") and raw fetch() with auth
 * headers must only appear in the BFF service layer (services/), never in
 * components or views.
 */
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "fs";
import { join } from "path";

const SRC_ROOT = new URL("../src", import.meta.url).pathname;

function walkVue(dir) {
  const results = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const stat = statSync(full);
    if (stat.isDirectory()) {
      results.push(...walkVue(full));
    } else if (entry.endsWith(".vue")) {
      results.push(full);
    }
  }
  return results;
}

const CTS_DIRS = [
  join(SRC_ROOT, "components", "cts"),
  join(SRC_ROOT, "views", "admin"),
  join(SRC_ROOT, "views", "medical"),
];

// Each entry: [pattern, description, allowedFiles]
// allowedFiles: files where the pattern is architecturally legitimate.
const FORBIDDEN = [
  [
    /localStorage\.getItem\(["']cc_api_key["']\)/,
    'localStorage.getItem("cc_api_key") in component/view (use services/cts.js)',
    // AdminView.vue manages the API key setting UI; it is the one legitimate site.
    ["AdminView.vue"],
  ],
  [
    /\bfetch\s*\(`\$\{BASE\}/,
    "raw fetch() with BASE URL interpolation (use services/cts.js)",
    [],
  ],
  [
    /\bfetch\s*\(`\/api\//,
    "raw fetch() with /api/ URL (use services/cts.js)",
    [],
  ],
];

describe("R4 anti-regression: no auth bypass in CTS components and views", () => {
  for (const [pattern, label, allowedFiles] of FORBIDDEN) {
    it(`no ${label}`, () => {
      const violations = [];
      for (const dir of CTS_DIRS) {
        let files;
        try {
          files = walkVue(dir);
        } catch {
          continue;
        }
        for (const file of files) {
          const name = file.split("/").pop();
          if (allowedFiles.includes(name)) continue;
          const src = readFileSync(file, "utf8");
          const lines = src.split("\n");
          lines.forEach((line, i) => {
            if (pattern.test(line)) {
              violations.push(`${file}:${i + 1}  ${line.trim()}`);
            }
          });
        }
      }
      if (violations.length) {
        throw new Error(
          `Rule 17 violation — ${label}:\n${violations.join("\n")}`
        );
      }
    });
  }
});
