import { describe, expect, it } from "vitest";
import vocabularies from "@/generated/vocabularies.json";
import { knownSignalKinds, stepConfigMap } from "@/components/pipeline/steps/index.js";
import { STEP_DOT_COLORS } from "@/components/pipeline/steps/stepMeta.js";

// STEP_DOT_COLORS is pure presentation (frontend-owned, not generated); these step types
// intentionally have no dedicated dot color and fall back to stepDotColor()'s "primary"
// default (backend-hardening-m14 task 7).
const STEP_DOT_COLOR_FALLBACK_EXEMPT = new Set(["guided_task_start", "quiz_start"]);

describe("vocabulary completeness: step types", () => {
  it("every generated step type has a stepConfigMap entry", () => {
    for (const step of vocabularies.step_types) {
      expect(
        Object.hasOwn(stepConfigMap, step.type_name),
        `missing stepConfigMap entry for '${step.type_name}'`,
      ).toBe(true);
    }
  });

  it("every generated step type has a STEP_DOT_COLORS entry or a documented fallback", () => {
    for (const step of vocabularies.step_types) {
      const hasColor = Object.hasOwn(STEP_DOT_COLORS, step.type_name);
      const isExempt = STEP_DOT_COLOR_FALLBACK_EXEMPT.has(step.type_name);
      expect(
        hasColor || isExempt,
        `'${step.type_name}' has no STEP_DOT_COLORS entry and is not in the documented fallback list`,
      ).toBe(true);
    }
  });
});

describe("vocabulary completeness: signal kinds", () => {
  it("knownSignalKinds includes every generated signal kind", () => {
    for (const kind of vocabularies.signal_kinds) {
      expect(knownSignalKinds).toContain(kind);
    }
  });
});
