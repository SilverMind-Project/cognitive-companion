/**
 * App-wide UI state: marauders mode and reduced-motion (M18).
 *
 * Ported from the module-level `reactive` singleton in `useMaraudersMode.js`. The composable
 * stays the public API because `useTheme()` must run inside a setup context; it hands the theme
 * binding to `init(theme)` here. The store never calls `useTheme()` itself -- a store action can
 * run from anywhere, and Vuetify's inject would fail outside setup.
 */

import { defineStore } from "pinia";
import { ref, watch } from "vue";

const MARAUDERS_KEY = "cc_marauders";
const THEME_KEY = "cc_theme";
const DEFAULT_THEME = "ccWarm";
const BLUR_KEY = "cts_blur_mode";

/**
 * Blur defaults to ON when unset. This is a privacy default, not a preference default: an
 * operator who has never touched the toggle must not be shown unpixelated faces.
 */
function readBlurMode(): boolean {
  const raw = localStorage.getItem(BLUR_KEY);
  return raw === null ? true : raw === "true";
}

/** The Vuetify theme binding, narrowed to the one property this store drives. */
interface ThemeBinding {
  global: { name: { value: string } };
}

export const useUiStore = defineStore("ui", () => {
  const maraudersEnabled = ref(false);
  const reducedMotion = ref(false);

  /** CTS pixelation, app-wide. Written directly (BlurToggle v-models it), so persistence is a
   *  watcher rather than an action -- same contract the composable had. */
  const blurMode = ref(readBlurMode());
  watch(blurMode, (val) => {
    localStorage.setItem(BLUR_KEY, String(val));
  });

  let theme: ThemeBinding | null = null;
  let priorTheme: string | null = null;
  let initialized = false;

  /** The theme to fall back to when marauders mode is switched off. */
  function restoreTarget(): string {
    return priorTheme || localStorage.getItem(THEME_KEY) || DEFAULT_THEME;
  }

  /** Capture the theme to return to. Guards against a stale ccMarauders being captured as it. */
  function captureTheme(): void {
    const current = theme!.global.name.value;
    priorTheme =
      current === "ccMarauders" ? localStorage.getItem(THEME_KEY) || DEFAULT_THEME : current;
  }

  /**
   * Bind the Vuetify theme and apply persisted state. Idempotent: the first component to use the
   * composable initializes; the rest are no-ops.
   */
  function init(themeBinding: ThemeBinding): void {
    theme ??= themeBinding;
    if (initialized) return;
    initialized = true;

    if (typeof window !== "undefined" && window.matchMedia) {
      const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
      reducedMotion.value = mq.matches;
      mq.addEventListener("change", (e) => {
        reducedMotion.value = e.matches;
      });
    }

    if (localStorage.getItem(MARAUDERS_KEY) === "1") {
      captureTheme();
      maraudersEnabled.value = true;
      theme!.global.name.value = "ccMarauders";
    }
  }

  function enable(): void {
    if (maraudersEnabled.value) return;
    captureTheme();
    maraudersEnabled.value = true;
    theme!.global.name.value = "ccMarauders";
    localStorage.setItem(MARAUDERS_KEY, "1");
  }

  function disable(): void {
    if (!maraudersEnabled.value) return;
    maraudersEnabled.value = false;
    theme!.global.name.value = restoreTarget();
    localStorage.setItem(MARAUDERS_KEY, "0");
  }

  function toggle(): void {
    if (maraudersEnabled.value) disable();
    else enable();
  }

  return { maraudersEnabled, reducedMotion, blurMode, init, enable, disable, toggle };
});
