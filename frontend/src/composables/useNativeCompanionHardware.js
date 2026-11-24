/**
 * The companion screen's hardware, driven by the server's `surface_hardware_command`.
 *
 * When a routine step, quiz, card, or prompt is for the resident in this room, the
 * server tells this screen to wake and to listen; she should never have to walk up
 * and tap a microphone button first. Inside the Android shell (tablet or TV) the
 * native `CompanionHardware` plugin wakes the screen (on a TV, HDMI-CEC turns the
 * set on), raises a muted volume, and opens the microphone and optionally the front
 * camera; in a browser only the microphone can be opened, and only once the page
 * has had a tap.
 *
 * Every capture is leased, per delivery (`lease_owner`): a guided routine, a quiz,
 * and a card each hold their own lease, and the microphone (camera) stays open
 * while any live lease asks for it, so a card closing mid-routine never cuts the
 * routine's microphone. A lease runs out unless its owner renews it, so a lost
 * release can never leave a microphone or camera open. A command that only wakes
 * the screen is a screen-only lease, never a release. Leases only stop a recording
 * they started: if she was already talking, the end of a quiz does not cut her off.
 *
 * The camera reports only whether a face is in front of the screen and roughly
 * where it is looking; no image ever leaves the device.
 *
 * Not a Pinia store: it owns listeners and a lease timer scoped to the view.
 */

import { reactive } from "vue";
import { Capacitor, registerPlugin } from "@capacitor/core";

const CompanionHardware = registerPlugin("CompanionHardware");

/**
 * @param {object} deps
 * @param {any} deps.ws The companion socket (`wsClient`).
 * @param {() => boolean} deps.isRecording Whether the microphone is capturing now.
 * @param {() => Promise<void> | void} deps.startCapture Start capturing (and sending) audio.
 * @param {() => void} deps.stopCapture Stop capturing audio.
 * @param {any} [deps.plugin] The native plugin (injectable for tests).
 * @param {() => boolean} [deps.isNative] Whether this runs inside the Android shell.
 * @param {typeof setTimeout} [deps.setTimer]
 * @param {typeof clearTimeout} [deps.clearTimer]
 */
export function useNativeCompanionHardware({
  ws,
  isRecording,
  startCapture,
  stopCapture,
  plugin = CompanionHardware,
  isNative = () => Capacitor.isNativePlatform(),
  setTimer = setTimeout,
  clearTimer = clearTimeout,
}) {
  const state = reactive({
    /** Running inside the Android shell. */
    native: false,
    /** `web`, `android_tablet`, or `android_tv` (sent with the socket and heartbeat). */
    platform: "web",
    /** The device says it is a TV (Android UI mode television). */
    isTelevision: false,
    /** A server lease currently holds the microphone open. */
    micLeased: false,
    /** The front camera is running (shown to her as "Camera active"). */
    cameraActive: false,
    /** The device's own report of its screen, or null when unknown (a browser). */
    screenAwake: null,
    /** Last hardware error, for the kiosk settings screen. */
    error: "",
  });

  /** Live leases by owner: `{ microphone, camera, timer }`. */
  const leases = new Map();
  // True when a lease, not her own tap, started the current recording.
  let leaseStartedCapture = false;
  const nativeListeners = [];

  function endLease(owner) {
    const lease = leases.get(owner);
    if (lease) clearTimer(lease.timer);
    leases.delete(owner);
  }

  /** Make capture match the leases still live. */
  async function reconcile({ openMicrophone = false } = {}) {
    const live = [...leases.values()];
    const microphone = live.some((lease) => lease.microphone);
    state.micLeased = microphone;
    state.cameraActive = state.native && live.some((lease) => lease.camera);
    if (microphone && openMicrophone && !isRecording()) {
      leaseStartedCapture = true;
      await startCapture();
    } else if (!microphone && leaseStartedCapture) {
      leaseStartedCapture = false;
      if (isRecording()) stopCapture();
    }
  }

  async function callNative(method, args) {
    if (!state.native) return null;
    try {
      return await plugin[method](args);
    } catch (err) {
      state.error = err?.message || String(err);
      return null;
    }
  }

  /** Act on one `surface_hardware_command` from the server. */
  async function applyCommand(command) {
    // The lease is recorded and capture started before anything is awaited: the
    // server sends `enable_microphone` right behind this command, and if it were
    // handled first (during the round trip to the shell) the recording would not
    // belong to the lease, and the lease's end would never close the microphone.
    const owner = command.lease_owner || "";
    const leaseMs = Math.max(0, Number(command.lease_seconds) || 0) * 1000;
    endLease(owner);
    if (leaseMs > 0) {
      const timer = setTimer(() => {
        leases.delete(owner);
        void reconcile();
      }, leaseMs);
      leases.set(owner, {
        microphone: Boolean(command.enable_microphone),
        camera: Boolean(command.enable_camera),
        timer,
      });
    }
    const reconciled = reconcile({
      openMicrophone: Boolean(command.enable_microphone) && leaseMs > 0,
    });
    if (state.native) {
      const result = await callNative("applyCommand", command);
      if (result && typeof result.screenAwake === "boolean") state.screenAwake = result.screenAwake;
    }
    await reconciled;
  }

  /** The shell's own lease timer fired (the page may have been suspended). */
  function onNativeLeaseExpired(event) {
    const owners = Array.isArray(event?.owners) ? event.owners : [...leases.keys()];
    for (const owner of owners) endLease(owner);
    void reconcile();
  }

  function onAttention(event) {
    ws.sendSurfaceAttentionState({
      facePresent: Boolean(event?.facePresent),
      headYawDeg: typeof event?.yaw === "number" ? event.yaw : null,
      headPitchDeg: typeof event?.pitch === "number" ? event.pitch : null,
    });
  }

  function onCommand(command) {
    void applyCommand(command);
  }

  /** Detect the shell, subscribe to commands, and forward native attention events. */
  async function mount() {
    ws.on("onSurfaceHardwareCommand", onCommand);
    state.native = Boolean(isNative());
    if (!state.native) return;
    const info = await callNative("getDeviceInfo");
    state.isTelevision = Boolean(info?.isTelevision);
    state.platform = state.isTelevision ? "android_tv" : "android_tablet";
    for (const [name, handler] of [
      ["facePresenceChanged", onAttention],
      // The native lease timer is the backstop when the page was suspended.
      ["leaseExpired", onNativeLeaseExpired],
    ]) {
      try {
        nativeListeners.push(await plugin.addListener(name, handler));
      } catch (err) {
        state.error = err?.message || String(err);
      }
    }
  }

  function unmount() {
    ws.off("onSurfaceHardwareCommand", onCommand);
    for (const owner of [...leases.keys()]) endLease(owner);
    for (const listener of nativeListeners.splice(0)) void listener?.remove?.();
  }

  /** What the heartbeat reports about this device (nulls when a browser cannot tell). */
  function deviceState() {
    return {
      platform: state.platform,
      mic_active: isRecording(),
      camera_active: state.native ? state.cameraActive : null,
      screen_awake: state.screenAwake,
    };
  }

  return { state, actions: { mount, unmount, applyCommand, deviceState } };
}
