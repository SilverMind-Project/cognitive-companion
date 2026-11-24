import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  ACK_TIMEOUT_MS,
  CELEBRATE_MS,
  useResidentGuidedSession,
} from "@/composables/useResidentGuidedSession.js";

const state = (overrides = {}) => ({
  type: "guided_session_state",
  session_id: 12,
  routine_id: 3,
  routine_name: "Morning Tea",
  person_id: "resident-1",
  status: "active",
  current_step_ord: 0,
  total_steps: 3,
  prompt_text: "Fill the kettle.",
  at: "2026-11-24T09:00:00Z",
  ...overrides,
});

function fakeWs() {
  const callbacks = {};
  return {
    isOpen: true,
    sent: [],
    on: (event, cb) => (callbacks[event] = [...(callbacks[event] ?? []), cb]),
    off: (event, cb) => (callbacks[event] = (callbacks[event] ?? []).filter((x) => x !== cb)),
    emit: (event, data) => (callbacks[event] ?? []).forEach((cb) => cb(data)),
    sendGuidedStepAction(sessionId, action, stepOrd) {
      this.sent.push([sessionId, action, stepOrd]);
    },
  };
}

describe("useResidentGuidedSession", () => {
  beforeEach(() => vi.useFakeTimers());

  it("hydrates on mount and again on every reconnect", async () => {
    const ws = fakeWs();
    const api = {
      getResidentGuidedState: vi
        .fn()
        .mockResolvedValueOnce({ session: state() })
        .mockResolvedValueOnce({ session: null }),
    };
    const guided = useResidentGuidedSession({ ws, api });

    guided.actions.mount();
    await vi.runAllTimersAsync();
    expect(guided.state.session.session_id).toBe(12);

    // The routine ended while the tablet was away: the reconnect clears it.
    ws.emit("onConnect");
    await vi.runAllTimersAsync();
    expect(guided.state.session).toBeNull();
  });

  it("drops a hydration read overtaken by a live broadcast", async () => {
    const ws = fakeWs();
    let resolve;
    const api = { getResidentGuidedState: () => new Promise((r) => (resolve = r)) };
    const guided = useResidentGuidedSession({ ws, api });

    guided.actions.mount();
    ws.emit("onGuidedSessionState", state({ current_step_ord: 1 }));
    resolve({ session: state({ current_step_ord: 0 }) });
    await vi.runAllTimersAsync();

    expect(guided.state.session.current_step_ord).toBe(1);
  });

  it("sends the step on screen with a tap and frees the buttons on the answer", () => {
    const ws = fakeWs();
    const guided = useResidentGuidedSession({ ws, api: {} });
    guided.actions.onState(state({ current_step_ord: 2 }));

    expect(guided.actions.submit("done")).toBe(true);
    expect(ws.sent).toEqual([[12, "done", 2]]);
    expect(guided.state.pendingAction).toBe("done");
    // A second tap while the first is in flight is not sent.
    expect(guided.actions.submit("done")).toBe(false);

    guided.actions.onActionResult({ session_id: 12, action: "done", accepted: false });
    expect(guided.state.pendingAction).toBeNull();
  });

  it("frees the buttons if the answer never comes, and never sends offline", () => {
    const ws = fakeWs();
    const guided = useResidentGuidedSession({ ws, api: {} });
    guided.actions.onState(state());

    guided.actions.submit("help");
    vi.advanceTimersByTime(ACK_TIMEOUT_MS);
    expect(guided.state.pendingAction).toBeNull();

    ws.isOpen = false;
    expect(guided.actions.submit("help")).toBe(false);
    expect(ws.sent).toHaveLength(1);
  });

  it("celebrates completion briefly, then clears", () => {
    const guided = useResidentGuidedSession({ ws: fakeWs(), api: {} });
    guided.actions.onState(state());

    guided.actions.onState(state({ status: "completed", prompt_text: "" }));
    expect(guided.state.celebrating).toBe(true);
    vi.advanceTimersByTime(CELEBRATE_MS);
    expect(guided.state.session).toBeNull();
    expect(guided.state.celebrating).toBe(false);
  });

  it("clears quietly when abandoned and ignores another session's ending", () => {
    const guided = useResidentGuidedSession({ ws: fakeWs(), api: {} });
    guided.actions.onState(state());

    guided.actions.onState(state({ session_id: 99, status: "abandoned" }));
    expect(guided.state.session.session_id).toBe(12);

    guided.actions.onState(state({ status: "abandoned" }));
    expect(guided.state.session).toBeNull();
    expect(guided.state.celebrating).toBe(false);
  });
});
