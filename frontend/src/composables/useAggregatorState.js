import { onUnmounted, reactive, watch } from "vue";
import { api } from "@/services/api.js";

export const AGGREGATOR_HISTORY_LIMIT = 20;
export const AGGREGATOR_REFRESH_SECONDS = 15;
/** Sampling period for the one camera whose depth trend is open. */
export const AGGREGATOR_SAMPLE_SECONDS = 5;
// Samples closer than this carry no trend, so a later one replaces the earlier (the page's
// initial load fetches twice: on mount and on the table's first options event).
const MIN_SAMPLE_GAP_MS = 1000;

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
  let sampleTimer = null;

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
    // ISO, not epoch milliseconds: the chart formats points through services/timezone.js.
    const capturedAt = new Date().toISOString();
    for (const item of items) {
      const points = state.history.get(item.camera_id) ?? [];
      const point = { t: capturedAt, depth: item.buffer_depth };
      const newest = points.at(-1);
      if (newest && Date.parse(capturedAt) - Date.parse(newest.t) < MIN_SAMPLE_GAP_MS) {
        points[points.length - 1] = point;
      } else {
        points.push(point);
      }
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

  /** Record one depth sample for *cameraId* without replacing the paged table rows. */
  async function sampleCamera(cameraId) {
    try {
      const response = await api.getAggregatorState({ camera_id: cameraId, limit: 1 });
      appendHistory(response.items.filter((item) => item.camera_id === cameraId));
    } catch {
      // A missed sample leaves a gap in the trend; the table's own fetch reports the error.
    }
  }

  function stopSampling() {
    if (sampleTimer !== null) {
      clearInterval(sampleTimer);
      sampleTimer = null;
    }
  }

  /**
   * Sample *cameraId* every AGGREGATOR_SAMPLE_SECONDS until stopSampling, starting at once unless
   * the table fetch has just recorded a point (two points in one second read as a flat line).
   */
  function startSampling(cameraId) {
    stopSampling();
    const newest = state.history.get(cameraId)?.at(-1);
    const recent = newest && Date.now() - Date.parse(newest.t) < AGGREGATOR_SAMPLE_SECONDS * 1000;
    if (!recent) sampleCamera(cameraId);
    sampleTimer = setInterval(() => sampleCamera(cameraId), AGGREGATOR_SAMPLE_SECONDS * 1000);
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

  onUnmounted(() => {
    stopAutoRefresh();
    stopSampling();
  });

  return {
    state,
    actions: {
      fetch,
      onPageOptions,
      setFilter,
      startAutoRefresh,
      stopAutoRefresh,
      sampleCamera,
      startSampling,
      stopSampling,
    },
  };
}
