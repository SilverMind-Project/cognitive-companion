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

  it("routes guided-task messages and sends a tap with the step on screen", async () => {
    const { WebSocketClient } = await import("@/services/WebSocketClient.js");
    const client = new WebSocketClient("ws://example.test/audio");
    const states = [];
    const results = [];
    const status = [];
    client.on("onGuidedSessionState", (d) => states.push(d));
    client.on("onGuidedStepActionResult", (d) => results.push(d));
    client.on("onStatus", (d) => status.push(d));
    client.connect();
    const socket = sockets[0];
    socket.readyState = 1;
    const sent = [];
    socket.send = (payload) => sent.push(JSON.parse(payload));

    socket.onmessage({ data: JSON.stringify({ type: "guided_session_state", session_id: 4 }) });
    socket.onmessage({
      data: JSON.stringify({ type: "guided_step_action_result", session_id: 4, accepted: true }),
    });
    // Quiz dismissal keeps arriving through onStatus, where QuizDialog listens.
    socket.onmessage({ data: JSON.stringify({ type: "quiz_timeout", session_id: 9 }) });
    client.sendGuidedStepAction(4, "done", 2);

    expect(states.map((d) => d.session_id)).toEqual([4]);
    expect(results.map((d) => d.accepted)).toEqual([true]);
    expect(status.map((d) => d.type)).toEqual(["quiz_timeout"]);
    expect(sent).toEqual([
      { type: "guided_step_action", session_id: 4, action: "done", step_ord: 2 },
    ]);
  });
});
