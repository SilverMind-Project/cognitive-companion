import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { useKioskMode } from "@/composables/useKioskMode.js";

function makeStorage(initial = null) {
  let value = initial ? JSON.stringify(initial) : null;
  return {
    getItem: vi.fn(() => value),
    setItem: vi.fn((_key, next) => {
      value = next;
    }),
    read: () => JSON.parse(value),
  };
}

function mountComposable(options = {}) {
  let result;
  const Wrapper = defineComponent({
    setup() {
      result = useKioskMode({
        route: { query: {} },
        apiClient: {
          getRooms: vi.fn().mockResolvedValue([]),
          recordCompanionSurfaceHeartbeat: vi.fn().mockResolvedValue({ status: "ok" }),
        },
        storage: makeStorage(),
        documentRef: { addEventListener: vi.fn(), removeEventListener: vi.fn() },
        ...options,
      });
      return () => h("div");
    },
  });
  const wrapper = mount(Wrapper);
  return { ...result, wrapper };
}

describe("useKioskMode", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(console, "info").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("first tap starts the session and the gate stays dismissed on disconnect", async () => {
    const startSession = vi.fn().mockResolvedValue();
    const { state, actions, wrapper } = mountComposable({ route: { query: { kiosk: "1" } } });

    expect(state.gateVisible).toBe(true);

    await actions.begin(startSession);
    actions.onSocketDisconnect();
    await flushPromises();

    expect(startSession).toHaveBeenCalledOnce();
    expect(state.started).toBe(true);
    expect(state.connected).toBe(false);
    expect(state.gateVisible).toBe(false);
    wrapper.unmount();
  });

  it("re-arms microphone on backend request without showing the gate", async () => {
    const startSession = vi.fn().mockResolvedValue();
    const { state, actions, wrapper } = mountComposable({ route: { query: { kiosk: "1" } } });

    await actions.begin(vi.fn());
    await actions.handleEnableMicrophone(startSession);

    expect(startSession).toHaveBeenCalledOnce();
    expect(state.gateVisible).toBe(false);
    wrapper.unmount();
  });

  it("sends heartbeat immediately and on the configured interval", async () => {
    const apiClient = {
      getRooms: vi.fn().mockResolvedValue([]),
      recordCompanionSurfaceHeartbeat: vi.fn().mockResolvedValue({ status: "ok" }),
    };
    const storage = makeStorage({
      kioskEnabled: true,
      surfaceId: "kitchen-tablet",
      roomId: 7,
      pin: "1234",
    });
    const { wrapper } = mountComposable({ apiClient, storage, heartbeatMs: 1000 });
    await flushPromises();

    expect(apiClient.recordCompanionSurfaceHeartbeat).toHaveBeenCalledWith("kitchen-tablet", {
      reported_room_id: 7,
    });

    vi.advanceTimersByTime(1000);
    await flushPromises();

    expect(apiClient.recordCompanionSurfaceHeartbeat).toHaveBeenCalledTimes(2);
    wrapper.unmount();
  });

  it("acquires and releases wake lock, and degrades when unsupported", async () => {
    const release = vi.fn().mockResolvedValue();
    const wakeLock = { request: vi.fn().mockResolvedValue({ release, addEventListener: vi.fn() }) };
    const { state, actions, wrapper } = mountComposable({
      route: { query: { kiosk: "1" } },
      wakeLock,
    });

    await actions.begin(vi.fn());
    await actions.releaseWakeLock();

    expect(wakeLock.request).toHaveBeenCalledWith("screen");
    expect(release).toHaveBeenCalledOnce();
    expect(state.wakeLockStatus).toBe("released");
    wrapper.unmount();

    const unsupported = mountComposable({ route: { query: { kiosk: "1" } }, wakeLock: null });
    await unsupported.actions.begin(vi.fn());
    expect(unsupported.state.wakeLockStatus).toBe("unsupported");
    unsupported.wrapper.unmount();
  });

  it("gates settings with the local PIN and persists updates", async () => {
    const storage = makeStorage({ kioskEnabled: false, surfaceId: "", roomId: null, pin: "2468" });
    const { state, actions, wrapper } = mountComposable({ storage });

    expect(actions.unlockSettings("0000")).toBe(false);
    expect(actions.unlockSettings("2468")).toBe(true);

    await actions.saveSettings({
      kioskEnabled: true,
      surfaceId: "hall-tablet",
      roomId: "12",
      pin: "1357",
    });

    expect(state.settingsUnlocked).toBe(true);
    expect(storage.read()).toMatchObject({
      kioskEnabled: true,
      surfaceId: "hall-tablet",
      roomId: 12,
      pin: "1357",
    });
    wrapper.unmount();
  });
});
