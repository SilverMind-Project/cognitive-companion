/**
 * useMaraudersMode — public API over the `ui` Pinia store (M18).
 *
 * The state itself lives in the store; this composable exists because `useTheme()` must run in a
 * setup context. It acquires the Vuetify theme binding on the first component that uses it and
 * hands it to the store's `init(theme)`, which is idempotent.
 *
 * The returned `{ state, actions }` shape is unchanged: `state` is a reactive view of the store
 * (consumers read `state.enabled` / `state.reducedMotion`), and `actions` keeps
 * enable/disable/toggle.
 */

import { computed, reactive } from "vue";
import { useTheme } from "vuetify";

import { useUiStore } from "@/stores/ui";

export function useMaraudersMode() {
  const ui = useUiStore();
  ui.init(useTheme());

  const state = reactive({
    enabled: computed(() => ui.maraudersEnabled),
    reducedMotion: computed(() => ui.reducedMotion),
  });

  const actions = {
    enable: () => ui.enable(),
    disable: () => ui.disable(),
    toggle: () => ui.toggle(),
  };

  return { state, actions };
}
