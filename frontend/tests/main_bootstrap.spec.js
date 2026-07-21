/**
 * Composition-root smoke test.
 *
 * main.js has hidden ordering requirements: Pinia must be installed before any store is touched,
 * the API-key provider must be repointed at the auth store before the first request, and
 * app-info must still resolve before mount so the first paint uses the operator's timezone.
 * Nothing else exercises this file -- the unit suites all mock it away -- so a wrong order here
 * is a white screen that every other test stays green over.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { setActivePinia } from "pinia";

const mocks = vi.hoisted(() => ({
  getAppInfo: vi.fn(),
  initTimezone: vi.fn(),
  setApiKeyProvider: vi.fn(),
}));

vi.mock("@/services/modules/admin", () => ({ getAppInfo: mocks.getAppInfo }));

vi.mock("@/services/timezone.js", async (importOriginal) => ({
  ...(await importOriginal()),
  initTimezone: mocks.initTimezone,
}));

vi.mock("@/services/http", async (importOriginal) => ({
  ...(await importOriginal()),
  setApiKeyProvider: mocks.setApiKeyProvider,
}));

describe("main.js bootstrap", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    localStorage.clear();
    document.body.innerHTML = '<div id="app"></div>';
    // Opt out of the global Pinia from vitest.setup.js. A browser has no ambient active Pinia,
    // and leaving one installed would satisfy a store touched *before* app.use(pinia) -- masking
    // the exact ordering bug this spec exists to catch. Verified: with this line, moving
    // bootstrap() above app.use(pinia) fails the suite; without it, that regression passes.
    setActivePinia(undefined);
    mocks.getAppInfo.mockResolvedValue({
      name: "Cognitive Companion",
      version: "2.0.0",
      timezone: "America/New_York",
      services: {},
    });
  });

  // `import("@/main.js")` cold-loads the whole app entry (router, Pinia, Vuetify,
  // ECharts, vue-flow,...); `deps.server.inline` for Vuetify (see vite.config.js)
  // means that graph is transformed on the fly rather than pre-bundled. That is
  // fast in isolation but can exceed the 5s default test timeout under full-suite
  // parallel CPU contention. The generous timeout here is a concession to that
  // cold-import cost, not a tolerance for a slow assertion.
  const BOOTSTRAP_TIMEOUT_MS = 20000;

  it(
    "mounts, applies the operator timezone, and points the key provider at the auth store",
    async () => {
      await import("@/main.js");
      // bootstrap() is async and self-invoking; let its awaits settle.
      await vi.waitFor(() => expect(mocks.setApiKeyProvider).toHaveBeenCalled());

      expect(mocks.initTimezone).toHaveBeenCalledWith("America/New_York");
      expect(document.querySelector("#app").innerHTML).not.toBe("");

      // The provider must resolve the key from the auth store, not from a stale localStorage read.
      const { setActivePinia, createPinia } = await import("pinia");
      const { useAuthStore } = await import("@/stores/auth");
      const provider = mocks.setApiKeyProvider.mock.calls[0][0];
      setActivePinia(createPinia());
      useAuthStore().setApiKey("from-store");
      expect(provider()).toBe("from-store");
    },
    BOOTSTRAP_TIMEOUT_MS,
  );

  it(
    "still mounts when the backend is unreachable at load",
    async () => {
      mocks.getAppInfo.mockRejectedValue(new Error("ECONNREFUSED"));

      await import("@/main.js");
      await vi.waitFor(() => expect(mocks.setApiKeyProvider).toHaveBeenCalled());

      // A backend that is down must not leave the caregiver looking at a white screen.
      await vi.waitFor(() => expect(document.querySelector("#app").innerHTML).not.toBe(""));
    },
    BOOTSTRAP_TIMEOUT_MS,
  );
});
