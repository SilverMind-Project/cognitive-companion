/**
 * Kiosk mode — deliberately NOT a Pinia store.
 *
 * Audited during and left as a composable. Unlike blur mode and marauders mode, this state
 * is per-instance, not app-wide: every call builds its own `reactive` from injected
 * dependencies (route, apiClient, storage, wakeLock, document, heartbeat interval), and it owns
 * mount-scoped resources -- a wake lock and a heartbeat timer -- that belong to the gate that
 * mounted it. Two kiosks in one tab would legitimately hold different settings. Hoisting this
 * into a store would force one instance to win and would leak the timer past unmount.
 */

import { computed, onMounted, onUnmounted, reactive, watch } from "vue";
import { api } from "@/services/api.js";

const STORAGE_KEY = "cc_companion_kiosk_settings";
const DEFAULT_PIN = "1234";
const DEFAULT_SETTINGS = {
  kioskEnabled: false,
  surfaceId: "",
  roomId: null,
  pin: DEFAULT_PIN,
};

function readSettings(storage) {
  try {
    const raw = storage?.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_SETTINGS };
    return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

function normalizeRoomId(roomId) {
  if (roomId === "" || roomId == null) return null;
  const parsed = Number(roomId);
  return Number.isFinite(parsed) ? parsed : null;
}

export function useKioskMode({
  route = null,
  apiClient = api,
  storage = globalThis.localStorage,
  wakeLock = globalThis.navigator?.wakeLock,
  documentRef = globalThis.document,
  heartbeatMs = 30000,
} = {}) {
  const stored = readSettings(storage);
  const state = reactive({
    settings: {
      kioskEnabled: Boolean(stored.kioskEnabled),
      surfaceId: stored.surfaceId || "",
      roomId: normalizeRoomId(stored.roomId),
      pin: stored.pin || DEFAULT_PIN,
    },
    started: false,
    connected: false,
    settingsUnlocked: false,
    rooms: [],
    roomsLoading: false,
    heartbeatStatus: "idle",
    heartbeatError: "",
    wakeLockStatus: "idle",
  });

  const routeKiosk = computed(() => route?.query?.kiosk === "1");
  const isActive = computed(() => routeKiosk.value || state.settings.kioskEnabled);
  const gateVisible = computed(() => isActive.value && !state.started);
  state.isActive = isActive;
  state.gateVisible = gateVisible;

  let heartbeatTimer = null;
  let wakeLockSentinel = null;

  function persistSettings() {
    storage?.setItem(STORAGE_KEY, JSON.stringify(state.settings));
  }

  async function loadRooms() {
    state.roomsLoading = true;
    try {
      state.rooms = await apiClient.getRooms();
    } finally {
      state.roomsLoading = false;
    }
  }

  async function sendHeartbeat() {
    if (!isActive.value || !state.settings.surfaceId) return;

    try {
      await apiClient.recordCompanionSurfaceHeartbeat(state.settings.surfaceId, {
        reported_room_id: normalizeRoomId(state.settings.roomId),
      });
      state.heartbeatStatus = "ok";
      state.heartbeatError = "";
    } catch (err) {
      state.heartbeatStatus = "error";
      state.heartbeatError = err?.message || String(err);
    }
  }

  function stopHeartbeat() {
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer);
      heartbeatTimer = null;
    }
  }

  function startHeartbeat() {
    stopHeartbeat();
    if (!isActive.value || !state.settings.surfaceId) return;
    void sendHeartbeat();
    heartbeatTimer = setInterval(() => void sendHeartbeat(), heartbeatMs);
  }

  async function acquireWakeLock() {
    if (!isActive.value) return;
    if (!wakeLock?.request) {
      state.wakeLockStatus = "unsupported";
      console.warn("Screen Wake Lock API is not supported in this browser.");
      return;
    }
    try {
      wakeLockSentinel = await wakeLock.request("screen");
      state.wakeLockStatus = "active";
      wakeLockSentinel.addEventListener?.("release", () => {
        state.wakeLockStatus = "released";
      });
    } catch (err) {
      state.wakeLockStatus = "error";
      console.warn("Screen wake lock request failed.", err);
    }
  }

  async function releaseWakeLock() {
    if (!wakeLockSentinel) return;
    try {
      await wakeLockSentinel.release?.();
    } finally {
      wakeLockSentinel = null;
      state.wakeLockStatus = "released";
    }
  }

  async function begin(startSession) {
    if (typeof startSession === "function") {
      await startSession();
    }
    state.started = true;
    await acquireWakeLock();
    startHeartbeat();
  }

  async function handleEnableMicrophone(startSession) {
    if (typeof startSession !== "function") return;
    await startSession();
  }

  function onSocketConnect() {
    state.connected = true;
  }

  function onSocketDisconnect() {
    state.connected = false;
  }

  function unlockSettings(pin) {
    state.settingsUnlocked = pin === state.settings.pin;
    return state.settingsUnlocked;
  }

  async function saveSettings(nextSettings) {
    state.settings.kioskEnabled = Boolean(nextSettings.kioskEnabled);
    state.settings.surfaceId = nextSettings.surfaceId?.trim() || "";
    state.settings.roomId = normalizeRoomId(nextSettings.roomId);
    state.settings.pin = nextSettings.pin || state.settings.pin || DEFAULT_PIN;
    persistSettings();

    if (!state.settings.kioskEnabled && !routeKiosk.value) {
      state.started = false;
      stopHeartbeat();
      await releaseWakeLock();
    } else {
      startHeartbeat();
    }
  }

  function onVisibilityChange() {
    if (documentRef?.visibilityState === "visible" && isActive.value && state.started) {
      void acquireWakeLock();
    }
  }

  watch(
    () => [isActive.value, state.settings.surfaceId, state.settings.roomId],
    () => startHeartbeat(),
  );

  onMounted(() => {
    documentRef?.addEventListener?.("visibilitychange", onVisibilityChange);
    if (isActive.value) {
      void loadRooms();
      startHeartbeat();
    }
  });

  onUnmounted(() => {
    stopHeartbeat();
    documentRef?.removeEventListener?.("visibilitychange", onVisibilityChange);
    void releaseWakeLock();
  });

  return {
    state,
    actions: {
      begin,
      handleEnableMicrophone,
      onSocketConnect,
      onSocketDisconnect,
      unlockSettings,
      saveSettings,
      loadRooms,
      sendHeartbeat,
      acquireWakeLock,
      releaseWakeLock,
      startHeartbeat,
      stopHeartbeat,
    },
  };
}
