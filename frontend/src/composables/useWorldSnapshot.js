/**
 * N4: World snapshot composable — subscribes to cts_world_snapshot WS events.
 *
 * Usage:
 *   const { phs, inferredRooms, lastUpdate, isStale } = useWorldSnapshot(onMessage);
 */

import { ref, shallowRef, onUnmounted } from "vue";
import { useCtsWebSocket } from "@/composables/useCtsWebSocket";

const STALE_THRESHOLD_MS = 2000;

export function useWorldSnapshot() {
  const phs = shallowRef([]);
  const inferredRooms = shallowRef([]);
  const lastUpdate = ref(0);
  const isStale = ref(true);

  let staleTimer = null;

  function checkStale() {
    isStale.value = Date.now() - lastUpdate.value > STALE_THRESHOLD_MS;
  }

  function onMessage(raw) {
    try {
      const event = JSON.parse(raw.data || raw);
      if (event.type === "cts_world_snapshot") {
        phs.value = event.phs || [];
        inferredRooms.value = event.inferred_rooms || [];
        lastUpdate.value = Date.now();
        isStale.value = false;
        if (staleTimer) clearTimeout(staleTimer);
        staleTimer = setTimeout(checkStale, STALE_THRESHOLD_MS + 100);
      }
    } catch {
      /* ignore malformed */
    }
  }

  const { status } = useCtsWebSocket(onMessage);

  onUnmounted(() => {
    if (staleTimer) clearTimeout(staleTimer);
  });

  return { phs, inferredRooms, lastUpdate, isStale, wsStatus: status };
}
