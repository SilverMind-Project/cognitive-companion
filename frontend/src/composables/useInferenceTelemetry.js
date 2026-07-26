import { reactive } from "vue";
import { getInferenceTelemetry } from "@/services/modules/admin";

/**
 * LLM admission-controller telemetry: queue depth, wait percentiles, and
 * calls per caller/lane (DL-M09).
 *
 * Polling, if the caller wants it, is the caller's responsibility
 * (e.g. `setInterval(actions.refresh, ...)` in the mounting view).
 */
export function useInferenceTelemetry() {
  const state = reactive({
    loading: false,
    error: null,
    telemetry: null,
  });

  async function refresh() {
    state.loading = true;
    state.error = null;
    try {
      state.telemetry = await getInferenceTelemetry();
    } catch (err) {
      state.error = err?.message || String(err);
      state.telemetry = null;
    } finally {
      state.loading = false;
    }
  }

  return {
    state,
    actions: { refresh },
  };
}
