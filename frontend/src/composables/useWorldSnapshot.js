/**
 * N4: World snapshot composable — subscribes to cts_world_snapshot WS events.
 *
 * Usage:
 *   const { phs, inferredRooms, lastUpdate, isStale, trailBuffers } = useWorldSnapshot();
 */

import { ref, shallowRef, reactive, onUnmounted } from "vue";
import { useCtsWebSocket } from "@/composables/useCtsWebSocket";

const STALE_THRESHOLD_MS = 2000;
const TRAIL_DURATION_MS = 30_000;

export function useWorldSnapshot() {
  const phs = shallowRef([]);
  const inferredRooms = shallowRef([]);
  const lastUpdate = ref(0);
  const isStale = ref(true);
  const trailBuffers = reactive(new Map());

  let staleTimer = null;

  function _updateTrails(newPhs) {
    const now = Date.now();
    const cutoff = now - TRAIL_DURATION_MS;
    const activePHIds = new Set(newPhs.map((p) => p.ph_id));

    for (const ph of newPhs) {
      if (ph.floor_xy_m == null) continue;
      const [x, y] = ph.floor_xy_m;
      if (!trailBuffers.has(ph.ph_id)) {
        trailBuffers.set(ph.ph_id, []);
      }
      const buf = trailBuffers.get(ph.ph_id);
      buf.push({ x, y, t: now });
      let i = 0;
      while (i < buf.length && buf[i].t < cutoff) i++;
      if (i > 0) buf.splice(0, i);
    }

    for (const id of trailBuffers.keys()) {
      if (!activePHIds.has(id)) trailBuffers.delete(id);
    }
  }

  function onMessage(raw) {
    try {
      const event =
        typeof raw === "string" ? JSON.parse(raw) : raw.data ? JSON.parse(raw.data) : raw;
      if (event.type === "cts_world_snapshot") {
        const newPhs = event.phs || [];
        phs.value = newPhs;
        inferredRooms.value = event.inferred_rooms || [];
        lastUpdate.value = Date.now();
        isStale.value = false;
        _updateTrails(newPhs);
        if (staleTimer) clearTimeout(staleTimer);
        staleTimer = setTimeout(() => {
          isStale.value = Date.now() - lastUpdate.value > STALE_THRESHOLD_MS;
        }, STALE_THRESHOLD_MS + 100);
      }
    } catch {
      /* ignore malformed */
    }
  }

  const { status } = useCtsWebSocket(onMessage);

  onUnmounted(() => {
    if (staleTimer) clearTimeout(staleTimer);
  });

  return { phs, inferredRooms, lastUpdate, isStale, wsStatus: status, trailBuffers };
}
