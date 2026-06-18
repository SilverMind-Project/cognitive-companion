import { reactive, readonly, onUnmounted } from "vue";
import { api } from "@/services/api.js";
import { useNotify } from "@/composables/useNotify.js";
import { openPipelineSocket } from "@/services/api.js";

/**
 * State + actions for the Guided Session Console.
 * Subscribes to guided_session_update / guided_escalation events via
 * the /ws/pipeline WebSocket (same reconnection pattern as useCtsWebSocket).
 */
export function useGuidedSessionConsole(sessionId) {
  const { notify } = useNotify();

  const state = reactive({
    loading: false,
    saving: false,
    session: null,
    currentStep: null,
    events: [],
    transcript: [],
    wsStatus: "disconnected",
    escalationBanner: null,
    error: null,
  });

  let ws = null;
  let reconnectTimer = null;
  let closed = false;

  async function load() {
    state.loading = true;
    state.error = null;
    try {
      const data = await api.getGuidedSessionDetail(sessionId);
      state.session = data.session;
      state.currentStep = data.current_step;
      state.events = data.recent_events ?? [];
      state.transcript = data.recent_transcript ?? [];
    } catch (err) {
      state.error = err.message || "Failed to load session";
      notify.error(state.error);
    } finally {
      state.loading = false;
    }
  }

  async function refreshSession() {
    try {
      const data = await api.getGuidedSessionDetail(sessionId);
      state.session = data.session;
      state.currentStep = data.current_step;
      state.events = data.recent_events ?? [];
      state.transcript = data.recent_transcript ?? [];
    } catch {
      // non-fatal refresh failure
    }
  }

  function onWsMessage(data) {
    if (
      data.type === "guided_session_update" &&
      data.session_id === Number(sessionId)
    ) {
      if (state.session) {
        state.session = {
          ...state.session,
          status: data.status,
          current_step_ord: data.current_step_ord,
        };
      }
      state.events = [
        {
          id: Date.now(),
          at: data.at,
          kind: data.event_kind,
          step_ord: data.current_step_ord,
          actor: data.actor,
          detail: data.detail,
        },
        ...state.events,
      ].slice(0, 50);
      refreshSession();
    }
    if (
      data.type === "guided_escalation" &&
      data.session_id === Number(sessionId)
    ) {
      state.escalationBanner = {
        reason: data.reason,
        emergency: data.emergency,
        at: data.at,
      };
    }
  }

  function connect() {
    if (closed) return;
    state.wsStatus = "connecting";
    ws = openPipelineSocket(onWsMessage);
    ws.onopen = () => {
      state.wsStatus = "open";
    };
    ws.onerror = () => {
      state.wsStatus = "error";
    };
    ws.onclose = () => {
      state.wsStatus = "closed";
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

  async function takeover() {
    state.saving = true;
    try {
      const updated = await api.beginGuidedSessionTakeover(sessionId);
      state.session = updated;
      state.escalationBanner = null;
      notify.success("Takeover active.");
    } catch (err) {
      notify.error("Takeover failed: " + (err.message || err));
    } finally {
      state.saving = false;
    }
  }

  async function say(text) {
    if (!text?.trim()) return;
    state.saving = true;
    try {
      await api.sayGuidedSession(sessionId, text);
    } catch (err) {
      notify.error("Failed to send: " + (err.message || err));
    } finally {
      state.saving = false;
    }
  }

  async function advance() {
    state.saving = true;
    try {
      await api.advanceGuidedSession(sessionId);
      await refreshSession();
    } catch (err) {
      notify.error("Advance failed: " + (err.message || err));
    } finally {
      state.saving = false;
    }
  }

  async function complete() {
    state.saving = true;
    try {
      const updated = await api.completeGuidedSession(sessionId);
      state.session = updated;
      notify.success("Session completed.");
    } catch (err) {
      notify.error("Complete failed: " + (err.message || err));
    } finally {
      state.saving = false;
    }
  }

  async function release() {
    state.saving = true;
    try {
      const updated = await api.releaseGuidedSession(sessionId);
      state.session = updated;
      notify.success("Takeover released.");
    } catch (err) {
      notify.error("Release failed: " + (err.message || err));
    } finally {
      state.saving = false;
    }
  }

  onUnmounted(disconnect);
  load();
  connect();

  return {
    state: readonly(state),
    actions: { load, takeover, say, advance, complete, release },
  };
}
