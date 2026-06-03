import { reactive } from "vue";
import { api } from "@/services/api.js";

export function useHeatmap() {
  const state = reactive({
    data: null,
    loading: false,
    error: null,
  });

  async function fetchHeatmap(personId, startDate, endDate, startHour, endHour) {
    state.loading = true;
    state.error = null;
    try {
      state.data = await api.getHeatmap({
        person_id: personId,
        start_time: startDate,
        end_time: endDate,
        start_hour: startHour,
        end_hour: endHour,
      });
    } catch (err) {
      state.error = err.message || String(err);
    } finally {
      state.loading = false;
    }
  }

  return { state, actions: { fetchHeatmap } };
}
