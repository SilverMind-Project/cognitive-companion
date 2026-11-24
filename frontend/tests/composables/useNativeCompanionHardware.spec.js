import { beforeEach, describe, expect, it, vi } from "vitest";
import { useNativeCompanionHardware } from "@/composables/useNativeCompanionHardware.js";

const COMMAND = {
  type: "surface_hardware_command",
  surface_id: "kitchen-tablet",
  lease_owner: "guided_task_start:12",
  reason: "guided_task_start",
  wake_screen: true,
  enable_microphone: true,
  enable_camera: true,
  volume_min_pct: 65,
  attention_chime: "gentle",
  lease_seconds: 120,
  server_timestamp: "2026-11-24T09:00:00Z",
};

const RELEASE = {
  ...COMMAND,
  wake_screen: false,
  enable_microphone: false,
  enable_camera: false,
  volume_min_pct: null,
  attention_chime: null,
  lease_seconds: 0,
};

function harness({ native = true, isTelevision = false } = {}) {
  const ws = { handlers: {} };
  ws.on = vi.fn((event, cb) => (ws.handlers[event] = cb));
  ws.off = vi.fn();
  ws.sendSurfaceAttentionState = vi.fn();
  const listeners = {};
  const plugin = {
    applyCommand: vi.fn().mockResolvedValue({ screenAwake: true }),
    getDeviceInfo: vi.fn().mockResolvedValue({ isTelevision }),
    addListener: vi.fn(async (name, cb) => {
      listeners[name] = cb;
      return { remove: vi.fn() };
    }),
  };
  let recording = false;
  const startCapture = vi.fn(() => {
    recording = true;
  });
  const stopCapture = vi.fn(() => {
    recording = false;
  });
  const hardware = useNativeCompanionHardware({
    ws,
    isRecording: () => recording,
    startCapture,
    stopCapture,
    plugin,
    isNative: () => native,
  });
  return {
    ws,
    plugin,
    listeners,
    hardware,
    startCapture,
    stopCapture,
    setRecording: (v) => (recording = v),
  };
}

async function receive(h, command) {
  h.ws.handlers.onSurfaceHardwareCommand(command);
  await vi.waitFor(() => expect(h.plugin.applyCommand.mock.calls.length).toBeGreaterThan(0));
}

describe("useNativeCompanionHardware", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  it("applies surface hardware command and auto starts mic without user gesture", async () => {
    const h = harness();
    await h.hardware.actions.mount();

    await receive(h, COMMAND);

    expect(h.plugin.applyCommand).toHaveBeenCalledWith(COMMAND);
    expect(h.startCapture).toHaveBeenCalledOnce();
    expect(h.hardware.state.micLeased).toBe(true);
    expect(h.hardware.state.cameraActive).toBe(true);
    expect(h.hardware.state.screenAwake).toBe(true);
    expect(h.hardware.state.platform).toBe("android_tablet");
  });

  it("forwards front camera face presence to the websocket", async () => {
    const h = harness();
    await h.hardware.actions.mount();

    h.listeners.facePresenceChanged({ facePresent: true, yaw: -4.2, pitch: 1.5 });

    expect(h.ws.sendSurfaceAttentionState).toHaveBeenCalledWith({
      facePresent: true,
      headYawDeg: -4.2,
      headPitchDeg: 1.5,
    });
  });

  it("closes the microphone when the lease runs out unrenewed, and a renewal extends it", async () => {
    const h = harness();
    await h.hardware.actions.mount();
    await h.hardware.actions.applyCommand(COMMAND);

    await vi.advanceTimersByTimeAsync(100_000);
    await h.hardware.actions.applyCommand(COMMAND);
    await vi.advanceTimersByTimeAsync(100_000);
    expect(h.stopCapture).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(20_000);
    expect(h.stopCapture).toHaveBeenCalledOnce();
    expect(h.hardware.state.micLeased).toBe(false);
    expect(h.hardware.state.cameraActive).toBe(false);
  });

  it("a release stops what the lease started, and never her own recording", async () => {
    const h = harness();
    await h.hardware.actions.mount();
    await h.hardware.actions.applyCommand(COMMAND);
    await h.hardware.actions.applyCommand(RELEASE);
    expect(h.stopCapture).toHaveBeenCalledOnce();

    // She tapped the microphone herself before the quiz began.
    h.setRecording(true);
    await h.hardware.actions.applyCommand(COMMAND);
    await h.hardware.actions.applyCommand(RELEASE);

    expect(h.stopCapture).toHaveBeenCalledOnce();
    expect(h.startCapture).toHaveBeenCalledOnce();
  });

  it("the native lease timer is a backstop for a suspended page", async () => {
    const h = harness();
    await h.hardware.actions.mount();
    await h.hardware.actions.applyCommand(COMMAND);

    h.listeners.leaseExpired({ owners: ["guided_task_start:12"] });
    await vi.advanceTimersByTimeAsync(0);

    expect(h.stopCapture).toHaveBeenCalledOnce();
  });

  it("a browser opens only the microphone and never calls the shell", async () => {
    const h = harness({ native: false });
    await h.hardware.actions.mount();

    await h.hardware.actions.applyCommand(COMMAND);

    expect(h.plugin.applyCommand).not.toHaveBeenCalled();
    expect(h.plugin.getDeviceInfo).not.toHaveBeenCalled();
    expect(h.startCapture).toHaveBeenCalledOnce();
    expect(h.hardware.state.cameraActive).toBe(false);
    expect(h.hardware.actions.deviceState()).toEqual({
      platform: "web",
      mic_active: true,
      camera_active: null,
      screen_awake: null,
    });
  });

  it("reports a TV platform and stops listening on unmount", async () => {
    const h = harness({ isTelevision: true });
    await h.hardware.actions.mount();

    expect(h.hardware.state.isTelevision).toBe(true);
    expect(h.hardware.state.platform).toBe("android_tv");

    h.hardware.actions.unmount();
    expect(h.ws.off).toHaveBeenCalledWith("onSurfaceHardwareCommand", expect.any(Function));
  });

  it("one delivery ending never closes another's microphone", async () => {
    const h = harness();
    await h.hardware.actions.mount();
    const card = {
      ...COMMAND,
      lease_owner: "info_card:4",
      enable_camera: false,
      lease_seconds: 90,
    };
    await h.hardware.actions.applyCommand(COMMAND);
    await h.hardware.actions.applyCommand(card);

    await h.hardware.actions.applyCommand({ ...RELEASE, lease_owner: "info_card:4" });
    await vi.advanceTimersByTimeAsync(100_000);

    expect(h.stopCapture).not.toHaveBeenCalled();
    expect(h.hardware.state.micLeased).toBe(true);

    await h.hardware.actions.applyCommand(RELEASE);
    expect(h.stopCapture).toHaveBeenCalledOnce();
  });

  it("a screen-only command is a lease, not a release", async () => {
    const h = harness();
    await h.hardware.actions.mount();
    await h.hardware.actions.applyCommand(COMMAND);

    await h.hardware.actions.applyCommand({
      ...COMMAND,
      lease_owner: "quiz:9",
      enable_microphone: false,
      enable_camera: false,
      lease_seconds: 630,
    });

    expect(h.stopCapture).not.toHaveBeenCalled();
    expect(h.hardware.state.micLeased).toBe(true);
    expect(h.startCapture).toHaveBeenCalledOnce();
  });

  it("the lease owns the recording even when the shell answers late", async () => {
    // The server's `enable_microphone` arrives right behind the command; on the
    // shell it is handled while the bridge call is still in flight.
    const h = harness();
    await h.hardware.actions.mount();
    let answer;
    h.plugin.applyCommand.mockImplementation(() => new Promise((resolve) => (answer = resolve)));

    const applying = h.hardware.actions.applyCommand(COMMAND);
    if (!h.startCapture.mock.calls.length) h.startCapture(); // the enable_microphone path
    answer({ screenAwake: true });
    await applying;

    h.plugin.applyCommand.mockResolvedValue({ screenAwake: false });
    await h.hardware.actions.applyCommand(RELEASE);

    expect(h.stopCapture).toHaveBeenCalledOnce();
  });
});
