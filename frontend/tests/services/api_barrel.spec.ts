/**
 * Barrel pin.
 *
 * migrates `api.js`'s ~150 methods onto the typed client over two PRs (17a: rules, pipeline,
 * workflows; 17b: everything else). The migration is mechanical and therefore easy to silently
 * drop a method from -- and a dropped method is not a type error anywhere, it is a runtime
 * `api.foo is not a function` in whichever view happened to call it.
 *
 * So: the method-name set is snapshotted from `api.js` as it stood *before* the first migration
 * (`__api_methods_pre_m17.json`, 178 names) and pinned here. The surface may grow; it may not
 * shrink. When 17b finishes and `api.js` is a pure barrel, this test is what proves nothing was
 * lost on the way.
 */

import { describe, it, expect } from "vitest";

import { api } from "@/services/api.js";
import preM17Methods from "./__api_methods_pre_m17.json";

const currentMethods = () =>
  Object.entries(api)
    .filter(([, value]) => typeof value === "function")
    .map(([name]) => name);

describe("api barrel", () => {
  it("still exposes every method that existed before the M17 migration", () => {
    const current = new Set(currentMethods());
    const dropped = (preM17Methods as string[]).filter((name) => !current.has(name));

    expect(dropped, `api.js lost method(s) during migration: ${dropped.join(", ")}`).toEqual([]);
  });

  it("exposes the migrated domains through the typed modules", async () => {
    // Spot-check one method per pilot module: present, and actually the module's function
    // rather than a leftover local definition.
    const rules = await import("@/services/modules/rules");
    const pipeline = await import("@/services/modules/pipeline");
    const workflows = await import("@/services/modules/workflows");

    expect(api.getRules).toBe(rules.getRules);
    expect(api.getStepTypes).toBe(pipeline.getStepTypes);
    expect(api.getWorkflowDetail).toBe(workflows.getWorkflowDetail);
  });

  it("every pilot-module export is reachable from the barrel", async () => {
    const modules = await Promise.all([
      import("@/services/modules/rules"),
      import("@/services/modules/pipeline"),
      import("@/services/modules/workflows"),
    ]);

    const missing: string[] = [];
    for (const mod of modules) {
      for (const [name, value] of Object.entries(mod)) {
        if (typeof value === "function" && (api as Record<string, unknown>)[name] !== value) {
          missing.push(name);
        }
      }
    }

    expect(missing, `not re-exported by api.js: ${missing.join(", ")}`).toEqual([]);
  });
});
