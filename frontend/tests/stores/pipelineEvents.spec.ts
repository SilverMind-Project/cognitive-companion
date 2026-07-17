import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getPipelineRuns: vi.fn(),
  openPipelineSocket: vi.fn(),
  sockets: [] as any[],
}));

vi.mock("@/services/api.js", () => ({
  api: { getPipelineRuns: (...args: any[]) => mocks.getPipelineRuns(...args) },
  openPipelineSocket: (onMessage: any) => mocks.openPipelineSocket(onMessage),
}));

import { MAX_INGEST_EVENTS, usePipelineEventsStore } from "@/stores/pipelineEvents";

function newSocket(onMessage: any) {
  const ws = {
    onMessage,
    onopen: null as any,
    onerror: null as any,
    onclose: null as any,
    close: vi.fn(),
  };
  mocks.sockets.push(ws);
  return ws;
}

function lastSocket() {
  return mocks.sockets[mocks.sockets.length - 1];
}

describe("pipelineEvents store", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
    mocks.sockets = [];
    mocks.getPipelineRuns.mockResolvedValue([]);
    mocks.openPipelineSocket.mockImplementation(newSocket);
    setActivePinia(createPinia());
  });

  it("two consumers share one socket (inverts the pre-M18 socket-per-consumer behavior)", () => {
    const store = usePipelineEventsStore();

    const releaseA = store.connect();
    const releaseB = store.connect();

    expect(mocks.openPipelineSocket).toHaveBeenCalledTimes(1);
    expect(mocks.getPipelineRuns).toHaveBeenCalledTimes(1);

    releaseA();
    releaseB();
  });

  it("the socket stays open until the last consumer releases", () => {
    const store = usePipelineEventsStore();
    const releaseA = store.connect();
    const releaseB = store.connect();
    const ws = lastSocket();

    releaseA();
    expect(ws.close).not.toHaveBeenCalled();

    releaseB();
    expect(ws.close).toHaveBeenCalledTimes(1);
    expect(store.connectionState).toBe("disconnected");
  });

  it("release is idempotent and cannot drive the count negative", () => {
    const store = usePipelineEventsStore();
    const releaseA = store.connect();
    const releaseB = store.connect();

    releaseA();
    releaseA();
    releaseA();

    expect(store._consumerCount()).toBe(1);
    expect(lastSocket().close).not.toHaveBeenCalled();

    releaseB();
    expect(store._consumerCount()).toBe(0);
  });

  it("re-acquiring after a full release opens a fresh socket", () => {
    const store = usePipelineEventsStore();
    store.connect()();
    expect(mocks.openPipelineSocket).toHaveBeenCalledTimes(1);

    const release = store.connect();
    expect(mocks.openPipelineSocket).toHaveBeenCalledTimes(2);
    release();
  });

  it("connectionState transitions through the documented set", () => {
    const store = usePipelineEventsStore();
    expect(store.connectionState).toBe("disconnected");

    const release = store.connect();
    expect(store.connectionState).toBe("connecting");

    lastSocket().onopen();
    expect(store.connectionState).toBe("open");

    lastSocket().onerror();
    expect(store.connectionState).toBe("error");
    expect(store.error).toBeTruthy();

    release();
    expect(store.connectionState).toBe("disconnected");
  });

  it("an unexpected close reconnects while a consumer is still listening", () => {
    vi.useFakeTimers();
    const store = usePipelineEventsStore();
    const release = store.connect();

    lastSocket().onclose();
    expect(store.connectionState).toBe("closed");

    vi.advanceTimersByTime(3000);
    expect(mocks.openPipelineSocket).toHaveBeenCalledTimes(2);
    expect(store.connectionState).toBe("connecting");

    release();
  });

  it("a deliberate last release does not schedule a reconnect", () => {
    vi.useFakeTimers();
    const store = usePipelineEventsStore();

    store.connect()();
    vi.advanceTimersByTime(10000);

    expect(mocks.openPipelineSocket).toHaveBeenCalledTimes(1);
    expect(store.connectionState).toBe("disconnected");
  });

  it("a pending reconnect that fires after the last release does not resurrect the socket", () => {
    vi.useFakeTimers();
    const store = usePipelineEventsStore();
    const release = store.connect();

    // Network drop schedules a reconnect, then the view unmounts before it fires.
    lastSocket().onclose();
    release();
    vi.advanceTimersByTime(10000);

    expect(mocks.openPipelineSocket).toHaveBeenCalledTimes(1);
  });

  it("state resets on last release so a later consumer does not inherit a stale feed", async () => {
    const store = usePipelineEventsStore();
    const release = store.connect();
    lastSocket().onMessage({ event_type: "frame_received", execution_id: 1 });
    expect(store.ingestEvents).toHaveLength(1);

    release();

    expect(store.ingestEvents).toEqual([]);
    expect(store.activeRuns).toEqual([]);
    expect(store.error).toBeNull();
  });

  it("caps the retained event feed", () => {
    const store = usePipelineEventsStore();
    const release = store.connect();

    for (let i = 0; i < MAX_INGEST_EVENTS + 25; i++) {
      lastSocket().onMessage({ event_type: "frame_received", execution_id: i });
    }

    expect(store.ingestEvents).toHaveLength(MAX_INGEST_EVENTS);
    // The newest survive; the oldest are dropped.
    expect(store.ingestEvents.at(-1).execution_id).toBe(MAX_INGEST_EVENTS + 24);
    expect(store.ingestEvents[0].execution_id).toBe(25);
    release();
  });

  it("a single socket message updates the run once, not once per consumer", () => {
    const store = usePipelineEventsStore();
    const releaseA = store.connect();
    const releaseB = store.connect();

    lastSocket().onMessage({
      event_type: "pipeline_started",
      execution_id: 10,
      rule_id: 1,
      rule_name: "motion-alert",
      started_at: "2026-07-16T10:00:00Z",
      steps: [{ id: "101", label: "Filter", step_type: "condition" }],
      edges: [],
    });

    expect(store.activeRuns).toHaveLength(1);
    expect(store.ingestEvents).toHaveLength(1);

    releaseA();
    releaseB();
  });
});
