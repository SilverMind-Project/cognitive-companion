/**
 * Composable for polling the unified PersonLocationService (M4).
 *
 * Polls GET /api/v1/rooms/{id}/occupants on a configurable interval and
 * merges WebSocket presence_segment_changed pushes for low-latency updates.
 *
 * @module usePersonLocation
 *
 * @example
 *   const { occupants, refresh } = useOccupants(rooms, { pollMs: 5000 });
 *   // occupants.value is { [roomId]: CurrentLocation[] }
 */

import { ref, onMounted, onBeforeUnmount } from "vue";
import { request } from "@/services/api";
import { useCtsWebSocket } from "@/composables/useCtsWebSocket";

/**
 * @param {import("vue").Ref<Array<{id: string}>>} rooms - List of rooms to fetch occupants for.
 * @param {{ pollMs?: number }} [opts]
 * @returns {{ occupants: import("vue").Ref<Record<string, Array>>, refresh: () => Promise<void> }}
 */
export function useOccupants(rooms, { pollMs = 5000 } = {}) {
  /** @type {import("vue").Ref<Record<string, Array>>} */
  const occupants = ref({});
  let timer = null;

  async function refresh() {
    const out = {};
    for (const r of rooms.value) {
      try {
        const resp = await request(`/rooms/${r.id}/occupants`, {
          contract: "rooms.occupants",
        });
        out[r.id] = resp.occupants || [];
      } catch {
        // Silently keep the previous value for transient failures.
        out[r.id] = occupants.value[r.id] || [];
      }
    }
    occupants.value = out;
  }

  // Merge real-time WebSocket pushes for low-latency updates between polls.
  useCtsWebSocket((msg) => {
    if (msg?.type === "presence_segment_changed" && msg.room_id) {
      const list = [...(occupants.value[msg.room_id] || [])];
      const idx = list.findIndex((o) => o.person_id === msg.person_id);
      if (msg.exited) {
        if (idx >= 0) list.splice(idx, 1);
      } else {
        const entry = {
          person_id: msg.person_id,
          room_id: msg.room_id,
          room_name: msg.room_name || "",
          since: msg.since,
          entry_source: msg.entry_source || "observed",
          confidence: msg.confidence || 0.5,
          is_inferred: msg.is_inferred || false,
        };
        if (idx >= 0) {
          list[idx] = entry;
        } else {
          list.push(entry);
        }
      }
      occupants.value = { ...occupants.value, [msg.room_id]: list };
    }
  });

  onMounted(() => {
    refresh();
    timer = setInterval(refresh, pollMs);
  });

  onBeforeUnmount(() => {
    if (timer) clearInterval(timer);
  });

  return { occupants, refresh };
}
