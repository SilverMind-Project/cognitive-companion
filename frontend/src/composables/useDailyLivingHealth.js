import { reactive } from "vue";
import { getDailyLivingHealth } from "@/services/modules/admin";

/**
 * Semantic-memory write recency + activity-ledger population (DL-M01).
 *
 * Polling, if the caller wants it, is the caller's responsibility
 * (e.g. `setInterval(actions.refresh, ...)` in the mounting view).
 */
export function useDailyLivingHealth() {
  const state = reactive({
    loading: false,
    error: null,
    health: null,
  });

  async function refresh() {
    state.loading = true;
    state.error = null;
    try {
      state.health = await getDailyLivingHealth();
    } catch (err) {
      state.error = err?.message || String(err);
      state.health = null;
    } finally {
      state.loading = false;
    }
  }

  return {
    state,
    actions: { refresh },
  };
}
