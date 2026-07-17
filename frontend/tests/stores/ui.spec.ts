import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";

import { useUiStore } from "@/stores/ui";

function fakeTheme(name = "ccWarm") {
  return { global: { name: { value: name } } };
}

/** Stub matchMedia and hand back the registered change listener. */
function stubReducedMotion(matches: boolean) {
  const listeners: Array<(e: { matches: boolean }) => void> = [];
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({
      matches,
      addEventListener: (_: string, cb: (e: { matches: boolean }) => void) => listeners.push(cb),
      removeEventListener: vi.fn(),
    })),
  );
  return { fire: (m: boolean) => listeners.forEach((cb) => cb({ matches: m })) };
}

describe("ui store — marauders mode", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
    stubReducedMotion(false);
    setActivePinia(createPinia());
  });

  it("enable() switches the theme and persists", () => {
    const theme = fakeTheme("ccWarm");
    const ui = useUiStore();
    ui.init(theme);

    ui.enable();

    expect(ui.maraudersEnabled).toBe(true);
    expect(theme.global.name.value).toBe("ccMarauders");
    expect(localStorage.getItem("cc_marauders")).toBe("1");
  });

  it("disable() restores the theme captured before enabling", () => {
    const theme = fakeTheme("ccWarm");
    const ui = useUiStore();
    ui.init(theme);

    ui.enable();
    ui.disable();

    expect(ui.maraudersEnabled).toBe(false);
    expect(theme.global.name.value).toBe("ccWarm");
    expect(localStorage.getItem("cc_marauders")).toBe("0");
  });

  it("toggle() flips both ways", () => {
    const theme = fakeTheme("ccWarm");
    const ui = useUiStore();
    ui.init(theme);

    ui.toggle();
    expect(ui.maraudersEnabled).toBe(true);
    ui.toggle();
    expect(ui.maraudersEnabled).toBe(false);
    expect(theme.global.name.value).toBe("ccWarm");
  });

  it("init() applies persisted marauders mode", () => {
    localStorage.setItem("cc_marauders", "1");
    const theme = fakeTheme("ccWarm");
    const ui = useUiStore();

    ui.init(theme);

    expect(ui.maraudersEnabled).toBe(true);
    expect(theme.global.name.value).toBe("ccMarauders");
  });

  it("a stale ccMarauders theme name is not captured as the restore target", () => {
    // Guards the case the original composable called out: if the app booted already showing
    // ccMarauders, capturing it as `priorTheme` would make toggle-off a no-op.
    localStorage.setItem("cc_marauders", "1");
    localStorage.setItem("cc_theme", "ccWarm");
    const theme = fakeTheme("ccMarauders");
    const ui = useUiStore();

    ui.init(theme);
    ui.disable();

    expect(theme.global.name.value).toBe("ccWarm");
  });

  it("init() is idempotent across the components that call it", () => {
    const theme = fakeTheme("ccWarm");
    const ui = useUiStore();
    ui.init(theme);
    ui.enable();

    // A second component mounts and initializes again; it must not clobber live state.
    ui.init(fakeTheme("ccWarm"));

    expect(ui.maraudersEnabled).toBe(true);
    expect(theme.global.name.value).toBe("ccMarauders");
  });

  it("blurMode defaults to on when never set (privacy default)", () => {
    expect(useUiStore().blurMode).toBe(true);
  });

  it("blurMode round-trips through localStorage", async () => {
    const ui = useUiStore();
    ui.blurMode = false;
    await nextTick();
    expect(localStorage.getItem("cts_blur_mode")).toBe("false");

    setActivePinia(createPinia());
    expect(useUiStore().blurMode).toBe(false);
  });

  it("seeds reducedMotion from the media query and tracks changes", () => {
    const motion = stubReducedMotion(true);
    setActivePinia(createPinia());
    const ui = useUiStore();
    ui.init(fakeTheme());

    expect(ui.reducedMotion).toBe(true);

    motion.fire(false);
    expect(ui.reducedMotion).toBe(false);
  });
});
