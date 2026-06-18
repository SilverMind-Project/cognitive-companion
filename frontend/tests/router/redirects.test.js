/**
 * U4-T5: Router redirects
 *
 * Verifies that each superseded route redirects to the correct workspace panel
 * and that no superseded route resolves to a 404 (missing component).
 */
import { describe, it, expect } from "vitest";
import { createRouter, createMemoryHistory } from "vue-router";
import { routes } from "../../src/router/index.js";

// createMemoryHistory for test environment (no browser URL needed)
function makeRouter() {
  return createRouter({ history: createMemoryHistory(), routes });
}

describe("Router redirects (U4)", () => {
  it("/ redirects to /companion", async () => {
    const router = makeRouter();
    await router.push("/");
    expect(router.currentRoute.value.fullPath).toBe("/companion");
  });

  it("/ preserves kiosk query when redirecting to /companion", async () => {
    const router = makeRouter();
    await router.push("/?kiosk=1");
    expect(router.currentRoute.value.fullPath).toBe("/companion?kiosk=1");
  });


  it("/admin/activity redirects to executions live tab", async () => {
    const router = makeRouter();
    await router.push("/admin/activity");
    expect(router.currentRoute.value.fullPath).toBe("/admin/executions?tab=live");
  });

  it("/admin/workflows redirects to executions history tab", async () => {
    const router = makeRouter();
    await router.push("/admin/workflows");
    expect(router.currentRoute.value.fullPath).toBe("/admin/executions?tab=history");
  });

  it("/admin/cts/dashboard redirects to /admin/tracking with panel=overview", async () => {
    const router = makeRouter();
    await router.push("/admin/cts/dashboard");
    expect(router.currentRoute.value.fullPath).toBe("/admin/tracking?panel=overview");
  });

  it("/admin/cts/live redirects to /admin/tracking with panel=live-floor", async () => {
    const router = makeRouter();
    await router.push("/admin/cts/live");
    expect(router.currentRoute.value.fullPath).toBe("/admin/tracking?panel=live-floor");
  });

  it("/admin/cts/floor-plan redirects to /admin/tracking with panel=live-floor", async () => {
    const router = makeRouter();
    await router.push("/admin/cts/floor-plan");
    expect(router.currentRoute.value.fullPath).toBe("/admin/tracking?panel=live-floor");
  });

  it("/admin/cts/people redirects to /admin/tracking with panel=people", async () => {
    const router = makeRouter();
    await router.push("/admin/cts/people");
    expect(router.currentRoute.value.fullPath).toBe("/admin/tracking?panel=people");
  });

  it("/admin/cts/presence redirects to /admin/tracking with panel=presence-timeline", async () => {
    const router = makeRouter();
    await router.push("/admin/cts/presence");
    expect(router.currentRoute.value.fullPath).toBe("/admin/tracking?panel=presence-timeline");
  });

  it("/admin/cts/signals redirects to /admin/tracking with panel=signals", async () => {
    const router = makeRouter();
    await router.push("/admin/cts/signals");
    expect(router.currentRoute.value.fullPath).toBe("/admin/tracking?panel=signals");
  });

  it("/admin/medical/signals redirects to /admin/tracking with panel=signals", async () => {
    const router = makeRouter();
    await router.push("/admin/medical/signals");
    expect(router.currentRoute.value.fullPath).toBe("/admin/tracking?panel=signals");
  });

  it("/admin/medical/reports/weekly redirects to /admin/tracking with panel=reports and period=week", async () => {
    const router = makeRouter();
    await router.push("/admin/medical/reports/weekly");
    const q = router.currentRoute.value.query;
    expect(router.currentRoute.value.path).toBe("/admin/tracking");
    expect(q.panel).toBe("reports");
    expect(q.period).toBe("week");
  });

  it("/admin/caregiver/presence/:personId redirects to /admin/tracking with panel=presence-timeline and person param", async () => {
    const router = makeRouter();
    await router.push("/admin/caregiver/presence/alice-123");
    const q = router.currentRoute.value.query;
    expect(router.currentRoute.value.path).toBe("/admin/tracking");
    expect(q.panel).toBe("presence-timeline");
    expect(q.person).toBe("alice-123");
  });

  it("/admin/tracking resolves to TrackingWorkspace component (not a redirect)", async () => {
    const router = makeRouter();
    await router.push("/admin/tracking");
    expect(router.currentRoute.value.name).toBe("tracking-workspace");
    expect(router.currentRoute.value.matched[1].components.default).toBeDefined();
  });
});
