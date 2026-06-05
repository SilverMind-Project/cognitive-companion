/**
 * useMaraudersMode composable — singleton state tests.
 *
 * Each test uses vi.resetModules() so the module-level singleton is re-created
 * fresh. The module is dynamically imported AFTER vi.doMock("vuetify") so the
 * mock is in place when useTheme() is first called from setup context.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

describe("useMaraudersMode", () => {
  let mockThemeName;

  beforeEach(() => {
    vi.resetModules();
    localStorage.clear();
    mockThemeName = { value: "ccDark" };
    vi.doMock("vuetify", () => ({
      useTheme: () => ({ global: { name: mockThemeName } }),
    }));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("enable() sets theme to ccMarauders and writes cc_marauders=1", async () => {
    const { useMaraudersMode } = await import("@/composables/useMaraudersMode.js");
    const { state, actions } = useMaraudersMode();

    actions.enable();

    expect(mockThemeName.value).toBe("ccMarauders");
    expect(state.enabled).toBe(true);
    expect(localStorage.getItem("cc_marauders")).toBe("1");
  });

  it("disable() after enable() restores the prior theme name", async () => {
    mockThemeName.value = "ccLight";
    const { useMaraudersMode } = await import("@/composables/useMaraudersMode.js");
    const { state, actions } = useMaraudersMode();

    actions.enable();
    expect(mockThemeName.value).toBe("ccMarauders");

    actions.disable();
    expect(mockThemeName.value).toBe("ccLight");
    expect(state.enabled).toBe(false);
    expect(localStorage.getItem("cc_marauders")).toBe("0");
  });

  it("restore: ccLight start, enable, then disable returns to ccLight (not ccDark)", async () => {
    mockThemeName.value = "ccLight";
    const { useMaraudersMode } = await import("@/composables/useMaraudersMode.js");
    const { actions } = useMaraudersMode();

    actions.enable();
    actions.disable();

    expect(mockThemeName.value).toBe("ccLight");
  });

  it("persistence: when cc_marauders=1, init applies ccMarauders and captures priorTheme", async () => {
    localStorage.setItem("cc_marauders", "1");
    mockThemeName.value = "ccDark";
    const { useMaraudersMode } = await import("@/composables/useMaraudersMode.js");
    const { state, actions } = useMaraudersMode();

    expect(state.enabled).toBe(true);
    expect(mockThemeName.value).toBe("ccMarauders");

    // Disable should restore to the theme that was active before the init apply
    actions.disable();
    expect(mockThemeName.value).toBe("ccDark");
  });

  it("cc_theme key is never written by enable() or disable()", async () => {
    const { useMaraudersMode } = await import("@/composables/useMaraudersMode.js");
    const { actions } = useMaraudersMode();

    localStorage.removeItem("cc_theme");
    actions.enable();
    expect(localStorage.getItem("cc_theme")).toBeNull();

    actions.disable();
    expect(localStorage.getItem("cc_theme")).toBeNull();
  });

  it("reducedMotion reflects matchMedia.matches and updates on change event", async () => {
    const listeners = {};
    vi.stubGlobal("matchMedia", (query) => ({
      matches: query.includes("reduce"),
      addEventListener: (type, fn) => { listeners[type] = fn; },
      removeEventListener: vi.fn(),
    }));

    const { useMaraudersMode } = await import("@/composables/useMaraudersMode.js");
    const { state } = useMaraudersMode();

    expect(state.reducedMotion).toBe(true);

    listeners["change"]?.({ matches: false });
    expect(state.reducedMotion).toBe(false);

    vi.unstubAllGlobals();
  });

  it("singleton: two useMaraudersMode() calls share the same state object", async () => {
    const { useMaraudersMode } = await import("@/composables/useMaraudersMode.js");
    const r1 = useMaraudersMode();
    const r2 = useMaraudersMode();

    expect(r1.state).toBe(r2.state);

    r1.actions.enable();
    expect(r2.state.enabled).toBe(true);
  });

  it("toggle() flips enabled from false to true", async () => {
    const { useMaraudersMode } = await import("@/composables/useMaraudersMode.js");
    const { state, actions } = useMaraudersMode();

    expect(state.enabled).toBe(false);
    actions.toggle();
    expect(state.enabled).toBe(true);
    actions.toggle();
    expect(state.enabled).toBe(false);
  });
});
