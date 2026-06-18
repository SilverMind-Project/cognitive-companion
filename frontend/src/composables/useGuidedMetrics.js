import { reactive } from "vue";
import { api } from "@/services/api.js";

export function useGuidedMetrics() {
  const state = reactive({
    routine: null,
    dashboard: null,
    loading: false,
    error: null,
  });

  async function fetchDashboard(routineId) {
    state.loading = true;
    state.error = null;
    try {
      const detail = await api.getRoutine(routineId);
      state.routine = detail.routine;
      state.dashboard = await api.getGuidedMetricsDashboard({
        person_id: detail.routine.person_id,
        routine_id: detail.routine.id,
      });
    } catch (err) {
      state.error = err.message || String(err);
    } finally {
      state.loading = false;
    }
  }

  return {
    state,
    actions: { fetchDashboard },
  };
}
