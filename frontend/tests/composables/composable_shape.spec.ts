import fs from "node:fs";
import path from "node:path";
import { defineComponent, isReadonly, isRef, ref } from "vue";
import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAggregatorState } from "@/composables/useAggregatorState.js";
import { useAttestedFaceAudit } from "@/composables/useAttestedFaceAudit";
import { useCanvasPipeline } from "@/composables/useCanvasPipeline.js";
import { useDailyLivingHealth } from "@/composables/useDailyLivingHealth.js";
import { useFaceCalibrationReview } from "@/composables/useFaceCalibrationReview";
import { useGaitTrend } from "@/composables/useGaitTrend.js";
import { useGuidedMetrics } from "@/composables/useGuidedMetrics.js";
import { useGuidedSessionConsole } from "@/composables/useGuidedSessionConsole.js";
import { useHeatmap } from "@/composables/useHeatmap.js";
import { useIdentityCorrection } from "@/composables/useIdentityCorrection.js";
import { useIdentityReadiness } from "@/composables/useIdentityReadiness";
import { useInferenceTelemetry } from "@/composables/useInferenceTelemetry.js";
import { useKioskMode } from "@/composables/useKioskMode.js";
import { useMedicationSchedule } from "@/composables/useMedicationSchedule.js";
import { usePHDetail } from "@/composables/usePHDetail.js";
import { usePHLifecycle } from "@/composables/usePHLifecycle.js";
import { usePHList } from "@/composables/usePHList.js";
import { useQuizzesAdmin } from "@/composables/useQuizzesAdmin.js";
import { useReIDReview } from "@/composables/useReIDReview.js";
import { useRoutineBuilder } from "@/composables/useRoutineBuilder.js";
import { useVisitorReview } from "@/composables/useVisitorReview.js";
import { useWearables } from "@/composables/useWearables";

const FRONTEND_ROOT = path.resolve(import.meta.dirname, "../..");
const COMPOSABLES_DIR = path.join(FRONTEND_ROOT, "src/composables");

type NotifyStub = ((message: string, color?: string) => void) & {
  success: (message: string) => void;
  error: (message: string) => void;
  warning: (message: string) => void;
};

function makeNotify(): NotifyStub {
  return Object.assign(vi.fn(), {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
  });
}

function runInSetup<T>(factory: () => T): T {
  let result!: T;
  const Harness = defineComponent({
    setup() {
      result = factory();
      return () => null;
    },
  });
  const wrapper = mount(Harness);
  wrapper.unmount();
  return result;
}

function isReadonlyComputedRef(value: unknown): boolean {
  return isRef(value) && isReadonly(value) && "effect" in (value as object);
}

/**
 * Explicit list of every server-state composable enforced against the C7 contract:
 * returns `{ state, actions }` plus optional read-only `ComputedRef` keys, with
 * every entry in `actions` a function and no aliased references.
 */
const ENFORCED_SERVER_COMPOSABLES: Record<string, () => Record<string, unknown>> = {
  "useAggregatorState.js": () => useAggregatorState() as unknown as Record<string, unknown>,
  "useAttestedFaceAudit.ts": () =>
    useAttestedFaceAudit(makeNotify()) as unknown as Record<string, unknown>,
  "useCanvasPipeline.js": () =>
    useCanvasPipeline(ref("rule-1"), { notify: makeNotify() }) as unknown as Record<
      string,
      unknown
    >,
  "useDailyLivingHealth.js": () => useDailyLivingHealth() as unknown as Record<string, unknown>,
  "useFaceCalibrationReview.ts": () =>
    useFaceCalibrationReview(makeNotify()) as unknown as Record<string, unknown>,
  "useGaitTrend.js": () => useGaitTrend() as unknown as Record<string, unknown>,
  "useGuidedMetrics.js": () => useGuidedMetrics() as unknown as Record<string, unknown>,
  "useGuidedSessionConsole.js": () =>
    useGuidedSessionConsole(ref("sess-1"), { notify: makeNotify() }) as unknown as Record<
      string,
      unknown
    >,
  "useHeatmap.js": () => useHeatmap() as unknown as Record<string, unknown>,
  "useIdentityCorrection.js": () =>
    useIdentityCorrection(makeNotify()) as unknown as Record<string, unknown>,
  "useIdentityReadiness.ts": () => useIdentityReadiness() as unknown as Record<string, unknown>,
  "useInferenceTelemetry.js": () => useInferenceTelemetry() as unknown as Record<string, unknown>,
  "useKioskMode.js": () => useKioskMode() as unknown as Record<string, unknown>,
  "useMedicationSchedule.js": () =>
    useMedicationSchedule(ref("person-1"), { notify: makeNotify() }) as unknown as Record<
      string,
      unknown
    >,
  "usePHDetail.js": () => usePHDetail() as unknown as Record<string, unknown>,
  "usePHLifecycle.js": () => usePHLifecycle(makeNotify()) as unknown as Record<string, unknown>,
  "usePHList.js": () => usePHList() as unknown as Record<string, unknown>,
  "useQuizzesAdmin.js": () =>
    useQuizzesAdmin({ notify: makeNotify() }) as unknown as Record<string, unknown>,
  "useReIDReview.js": () => useReIDReview(makeNotify()) as unknown as Record<string, unknown>,
  "useRoutineBuilder.js": () =>
    useRoutineBuilder({ notify: makeNotify() }) as unknown as Record<string, unknown>,
  "useVisitorReview.js": () => useVisitorReview(makeNotify()) as unknown as Record<string, unknown>,
  "useWearables.ts": () => useWearables(makeNotify()) as unknown as Record<string, unknown>,
};

/**
 * Frozen ratchet allowlist of pre-EG-M13 server-state composables that still return
 * flat refs/functions. Do NOT add new files here: migrate entries out into
 * ENFORCED_SERVER_COMPOSABLES when touched.
 */
const LEGACY_FLAT_SERVER_COMPOSABLES = new Set([
  "useAutoCalibration.js",
  "useCalibrationCamera.js",
  "useCalibrationPoints.js",
  "useCalibrationPreview.js",
  "useCtsLiveCameras.js",
  "useCtsWebSocket.js",
  "useFloorPlan.js",
  "useFloorPlanCanvas.js",
  "useFloorPlanCoverage.js",
  "useFloorPlanDoorZones.js",
  "useFloorPlanHeatmap.js",
  "useFloorPlanRooms.js",
  "useFloorPlanUpload.js",
  "useFloorRegion.js",
  "useLivePipeline.js",
  "useLiveWorldMarkers.js",
  "usePersonPresence.js",
  "usePresenceTimeline.js",
  "useRoomPolygonEditor.js",
  "useRuleContexts.js",
  "useRuleDependencies.js",
  "useRuleDetail.js",
  "useRuleExecutions.js",
  "useWorldSnapshot.js",
]);

/**
 * Non-server-state UI/theme/math utility composables outside the server-state C7 scope.
 */
const LOCAL_UI_COMPOSABLES = new Set([
  "useAnnotationStyle.js",
  "useBlurMode.js",
  "useCanvasZoom.js",
  "useChartTheme.js",
  "useConfirm.js",
  "useCtsSeverity.js",
  "useFloorPlanProjection.js",
  "useFootprintTrail.js",
  "useFormatRelative.js",
  "useIdentityColor.js",
  "useLiveIdentityCache.js",
  "useLiveOverlayGeometry.js",
  "useMaraudersMode.js",
  "useMultiCameraLinks.js",
  "useNotify.js",
  "useReviewKeys.ts",
  "useRoughSketch.js",
  "useSpatialCanvas.js",
]);

function assertComposableShape(name: string, returned: Record<string, unknown>): void {
  expect(returned, `${name} must return an object`).toBeTypeOf("object");
  expect(returned, `${name} must not return null`).not.toBeNull();
  expect(returned, `${name} must expose 'state'`).toHaveProperty("state");
  expect(returned, `${name} must expose 'actions'`).toHaveProperty("actions");
  expect(returned.state, `${name}.state must be an object`).toBeTypeOf("object");
  expect(returned.state, `${name}.state must not be null`).not.toBeNull();
  expect(returned.actions, `${name}.actions must be an object`).toBeTypeOf("object");
  expect(returned.actions, `${name}.actions must not be null`).not.toBeNull();

  const actionsObj = returned.actions as Record<string, unknown>;
  expect(
    Object.keys(actionsObj).length,
    `${name}.actions must contain at least one action`,
  ).toBeGreaterThan(0);
  for (const [actionName, fn] of Object.entries(actionsObj)) {
    expect(fn, `${name}.actions.${actionName} must be a function`).toBeTypeOf("function");
  }

  const seenRefs = new Set<unknown>();
  for (const [key, value] of Object.entries(returned)) {
    if (typeof value === "object" && value !== null) {
      expect(seenRefs.has(value), `${name} must not alias the same object under '${key}'`).toBe(
        false,
      );
      seenRefs.add(value);
    }
    if (key === "state" || key === "actions") continue;
    expect(
      isReadonlyComputedRef(value),
      `${name} extra top-level key '${key}' must be a read-only ComputedRef (no raw refs or functions outside actions)`,
    ).toBe(true);
  }
}

describe("composable return shape (C7 / front-end rule 18)", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({}),
        text: async () => "{}",
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("classifies every src/composables/use*.{js,ts} file with no overlap and no omissions", () => {
    const onDisk = fs
      .readdirSync(COMPOSABLES_DIR)
      .filter((f) => /^use.*\.(js|ts)$/.test(f))
      .sort();
    const enforced = new Set(Object.keys(ENFORCED_SERVER_COMPOSABLES));

    // No file appears in more than one bucket.
    for (const f of enforced) {
      expect(LEGACY_FLAT_SERVER_COMPOSABLES.has(f), `${f} in both enforced and legacy`).toBe(false);
      expect(LOCAL_UI_COMPOSABLES.has(f), `${f} in both enforced and local`).toBe(false);
    }
    for (const f of LEGACY_FLAT_SERVER_COMPOSABLES) {
      expect(LOCAL_UI_COMPOSABLES.has(f), `${f} in both legacy and local`).toBe(false);
    }

    const classified = [
      ...enforced,
      ...LEGACY_FLAT_SERVER_COMPOSABLES,
      ...LOCAL_UI_COMPOSABLES,
    ].sort();
    expect(classified).toEqual(onDisk);
    expect(enforced.size).toBeGreaterThanOrEqual(21);
  });

  it("canary: rejects raw refs and top-level functions outside actions", () => {
    const rawRef = ref(0);
    expect(() =>
      assertComposableShape("badRawRef", { state: {}, actions: { run: () => {} }, count: rawRef }),
    ).toThrow();
    expect(() =>
      assertComposableShape("badFn", { state: {}, actions: { run: () => {} }, helper: () => {} }),
    ).toThrow();
  });

  for (const [file, factory] of Object.entries(ENFORCED_SERVER_COMPOSABLES)) {
    it(`${file} returns { state, actions } plus read-only ComputedRef keys only`, () => {
      const returned = runInSetup(factory);
      assertComposableShape(file, returned);
    });
  }
});
