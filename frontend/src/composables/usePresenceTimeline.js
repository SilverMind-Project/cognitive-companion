/**
 * N5: Presence timeline composable.
 *
 * Fetches timeline segments, dwell totals, and current-location HUD data
 * for a given household member. Subscribes to WS for live updates.
 */

import { ref, shallowRef, watch } from "vue";

const BASE = "/api/v1/cts";

async function req(path) {
  const apiKey = localStorage.getItem("cc_api_key") || "";
  const headers = { "X-API-Key": apiKey };
  const resp = await fetch(`${BASE}${path}`, { headers });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export function usePresenceTimeline(notify) {
  const personId = ref("");
  const segments = shallowRef([]);
  const dwells = shallowRef([]);
  const currentLocation = ref(null);
  const loading = ref(false);
  const error = ref("");

  async function fetch(personId_) {
    personId.value = personId_;
    loading.value = true;
    error.value = "";
    try {
      const [timeline, dwellsData, currentData] = await Promise.all([
        req(`/presence/timeline/${encodeURIComponent(personId_)}`),
        req(`/presence/dwells/${encodeURIComponent(personId_)}`),
        req("/presence/currently_in"),
      ]);
      segments.value = timeline.segments || [];
      dwells.value = dwellsData.dwells || [];
      currentLocation.value =
        (currentData.occupants || []).find((o) => o.person_id === personId_) || null;
    } catch (err) {
      error.value = String(err.message || err);
      if (notify) notify.error(error.value);
    } finally {
      loading.value = false;
    }
  }

  function handleWsEvent(event) {
    if (event.type === "cts_presence_segment_changed") {
      const seg = event.segment;
      const idx = segments.value.findIndex((s) => s.segment_id === seg.segment_id);
      if (idx >= 0) {
        segments.value[idx] = { ...segments.value[idx], ...seg };
      } else {
        segments.value = [...segments.value, seg];
      }
    } else if (event.type === "cts_ph_update" && event.current_identity_id === personId.value) {
      if (currentLocation.value) {
        currentLocation.value = { ...currentLocation.value, ...event };
      }
    }
  }

  return { personId, segments, dwells, currentLocation, loading, error, fetch, handleWsEvent };
}
