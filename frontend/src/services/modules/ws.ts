/**
 * WebSocket helpers.
 *
 * Auth uses the Sec-WebSocket-Protocol subprotocol rather than a query parameter, so the key
 * never lands in access logs or browser history. Same pattern as `cts.openLiveSocket`.
 * Components never construct a WebSocket directly.
 */

import { getApiKey } from "@/services/http";

/**
 * Open a connection to /ws/pipeline for live pipeline events.
 *
 * @param onMessage Called with each parsed event. Malformed frames are ignored rather than
 *   thrown: a single bad frame must not tear down a live console.
 */
export function openPipelineSocket(onMessage: (data: unknown) => void): WebSocket {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const key = getApiKey();
  const ws = new WebSocket(`${proto}//${window.location.host}/ws/pipeline`, key ? [key] : undefined);
  ws.onmessage = (ev: MessageEvent) => {
    try {
      onMessage(JSON.parse(ev.data));
    } catch {
      // ignore malformed messages
    }
  };
  return ws;
}
