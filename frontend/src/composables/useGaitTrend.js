/**
 * useGaitTrend — fetch and expose gait mobility trend data for one resident.
 *
 * Follows the {state, actions} composable shape (front-end skill).
 * Data ownership: this composable is the single fetch owner for gait trend data.
 * MobilityPanel consumes it; it must not independently call cts.getGaitTrend().
 */
import { reactive } from "vue";
import { cts } from "@/services/cts.js";

export function useGaitTrend() {
  const state = reactive({
    personId: null,
    envelope: null,   // GaitTrendEnvelope | null
    loading: false,
    error: null,
  });

  async function fetch(personId, days = 56) {
    if (!personId) return;
    state.personId = personId;
    state.loading = true;
    state.error = null;
    try {
      state.envelope = await cts.getGaitTrend(personId, days);
    } catch (e) {
      state.error = e.message || "Failed to load mobility trend";
      state.envelope = null;
    } finally {
      state.loading = false;
    }
  }

  return { state, actions: { fetch } };
}
