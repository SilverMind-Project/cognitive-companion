import { onUnmounted, reactive, watch } from "vue";
import { api } from "@/services/api.js";

export const AGGREGATOR_HISTORY_LIMIT = 20;
export const AGGREGATOR_REFRESH_SECONDS = 15;

export function useAggregatorState() {
  const state = reactive({
    items: [],
    total: 0,
    loading: false,
    error: null,
    page: 1,
    itemsPerPage: 25,
    filters: {
      origin: null,
      query: "",
      roomName: null,
    },
    autoRefresh: false,
    history: new Map(),
    roomNames: [],
  });

  let refreshTimer = null;

  function fetchParams() {
    const params = {
      limit: state.itemsPerPage,
      offset: (state.page - 1) * state.itemsPerPage,
    };
    if (state.filters.origin) params.origin = state.filters.origin;
    if (state.filters.query) params.q = state.filters.query;
    if (state.filters.roomName) params.room_name = state.filters.roomName;
    return params;
  }

  function appendHistory(items) {
    const capturedAt = Date.now();
    for (const item of items) {
      const points = state.history.get(item.camera_id) ?? [];
      points.push({ t: capturedAt, depth: item.buffer_depth });
      if (points.length > AGGREGATOR_HISTORY_LIMIT) {
        points.splice(0, points.length - AGGREGATOR_HISTORY_LIMIT);
      }
      state.history.set(item.camera_id, points);
    }
  }

  function collectRooms(items) {
    const rooms = new Set(state.roomNames);
    for (const item of items) {
      if (item.room_name) rooms.add(item.room_name);
    }
    state.roomNames = [...rooms].sort((a, b) => a.localeCompare(b));
  }

  async function fetch() {
    state.loading = true;
    state.error = null;
    try {
      const response = await api.getAggregatorState(fetchParams());
      state.items = response.items;
      state.total = response.total;
      appendHistory(response.items);
      collectRooms(response.items);
    } catch (error) {
      state.error = error?.message || "Failed to load aggregator state";
      state.items = [];
      state.total = 0;
    } finally {
      state.loading = false;
    }
  }

  async function onPageOptions({ page, itemsPerPage }) {
    if (itemsPerPage !== state.itemsPerPage) {
      state.itemsPerPage = itemsPerPage;
      state.page = 1;
    } else {
      state.page = page;
    }
    await fetch();
  }

  async function setFilter(name, value) {
    state.filters[name] = value;
    state.page = 1;
    await fetch();
  }

  function stopAutoRefresh() {
    if (refreshTimer !== null) {
      clearInterval(refreshTimer);
      refreshTimer = null;
    }
  }

  function startAutoRefresh() {
    stopAutoRefresh();
    refreshTimer = setInterval(fetch, AGGREGATOR_REFRESH_SECONDS * 1000);
  }

  watch(
    () => state.autoRefresh,
    (enabled) => {
      if (enabled) startAutoRefresh();
      else stopAutoRefresh();
    },
  );

  onUnmounted(stopAutoRefresh);

  return {
    state,
    actions: {
      fetch,
      onPageOptions,
      setFilter,
      startAutoRefresh,
      stopAutoRefresh,
    },
  };
}
