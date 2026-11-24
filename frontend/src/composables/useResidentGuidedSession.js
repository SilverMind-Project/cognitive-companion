/**
 * The resident's view of a guided routine on the companion screen.
 *
 * State arrives two ways: `guided_session_state` broadcasts while connected, and
 * a hydration read (`GET /guided-sessions/resident-state`) on load and on every
 * reconnect, so a tablet that rebooted or dropped mid-routine shows the step she
 * is on (or clears a routine that ended while it was away). Both carry the same
 * resident-safe shape. A broadcast that lands while a hydration read is in
 * flight is newer than that read, so the read is discarded.
 *
 * Taps go over `/ws/audio`; each is answered by `guided_step_action_result` to
 * the tapping tablet only, which releases the buttons even when the tap changed
 * nothing. A timeout releases them if that answer never comes.
 */

import { reactive } from "vue";

// Statuses in which a step has been put to her and is on her screen.
export const STEP_IN_PROGRESS = new Set(["active", "waiting", "escalated", "caregiver_takeover"]);

export const CELEBRATE_MS = 4000;
export const ACK_TIMEOUT_MS = 8000;

/**
 * @param {object} deps
 * @param {any} deps.ws The companion socket (`wsClient`).
 * @param {{ getResidentGuidedState: () => Promise<any> }} deps.api
 * @param {typeof setTimeout} [deps.setTimer]
 * @param {typeof clearTimeout} [deps.clearTimer]
 */
export function useResidentGuidedSession({
  ws,
  api,
  setTimer = setTimeout,
  clearTimer = clearTimeout,
}) {
  const state = reactive({
    /** The session on screen (a `guided_session_state` payload) or null. */
    session: null,
    /** The tap awaiting its answer ("done" | "repeat" | "help") or null. */
    pendingAction: null,
    /** True for a few seconds after she finishes, before the widget closes. */
    celebrating: false,
  });

  let stateVersion = 0;
  let celebrateTimer = null;
  let ackTimer = null;

  function clearPending() {
    state.pendingAction = null;
    if (ackTimer !== null) {
      clearTimer(ackTimer);
      ackTimer = null;
    }
  }

  function clearSession() {
    if (celebrateTimer !== null) {
      clearTimer(celebrateTimer);
      celebrateTimer = null;
    }
    state.celebrating = false;
    state.session = null;
    clearPending();
  }

  function show(next) {
    if (celebrateTimer !== null) {
      clearTimer(celebrateTimer);
      celebrateTimer = null;
    }
    state.celebrating = false;
    state.session = next;
    clearPending();
  }

  function onState(next) {
    stateVersion += 1;
    const current = state.session;
    const isCurrent = current !== null && current.session_id === next.session_id;

    if (STEP_IN_PROGRESS.has(next.status)) {
      show(next);
      return;
    }
    // Only the session on screen may close it; news of another one is ignored.
    if (!isCurrent) return;
    if (next.status === "completed") {
      state.session = next;
      state.celebrating = true;
      clearPending();
      celebrateTimer = setTimer(() => {
        celebrateTimer = null;
        if (state.session?.session_id === next.session_id) clearSession();
      }, CELEBRATE_MS);
      return;
    }
    // Abandoned, failed, or back to summoning: nothing to show, and no word
    // that sounds like failure.
    clearSession();
  }

  async function hydrate() {
    const version = stateVersion;
    let result;
    try {
      result = await api.getResidentGuidedState();
    } catch (err) {
      // Keep what is on screen; the next broadcast or reconnect corrects it.
      console.warn("Guided session hydration failed:", err);
      return;
    }
    if (version !== stateVersion) return;
    const live = result?.session ?? null;
    if (live && STEP_IN_PROGRESS.has(live.status)) {
      if (state.session?.session_id !== live.session_id || !state.celebrating) show(live);
    } else if (!state.celebrating) {
      clearSession();
    }
  }

  function onActionResult(result) {
    if (
      result?.session_id === state.session?.session_id &&
      result?.action === state.pendingAction
    ) {
      clearPending();
    }
  }

  /** Send a tap; returns false when nothing was sent (busy, idle, or offline). */
  function submit(action) {
    const current = state.session;
    if (!current || state.celebrating || state.pendingAction !== null || !ws.isOpen) return false;
    state.pendingAction = action;
    ws.sendGuidedStepAction(current.session_id, action, current.current_step_ord);
    ackTimer = setTimer(() => {
      ackTimer = null;
      state.pendingAction = null;
    }, ACK_TIMEOUT_MS);
    return true;
  }

  function onConnect() {
    void hydrate();
  }

  function mount() {
    ws.on("onGuidedSessionState", onState);
    ws.on("onGuidedStepActionResult", onActionResult);
    ws.on("onConnect", onConnect);
    void hydrate();
  }

  function unmount() {
    ws.off("onGuidedSessionState", onState);
    ws.off("onGuidedStepActionResult", onActionResult);
    ws.off("onConnect", onConnect);
    clearSession();
  }

  return {
    state,
    actions: { hydrate, onState, onActionResult, submit, mount, unmount },
  };
}
