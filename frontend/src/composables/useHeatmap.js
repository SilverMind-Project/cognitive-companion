import { reactive } from "vue";
import { api } from "@/services/api.js";

export function useHeatmap() {
  const state = reactive({
    data: null,
    loading: false,
    error: null,
  });

  async function fetchHeatmap(personId, startTime, endTime, startMinute, endMinute) {
    state.loading = true;
    state.error = null;
    try {
      state.data = await api.getHeatmap({
        person_id: personId,
        start_time: startTime,
        end_time: endTime,
        start_minute: startMinute,
        end_minute: endMinute,
      });
    } catch (err) {
      state.error = err.message || String(err);
    } finally {
      state.loading = false;
    }
  }

  return { state, actions: { fetchHeatmap } };
}
