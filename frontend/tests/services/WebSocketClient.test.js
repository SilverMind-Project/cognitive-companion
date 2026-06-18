import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

describe("WebSocketClient", () => {
  let originalWebSocket;
  let sockets;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.resetModules();
    sockets = [];
    originalWebSocket = globalThis.WebSocket;
    globalThis.WebSocket = class FakeWebSocket {
      static OPEN = 1;

      constructor(url) {
        this.url = url;
        this.readyState = 0;
        sockets.push(this);
      }

      close() {
        this.onclose?.({ code: 1000, reason: "closed" });
      }

      send() {}
    };
  });

  afterEach(() => {
    globalThis.WebSocket = originalWebSocket;
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("auto-reconnects with exponential backoff", async () => {
    const { WebSocketClient } = await import("@/services/WebSocketClient.js");
    const client = new WebSocketClient("ws://example.test/audio");
    client.reconnectInterval = 1000;

    client.connect();
    sockets[0].onclose({ code: 1006, reason: "drop" });

    vi.advanceTimersByTime(999);
    expect(sockets).toHaveLength(1);

    vi.advanceTimersByTime(1);
    expect(sockets).toHaveLength(2);

    sockets[1].onclose({ code: 1006, reason: "drop" });
    vi.advanceTimersByTime(1999);
    expect(sockets).toHaveLength(2);

    vi.advanceTimersByTime(1);
    expect(sockets).toHaveLength(3);
  });
});
