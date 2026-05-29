/**
 * N5: Presence timeline composable.
 *
 * Fetches timeline segments, dwell totals, and current-location HUD data
 * for a given household member. Subscribes to WS for live updates.
 *
 * U4: raw fetch replaced with cts service (rule 17).
 */

import { ref, shallowRef, onUnmounted } from "vue";
import { cts } from "@/services/cts.js";

export function usePresenceTimeline(notify) {
  const personId = ref("");
  const segments = shallowRef([]);
  const dwells = shallowRef([]);
  const currentLocation = ref(null);
  const loading = ref(false);
  const error = ref("");
  const activeDuration = ref(0);
  let timerInterval = null;

  function _startLiveTimer() {
    if (timerInterval) clearInterval(timerInterval);
    timerInterval = setInterval(() => {
      const active = segments.value.find((s) => !s.exited_at);
      if (active && active.entered_at) {
        activeDuration.value = Math.floor(
          (Date.now() - new Date(active.entered_at).getTime()) / 1000
        );
      }
    }, 1000);
  }

  async function fetch(personId_) {
    personId.value = personId_;
    loading.value = true;
    error.value = "";
    try {
      const [timeline, dwellsData, currentData] = await Promise.all([
        cts.getPresenceTimeline(personId_),
        cts.getPresenceDwells(personId_),
        cts.getCurrentlyIn(),
      ]);
      segments.value = timeline.segments || [];
      dwells.value = dwellsData.dwells || [];
      currentLocation.value =
        (currentData.occupants || []).find((o) => o.person_id === personId_) || null;
      _startLiveTimer();
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

  onUnmounted(() => {
    if (timerInterval) clearInterval(timerInterval);
  });

  return {
    personId,
    segments,
    dwells,
    currentLocation,
    loading,
    error,
    activeDuration,
    fetch,
    handleWsEvent,
  };
}
