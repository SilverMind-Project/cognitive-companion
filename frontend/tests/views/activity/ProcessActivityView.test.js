/**
 * U5-T6: ProcessActivityView
 *
 * Verifies:
 * - Renders CcDagChart in the runs tab
 * - An incoming step_started WS event marks the active node as running
 * - A failed step_completed event carries the error status (not succeeded)
 * - "Stream interrupted" alert shows when socket error fires (D5)
 * - CcLiveActivityFeed is rendered in the ingest tab
 */
import { describe, it, expect, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";

// ── Top-level mocks ──────────────────────────────────────────────────────────

const mockGetPipelineRuns = vi.fn();
const mockGetIngestActivity = vi.fn();
const mockGetWorkflowDetail = vi.fn();
let capturedOnMessage = null;
const mockWs = { onopen: null, onerror: null, onclose: null, close: vi.fn() };

vi.mock("@/services/api.js", () => ({
  api: {
    getPipelineRuns: (...a) => mockGetPipelineRuns(...a),
    getIngestActivity: (...a) => mockGetIngestActivity(...a),
    getWorkflowDetail: (...a) => mockGetWorkflowDetail(...a),
  },
  openPipelineSocket: (onMessage) => {
    capturedOnMessage = onMessage;
    return mockWs;
  },
}));

vi.mock("@/composables/useNotify.js", () => ({
  useNotify: () => ({ notify: { error: vi.fn(), success: vi.fn() } }),
}));

vi.mock("@/services/timezone.js", () => ({
  formatDateTimeShort: (iso) => iso || "",
}));

vi.mock("@/components/process/CcDagChart.vue", () => ({
  default: {
    name: "CcDagChart",
    template: '<div data-testid="cc-dag-chart" />',
    props: ["nodes", "edges", "activeNodeId", "activeEdges", "nodeTimings", "loading", "error"],
  },
}));

vi.mock("@/components/process/CcStatusTimeline.vue", () => ({
  default: {
    template: '<div data-testid="cc-status-timeline" />',
    props: ["lanes", "events", "loading", "error"],
  },
}));

vi.mock("@/components/process/CcLiveActivityFeed.vue", () => ({
  default: {
    template: '<div data-testid="cc-live-activity-feed" />',
    props: ["events", "maxHeight"],
  },
}));

vi.mock("@/components/dashboard/CcMetricTile.vue", () => ({
  default: { template: "<div />", props: ["label", "value", "status"] },
}));

vi.mock("@/components/pipeline/ExecutionInspector.vue", () => ({
  default: {
    template: '<div data-testid="execution-inspector" />',
    props: ["executionId", "source", "ruleId", "liveRun"],
  },
}));

vi.mock("vue-router", () => ({
  useRoute: () => ({ query: {}, params: {} }),
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

import ProcessActivityView from "../../../src/views/activity/ProcessActivityView.vue";

const ACTIVE_RUN = {
  execution_id: 10,
  rule_id: 1,
  rule_name: "motion-alert",
  status: "running",
  started_at: "2026-05-29T10:00:00Z",
  nodes: [
    { id: "101", label: "Filter", step_type: "condition", status: "pending" },
    { id: "102", label: "Notify", step_type: "notification", status: "pending" },
  ],
  edges: [{ source: "101", target: "102" }],
};

const stubs = {
  "v-row": { template: "<div><slot /></div>" },
  "v-col": { template: "<div><slot /></div>", props: ["cols", "sm", "md"] },
  "v-card": { template: "<div><slot /></div>" },
  "v-card-title": { template: "<div><slot /></div>" },
  "v-card-text": { template: "<div><slot /></div>" },
  "v-card-actions": { template: "<div><slot /></div>" },
  "v-alert": {
    template: '<div :data-type="type"><slot /></div>',
    props: ["type", "variant", "density"],
  },
  "v-btn": {
    template: "<button><slot /></button>",
    props: ["size", "variant", "color", "to", "prepend-icon", "icon", "title", "loading"],
  },
  "v-chip": {
    template: "<span><slot /></span>",
    props: ["color", "size", "variant", "class", "prepend-icon"],
  },
  "v-spacer": { template: "<div />" },
  "v-tabs": { template: "<div><slot /></div>", props: ["modelValue", "color"] },
  "v-tab": { template: "<button><slot /></button>", props: ["value"] },
  "v-window": { template: "<div><slot /></div>", props: ["modelValue"] },
  "v-window-item": { template: "<div><slot /></div>", props: ["value"] },
  "v-list": { template: "<ul><slot /></ul>", props: ["density"] },
  "v-list-item": { template: "<li />", props: ["title", "subtitle", "active"] },
  "v-divider": { template: "<hr />" },
  "v-icon": { template: "<i />", props: ["color", "size", "class"] },
  "v-progress-circular": { template: "<div />", props: ["indeterminate", "size"] },
  "v-navigation-drawer": {
    template: "<div />",
    props: ["modelValue", "location", "temporary", "width", "class"],
  },
  "router-link": { template: "<a />" },
};

function mountView() {
  mockGetPipelineRuns.mockResolvedValue([ACTIVE_RUN]);
  mockGetIngestActivity.mockResolvedValue([]);
  mockGetWorkflowDetail.mockResolvedValue(null);
  capturedOnMessage = null;
  return mount(ProcessActivityView, { global: { stubs } });
}

// Vue Test Utils unwraps refs from defineExpose; access them directly (not .value).

describe("ProcessActivityView — connection state (D5)", () => {
  it("shows stream-interrupted alert when socket error fires", async () => {
    const w = mountView();
    await flushPromises();

    // Trigger socket error via the WS mock; the composable sets connectionState='error'.
    mockWs.onerror?.();
    await w.vm.$nextTick();

    const alerts = w.findAll('[data-type="warning"]');
    expect(alerts.length).toBeGreaterThan(0);
  });
});

describe("ProcessActivityView — active runs DAG", () => {
  it("CcDagChart is rendered after selecting a run (D2: uses shared component)", async () => {
    const w = mountView();
    await flushPromises();

    // activeRuns is pre-loaded with ACTIVE_RUN; select it.
    w.vm.selectRun(ACTIVE_RUN);
    await w.vm.$nextTick();

    expect(w.findAll('[data-testid="cc-dag-chart"]').length).toBeGreaterThan(0);
  });

  it("step_started WS event marks the node as running in activeRuns", async () => {
    const w = mountView();
    await flushPromises();

    // activeRuns is already loaded with ACTIVE_RUN (unwrapped ref → array).
    const runs = w.vm.activeRuns;
    expect(Array.isArray(runs)).toBe(true);

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

    await w.vm.$nextTick();

    const updatedRuns = w.vm.activeRuns;
    const node = updatedRuns
      ?.find?.((r) => r.execution_id === 10)
      ?.nodes?.find((n) => n.id === "101");
    expect(node?.status).toBe("running");
  });

  it("step_completed with failed status sets node status to failed (rule 15: never succeeded)", async () => {
    const w = mountView();
    await flushPromises();

    capturedOnMessage?.({
      type: "pipeline_event",
      event_type: "step_completed",
      execution_id: 10,
      rule_id: 1,
      rule_name: "motion-alert",
      step_id: "102",
      status: "failed",
      error_code: "timeout",
      sequence: 3,
    });

    await w.vm.$nextTick();

    const node = w.vm.activeRuns
      ?.find?.((r) => r.execution_id === 10)
      ?.nodes?.find((n) => n.id === "102");
    expect(node?.status).toBe("failed");
  });
});

describe("ProcessActivityView — ingest feed (D2: CcLiveActivityFeed)", () => {
  it("renders CcLiveActivityFeed", async () => {
    const w = mountView();
    await flushPromises();
    expect(w.findAll('[data-testid="cc-live-activity-feed"]').length).toBeGreaterThan(0);
  });
});
