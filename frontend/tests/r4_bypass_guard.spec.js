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
import { dirname, join, resolve } from "path";
import { fileURLToPath } from "url";

// Resolved via fileURLToPath, NOT `new URL("../src", import.meta.url)`: Vite statically rewrites
// that pattern as an asset reference, so it evaluated to the literal "/src" and every walk below
// threw ENOENT into a `catch { continue }` -- the guard scanned zero files and passed vacuously
// from the day it was written.
const SRC_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../src");

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
    // No exceptions: since M18 the auth store owns the key, and AdminView -- previously the one
    // allowed site -- goes through it like everything else.
    [],
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
        // Deliberately not wrapped in try/catch: an unreadable directory means the guard is not
        // scanning what it claims to, which must fail loudly rather than pass as "no violations".
        const files = walkVue(dir);
        expect(files.length, `${dir} contains no .vue files to scan`).toBeGreaterThan(0);
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

describe("M18: the auth store is the only owner of the API key", () => {
  // The scan above only reaches .vue files under the CTS directories, so it cannot see a raw
  // key read in a composable, a service, or a store. This walks all of src.
  function walkAll(dir) {
    const results = [];
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) results.push(...walkAll(full));
      else if (/\.(js|ts|vue)$/.test(entry)) results.push(full);
    }
    return results;
  }

  it("no file outside stores/auth.ts touches the cc_api_key storage key", () => {
    const violations = [];
    for (const file of walkAll(SRC_ROOT)) {
      if (file.endsWith("stores/auth.ts")) continue;
      // http.ts declares the storage-key constant and keeps a pre-wire localStorage fallback for
      // requests issued before main.js repoints the provider at the store.
      if (file.endsWith("services/http.ts")) continue;
      readFileSync(file, "utf8")
        .split("\n")
        .forEach((line, i) => {
          if (/localStorage\.(get|set|remove)Item\(\s*["']cc_api_key["']/.test(line)) {
            violations.push(`${file}:${i + 1}  ${line.trim()}`);
          }
        });
    }

    expect(
      violations,
      "The API key lives in the Pinia auth store (src/stores/auth.ts); http.ts reads it through " +
        "setApiKeyProvider. Writing localStorage directly leaves the store's reactive key stale, " +
        `so the app keeps sending the old key until a reload:\n${violations.join("\n")}`,
    ).toEqual([]);
  });
});
