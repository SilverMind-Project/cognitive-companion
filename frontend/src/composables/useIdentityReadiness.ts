/**
 * The identity readiness composable: loads the server's readiness envelope once per call.
 *
 * Used by the identity setup page and, for one step each, by the Face calibration and ReID
 * review pages. It exposes `state.error` instead of notifying, so a view that only shows a hint
 * can ignore a failure while the setup page shows it. A 403 is `state.forbidden`: retrying cannot
 * help.
 *
 * Returns `{ state, actions }` plus read-only `stepByKey` per the front-end skill.
 */

import { computed, reactive } from "vue";
import {
  getIdentityReadiness,
  type IdentityReadiness,
  type ReadinessStep,
} from "@/services/modules/identity_readiness";
import { ApiError } from "@/services/http";

export function useIdentityReadiness() {
  const state = reactive({
    readiness: null as IdentityReadiness | null,
    loading: false,
    error: "",
    forbidden: false,
  });

  const stepByKey = computed(() => {
    const map: Partial<Record<ReadinessStep["key"], ReadinessStep>> = {};
    for (const step of state.readiness?.steps ?? []) map[step.key] = step;
    return map;
  });

  async function load() {
    state.loading = true;
    state.error = "";
    state.forbidden = false;
    try {
      state.readiness = await getIdentityReadiness();
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) state.forbidden = true;
      else state.error = err instanceof Error ? err.message : String(err);
    } finally {
      state.loading = false;
    }
  }

  return { state, stepByKey, actions: { load } };
}
