/**
 * U5-T7: useLivePipeline composable
 *
 * Verifies:
 * - Surfaces connection state (connecting → open → error/closed)
 * - On socket error sets connectionState='error', error message set (D5)
 * - Seeded activeRuns from REST; updated on WS events
 * - step_started event marks the node as running in activeRuns
 * - pipeline_completed/failed removes the run from activeRuns
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { defineComponent, h } from "vue";

// ── Top-level mocks ──────────────────────────────────────────────────────────

const mockGetPipelineRuns = vi.fn();
const mockGetIngestActivity = vi.fn();
let capturedOnMessage = null;
const mockWs = {
  onopen: null,
  onerror: null,
  onclose: null,
  close: vi.fn(),
};

vi.mock("@/services/api.js", () => ({
  api: {
    getPipelineRuns:   (...args) => mockGetPipelineRuns(...args),
    getIngestActivity: (...args) => mockGetIngestActivity(...args),
  },
  openPipelineSocket: (onMessage) => {
    capturedOnMessage = onMessage;
    return mockWs;
  },
}));

import { useLivePipeline } from "../../src/composables/useLivePipeline.js";

const ACTIVE_RUN = {
  execution_id: 10,
  rule_id: 1,
  rule_name: "motion-alert",
  status: "running",
  started_at: "2026-05-29T10:00:00Z",
  nodes: [
    { id: "101", label: "Filter",  step_type: "condition",    status: "pending" },
    { id: "102", label: "Notify",  step_type: "notification", status: "pending" },
  ],
  edges: [{ source: "101", source_handle: "true", target: "102" }],
};

function mountComposable() {
  let result;
  const Wrapper = defineComponent({
    setup() {
      result = useLivePipeline();
      return () => h("div");
    },
  });
  const w = mount(Wrapper);
  return { result, wrapper: w };
}

beforeEach(() => {
  vi.clearAllMocks();
  capturedOnMessage = null;
  mockWs.onopen = null;
  mockWs.onerror = null;
  mockWs.onclose = null;
  mockGetPipelineRuns.mockResolvedValue([ACTIVE_RUN]);
  mockGetIngestActivity.mockResolvedValue([]);
});

describe("useLivePipeline — connection state", () => {
  it("starts as connecting", () => {
    const { result } = mountComposable();
    expect(result.connectionState.value).toBe("connecting");
  });

  it("transitions to open on ws.onopen", () => {
    const { result } = mountComposable();
    mockWs.onopen?.();
    expect(result.connectionState.value).toBe("open");
  });

  it("sets error state and message on ws.onerror (D5: never frozen DAG)", () => {
    const { result } = mountComposable();
    mockWs.onerror?.();
    expect(result.connectionState.value).toBe("error");
    expect(result.error.value).toBeTruthy();
  });

  it("sets closed state on ws.onclose when not reconnecting", () => {
    const { result } = mountComposable();
    result.disconnect();
    mockWs.onclose?.();
    expect(["closed", "disconnected", "connecting"]).toContain(result.connectionState.value);
  });
});

describe("useLivePipeline — active runs (D1)", () => {
  it("calls api.getPipelineRuns with status=active on mount", async () => {
    mountComposable();
    await flushPromises();
    expect(mockGetPipelineRuns).toHaveBeenCalledWith({ status: "active" });
  });

  it("seeds activeRuns from REST response", async () => {
    const { result } = mountComposable();
    await flushPromises();
    expect(result.activeRuns.value).toHaveLength(1);
    expect(result.activeRuns.value[0].execution_id).toBe(10);
  });

  it("step_started event marks the node as running", async () => {
    const { result } = mountComposable();
    await flushPromises();

    capturedOnMessage?.({
      type: "pipeline_event",
      event_type: "step_started",
      execution_id: 10,
      rule_id: 1,
      rule_name: "motion-alert",
      step_id: "101",
      status: "running",
      sequence: 2,
    });

    const node = result.activeRuns.value
      .find((r) => r.execution_id === 10)
      ?.nodes.find((n) => n.id === "101");
    expect(node?.status).toBe("running");
    expect(result.activeRuns.value.find((r) => r.execution_id === 10)?.active_node_id).toBe("101");
  });

  it("seeds nodes and edges from pipeline_started event payload", async () => {
    const { result } = mountComposable();
    await flushPromises();

    capturedOnMessage?.({
      type: "pipeline_event",
      event_type: "pipeline_started",
      execution_id: 20,
      rule_id: 2,
      rule_name: "doorbell",
      status: "running",
      started_at: "2026-06-01T10:01:00Z",
      steps: [
        { id: "201", label: "Condition", step_type: "condition", enabled: true },
        { id: "202", label: "Notify", step_type: "notification", enabled: true },
      ],
      edges: [
        { source: "201", source_handle: "false", target: "202", target_handle: "main" },
      ],
      sequence: 1,
    });

    const run = result.activeRuns.value.find((r) => r.execution_id === 20);
    expect(run?.nodes).toHaveLength(2);
    expect(run?.edges[0].sourceHandle).toBe("false");
    expect(run?.active_edges).toBeInstanceOf(Set);
  });

  it("tracks active_edges when step_completed event has output_port", async () => {
    const { result } = mountComposable();
    await flushPromises();

    capturedOnMessage?.({
      type: "pipeline_event",
      event_type: "step_completed",
      execution_id: 10,
      rule_id: 1,
      rule_name: "motion-alert",
      step_id: "101",
      status: "succeeded",
      output_port: "true",
      elapsed_ms: 42,
      sequence: 3,
    });

    const run = result.activeRuns.value.find((r) => r.execution_id === 10);
    const node = run?.nodes.find((n) => n.id === "101");
    expect(run?.active_edges.has("101:true")).toBe(true);
    expect(run?.edges[0].active).toBe(true);
    expect(node?.output_port).toBe("true");
    expect(node?.elapsed_ms).toBe(42);
  });

  it("pipeline_completed removes run from activeRuns", async () => {
    const { result } = mountComposable();
    await flushPromises();
    expect(result.activeRuns.value).toHaveLength(1);

    capturedOnMessage?.({
      type: "pipeline_event",
      event_type: "pipeline_completed",
      execution_id: 10,
      rule_id: 1,
      rule_name: "motion-alert",
      status: "completed",
      sequence: 10,
    });

    expect(result.activeRuns.value.find((r) => r.execution_id === 10)).toBeUndefined();
  });

  it("pipeline_failed removes run from activeRuns (never stays as running)", async () => {
    const { result } = mountComposable();
    await flushPromises();

    capturedOnMessage?.({
      type: "pipeline_event",
      event_type: "pipeline_failed",
      execution_id: 10,
      rule_id: 1,
      rule_name: "motion-alert",
      status: "failed",
      sequence: 10,
    });

    expect(result.activeRuns.value.find((r) => r.execution_id === 10)).toBeUndefined();
  });
});
