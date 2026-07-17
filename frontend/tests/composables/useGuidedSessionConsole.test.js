/**
 * Tests for useGuidedSessionConsole composable.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { defineComponent, h } from "vue";

const mockApi = vi.hoisted(() => ({
  getGuidedSessionDetail: vi.fn(),
  beginGuidedSessionTakeover: vi.fn(),
  sayGuidedSession: vi.fn(),
  advanceGuidedSession: vi.fn(),
  completeGuidedSession: vi.fn(),
  releaseGuidedSession: vi.fn(),
}));

const mockWs = vi.hoisted(() => ({
  onopen: null,
  onerror: null,
  onclose: null,
  close: vi.fn(),
}));

let capturedOnMessage = null;

vi.mock("@/services/api.js", () => ({
  api: mockApi,
  openPipelineSocket: (onMessage) => {
    capturedOnMessage = onMessage;
    return mockWs;
  },
}));

vi.mock("@/composables/useNotify.js", () => ({
  useNotify: () => ({ notify: { success: vi.fn(), error: vi.fn() } }),
}));

import { useGuidedSessionConsole } from "../../src/composables/useGuidedSessionConsole.js";

function mountComposable(sessionId = "7") {
  let result;
  const Wrapper = defineComponent({
    setup() {
      result = useGuidedSessionConsole(sessionId);
      return () => h("div");
    },
  });
  mount(Wrapper);
  return result;
}

const SESSION = {
  id: 7,
  routine_id: 1,
  person_id: "resident-1",
  status: "escalated",
  current_step_ord: 0,
  attempts: 1,
  started_at: "2026-06-01T10:00:00Z",
  last_activity_at: "2026-06-01T10:05:00Z",
};

describe("useGuidedSessionConsole", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    capturedOnMessage = null;
    mockApi.getGuidedSessionDetail.mockResolvedValue({
      session: SESSION,
      current_step: {
        ord: 0,
        prompt_text: "Pour water.",
        completion_gate: { kinds: ["response"] },
        is_safety_critical: false,
      },
      recent_events: [],
      recent_transcript: [],
    });
    mockApi.sayGuidedSession.mockResolvedValue(SESSION);
    mockApi.advanceGuidedSession.mockResolvedValue({});
  });

  it("load populates session and currentStep", async () => {
    const { state } = mountComposable();
    await flushPromises();
    expect(state.session.id).toBe(7);
    expect(state.currentStep.ord).toBe(0);
    expect(state.loading).toBe(false);
  });

  it("guided_session_update for matching session updates status and appends event", async () => {
    const { state } = mountComposable();
    await flushPromises();
    // Update mock so the refresh after WS also returns the new status
    mockApi.getGuidedSessionDetail.mockResolvedValue({
      session: { ...SESSION, status: "active", current_step_ord: 1 },
      current_step: {
        ord: 1,
        prompt_text: "Boil water.",
        completion_gate: { kinds: ["response"] },
        is_safety_critical: false,
      },
      recent_events: [],
      recent_transcript: [],
    });
    capturedOnMessage({
      type: "guided_session_update",
      session_id: 7,
      status: "active",
      current_step_ord: 1,
      event_kind: "step_completed",
      actor: "user",
      detail: null,
      at: "2026-06-01T10:06:00Z",
    });
    // Events are updated synchronously before the refresh
    expect(state.events.length).toBeGreaterThan(0);
    await flushPromises();
    expect(state.session.status).toBe("active");
    expect(state.session.current_step_ord).toBe(1);
  });

  it("guided_session_update for different session is ignored", async () => {
    const { state } = mountComposable();
    await flushPromises();
    capturedOnMessage({
      type: "guided_session_update",
      session_id: 999,
      status: "completed",
      current_step_ord: 5,
      event_kind: "session_completed",
      actor: null,
      detail: null,
      at: "2026-06-01T10:07:00Z",
    });
    expect(state.session.status).toBe("escalated");
    expect(state.events).toHaveLength(0);
  });

  it("guided_escalation sets escalationBanner", async () => {
    const { state } = mountComposable();
    await flushPromises();
    capturedOnMessage({
      type: "guided_escalation",
      session_id: 7,
      status: "escalated",
      reason: "step_timeout",
      emergency: false,
      urgent: false,
      at: "2026-06-01T10:06:00Z",
    });
    expect(state.escalationBanner).not.toBeNull();
    expect(state.escalationBanner.reason).toBe("step_timeout");
  });

  it("say() calls the API with text", async () => {
    const { actions } = mountComposable();
    await flushPromises();
    await actions.say("Hello there!");
    await flushPromises();
    expect(mockApi.sayGuidedSession).toHaveBeenCalledWith("7", "Hello there!");
  });

  it("advance() calls the API", async () => {
    const { actions } = mountComposable();
    await flushPromises();
    await actions.advance();
    await flushPromises();
    expect(mockApi.advanceGuidedSession).toHaveBeenCalledWith("7");
  });
});
