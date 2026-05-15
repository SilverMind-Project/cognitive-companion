/**
 * CTS Live View WebSocket with automatic reconnection.
 *
 * Replaces the ad-hoc WebSocket lifecycle in CTSLiveView.vue that had no
 * reconnection logic. Uses 3-second exponential backoff on disconnect.
 *
 * Usage:
 *   const { status, disconnect } = useCtsWebSocket(onMessage);
 */

import { ref, onUnmounted } from "vue";
import { cts } from "@/services/cts";

export function useCtsWebSocket(onMessage) {
  const status = ref("disconnected");
  let ws = null;
  let reconnectTimer = null;
  let closed = false;

  function connect() {
    if (closed) return;
    console.debug("[cts_live] WS connecting");
    status.value = "connecting";

    ws = cts.openLiveSocket(onMessage);
    ws.onopen = () => {
      console.debug("[cts_live] WS connected");
      status.value = "open";
    };
    ws.onerror = (ev) => {
      console.warn("[cts_live] WS error", ev);
      status.value = "error";
    };
    ws.onclose = (ev) => {
      console.debug("[cts_live] WS closed", { code: ev.code, reason: ev.reason, will_reconnect: !closed });
      status.value = "closed";
      ws = null;
      if (!closed) {
        reconnectTimer = setTimeout(connect, 3000);
      }
    };
  }

  function disconnect() {
    closed = true;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    if (ws) ws.close();
  }

  onUnmounted(disconnect);
  connect();

  return { status, disconnect };
}
