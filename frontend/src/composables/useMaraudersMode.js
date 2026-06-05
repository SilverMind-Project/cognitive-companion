import { reactive } from "vue";
import { useTheme } from "vuetify";

// Module-level singleton: one shared state for the lifetime of the app.
const state = reactive({ enabled: false, reducedMotion: false });

let _priorTheme = null; // theme name captured before switching to ccMarauders
let _theme = null;      // cached Vuetify theme binding (acquired from setup context once)
let _initialized = false;

function _initOnce() {
  if (_initialized) return;
  _initialized = true;

  if (typeof window !== "undefined" && window.matchMedia) {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    state.reducedMotion = mq.matches;
    mq.addEventListener("change", (e) => {
      state.reducedMotion = e.matches;
    });
  }

  if (localStorage.getItem("cc_marauders") === "1") {
    // Capture the real theme (cc_theme) as the restore target. If for some
    // reason the current name is already ccMarauders (stale state), fall back
    // to the cc_theme key so toggle-off still restores the correct theme.
    _priorTheme = _theme.global.name.value;
    if (_priorTheme === "ccMarauders") {
      _priorTheme = localStorage.getItem("cc_theme") || "ccDark";
    }
    state.enabled = true;
    _theme.global.name.value = "ccMarauders";
  }
}

export function useMaraudersMode() {
  // useTheme() must run inside a Vue setup() context. We call it on the first
  // component that uses this composable and cache the result at module level
  // so subsequent calls (from other components) skip the inject() call.
  if (!_theme) {
    _theme = useTheme();
  }

  _initOnce();

  const actions = {
    enable() {
      if (state.enabled) return;
      _priorTheme = _theme.global.name.value;
      if (_priorTheme === "ccMarauders") {
        _priorTheme = localStorage.getItem("cc_theme") || "ccDark";
      }
      state.enabled = true;
      _theme.global.name.value = "ccMarauders";
      localStorage.setItem("cc_marauders", "1");
    },

    disable() {
      if (!state.enabled) return;
      state.enabled = false;
      _theme.global.name.value =
        _priorTheme || localStorage.getItem("cc_theme") || "ccDark";
      localStorage.setItem("cc_marauders", "0");
    },

    toggle() {
      if (state.enabled) actions.disable();
      else actions.enable();
    },
  };

  return { state, actions };
}
