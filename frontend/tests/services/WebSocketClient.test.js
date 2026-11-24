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

      constructor(url, protocols) {
        this.url = url;
        this.protocols = protocols;
        this.readyState = 0;
        this.sent = [];
        sockets.push(this);
      }

      close() {
        this.onclose?.({ code: 1000, reason: "closed" });
      }

      send(data) {
        this.sent.push(data);
      }
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

  it("offers the API key as the subprotocol and names its surface in the URL", async () => {
    const { WebSocketClient } = await import("@/services/WebSocketClient.js");
    const client = new WebSocketClient("ws://example.test/ws/audio", {
      keyProvider: () => "tabletkey123",
    });
    client.setSurfaceContext({ surfaceId: " kitchen-tablet ", platform: "android_tablet" });

    client.connect();

    expect(sockets[0].url).toBe(
      "ws://example.test/ws/audio?surface_id=kitchen-tablet&platform=android_tablet",
    );
    expect(sockets[0].protocols).toEqual(["tabletkey123"]);
  });

  it("connects without a subprotocol when no key is configured", async () => {
    const { WebSocketClient } = await import("@/services/WebSocketClient.js");
    const client = new WebSocketClient("ws://example.test/ws/audio", { keyProvider: () => "" });

    client.connect();

    expect(sockets[0].url).toBe("ws://example.test/ws/audio");
    expect(sockets[0].protocols).toBeUndefined();
  });

  it("reconnects once, without a backoff loop, when its surface changes", async () => {
    const { WebSocketClient } = await import("@/services/WebSocketClient.js");
    const client = new WebSocketClient("ws://example.test/ws/audio", { keyProvider: () => "k" });
    client.connect();

    client.setSurfaceContext({ surfaceId: "bedroom-tablet" });
    vi.advanceTimersByTime(60_000);

    expect(sockets).toHaveLength(2);
    expect(sockets[1].url).toBe("ws://example.test/ws/audio?surface_id=bedroom-tablet");
    client.setSurfaceContext({ surfaceId: "bedroom-tablet" });
    expect(sockets).toHaveLength(2);
  });

  it("routes a hardware command and sends an attention reading with no image", async () => {
    const { WebSocketClient } = await import("@/services/WebSocketClient.js");
    const client = new WebSocketClient("ws://example.test/ws/audio", { keyProvider: () => "k" });
    const commands = [];
    client.on("onSurfaceHardwareCommand", (cmd) => commands.push(cmd));
    client.connect();
    sockets[0].readyState = 1;

    sockets[0].onmessage({
      data: JSON.stringify({ type: "surface_hardware_command", enable_microphone: true }),
    });
    client.sendSurfaceAttentionState({ facePresent: true, headYawDeg: -4.2, headPitchDeg: 1.5 });

    expect(commands).toEqual([{ type: "surface_hardware_command", enable_microphone: true }]);
    const sent = JSON.parse(sockets[0].sent[0]);
    expect(sent).toMatchObject({
      type: "surface_attention_state",
      face_present: true,
      head_yaw_deg: -4.2,
      head_pitch_deg: 1.5,
    });
    expect(Object.keys(sent).sort()).toEqual(
      ["face_present", "head_pitch_deg", "head_yaw_deg", "timestamp", "type"].sort(),
    );
  });

  it("a key the browser rejects as a subprotocol leaves the page running", async () => {
    const { WebSocketClient } = await import("@/services/WebSocketClient.js");
    globalThis.WebSocket = class {
      static OPEN = 1;

      constructor() {
        throw new SyntaxError("invalid subprotocol");
      }
    };
    vi.spyOn(console, "error").mockImplementation(() => {});
    const client = new WebSocketClient("ws://example.test/ws/audio", { keyProvider: () => "a/b=" });
    const disconnects = [];
    client.on("onDisconnect", () => disconnects.push(true));

    expect(() => client.connect()).not.toThrow();
    expect(disconnects).toEqual([true]);
    expect(client.isOpen).toBe(false);
  });
});
