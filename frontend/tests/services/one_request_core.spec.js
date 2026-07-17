/**
 * One request core (M17).
 *
 * Before M17 the request/auth/error plumbing existed in five places: `api.js`'s six variants
 * plus a private copy in each of `cts.js`, `cts_identity.js`, `cts_ph.js` and `household.js`.
 * They drifted -- different error message shapes, some encoding params and some interpolating
 * them raw. All HTTP now goes through `services/http.ts`.
 *
 * `r4_bypass_guard.spec.js` enforces the same rule for components and views (it only walks
 * `.vue` files); this covers the service layer, which is where the duplication actually lived.
 * M19 replaces both with ESLint rules that catch this at edit time rather than in CI.
 */
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "fs";
import { join, resolve } from "path";

// vitest runs with the frontend package root as cwd (see vite.config.js `test`).
const SERVICES_ROOT = resolve(process.cwd(), "src/services");

// The core itself, and the one endpoint that legitimately does not use it.
const ALLOWED = new Set([
  // Owns every fetch call in the app, by design.
  "http.ts",
  // Authenticates with a per-rule X-Webhook-Secret rather than the app API key, so it must not
  // pass through the auth middleware. Documented at the call site.
  "webhooks.ts",
]);

function walk(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else if (/\.(js|ts)$/.test(entry)) out.push(full);
  }
  return out;
}

describe("one request core", () => {
  it("no service module calls fetch() directly except the core", () => {
    const violations = [];

    for (const file of walk(SERVICES_ROOT)) {
      if (ALLOWED.has(file.split("/").pop())) continue;
      const lines = readFileSync(file, "utf8").split("\n");
      lines.forEach((line, i) => {
        // `await fetch(` / `= fetch(` / `return fetch(`: a real call, not a local helper
        // named fetch and not the word inside a comment.
        if (/(?:await|=|return)\s+fetch\s*\(/.test(line) && !/^\s*(\/\/|\*)/.test(line)) {
          violations.push(`${file}:${i + 1}  ${line.trim()}`);
        }
      });
    }

    expect(
      violations,
      "Service module(s) call fetch() directly. Use the typed client or the helpers in " +
        `services/http.ts:\n${violations.join("\n")}`,
    ).toEqual([]);
  });

  it("no service module reads the API key out of localStorage itself", () => {
    const violations = [];

    for (const file of walk(SERVICES_ROOT)) {
      if (ALLOWED.has(file.split("/").pop())) continue;
      const lines = readFileSync(file, "utf8").split("\n");
      lines.forEach((line, i) => {
        if (/localStorage\.(get|set)Item\(\s*["']cc_api_key["']/.test(line)) {
          violations.push(`${file}:${i + 1}  ${line.trim()}`);
        }
      });
    }

    expect(
      violations,
      "The API key is owned by the Pinia auth store (M18), which services/http.ts reads through " +
        `its setApiKeyProvider seam. A direct localStorage read here bypasses the store and goes ` +
        `stale the moment the key is rotated:\n${violations.join("\n")}`,
    ).toEqual([]);
  });

  it("contracts.js is gone and stays gone", () => {
    const names = walk(SERVICES_ROOT).map((f) => f.split("/").pop());

    expect(
      names,
      "contracts.js was the hand-rolled dev-only shape checker M17 replaced with types " +
        "generated from openapi.json. Do not reintroduce it.",
    ).not.toContain("contracts.js");
  });
});
