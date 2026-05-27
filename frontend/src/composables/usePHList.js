/**
 * N3: PH list composable — pagination, filters, and WebSocket merge.
 *
 * Usage:
 *   const { items, total, loading, error, fetch, handleWsEvent } = usePHList();
 */

import { ref, reactive } from "vue";
import { ctsPh } from "@/services/cts_ph";

export function usePHList() {
  const items = ref([]);
  const total = ref(0);
  const loading = ref(false);
  const error = ref("");
  const newSinceRefresh = ref(0);

  const filters = reactive({
    identity_id: null,
    room_id: null,
    since: null,
  });

  const pagination = reactive({
    page: 1,
    itemsPerPage: 25,
  });

  async function fetch() {
    loading.value = true;
    error.value = "";
    try {
      const params = {
        limit: pagination.itemsPerPage,
        offset: (pagination.page - 1) * pagination.itemsPerPage,
      };
      if (filters.identity_id) params.identity_id = filters.identity_id;
      if (filters.room_id) params.room_id = filters.room_id;
      if (filters.since) params.since = filters.since;

      const data = await ctsPh.list(params);
      items.value = data.items || [];
      total.value = data.total || 0;
    } catch (err) {
      error.value = String(err.message || err);
    } finally {
      loading.value = false;
    }
  }

  function updateRowInPlace(phId, updates) {
    const idx = items.value.findIndex((it) => it.ph_id === phId);
    if (idx >= 0) {
      items.value[idx] = { ...items.value[idx], ...updates };
    } else {
      newSinceRefresh.value++;
    }
  }

  function handleWsEvent(event) {
    if (event.type === "cts_ph_update") {
      updateRowInPlace(event.ph_id, {
        current_identity_id: event.current_identity_id,
        last_seen_at: event.last_observed_at,
      });
    } else if (event.type === "cts_ph_correction") {
      // Refresh the affected row
      ctsPh.get(event.ph_id).then((ph) => updateRowInPlace(event.ph_id, ph)).catch(() => {});
    }
  }

  return {
    items,
    total,
    loading,
    error,
    filters,
    pagination,
    newSinceRefresh,
    fetch,
    updateRowInPlace,
    handleWsEvent,
  };
}
