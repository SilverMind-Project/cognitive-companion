/**
 * U5-T8: Ingest feed integration in ProcessActivityView
 *
 * Verifies:
 * - CcLiveActivityFeed receives events from ingest activity REST data
 * - New pipeline_started WS events append to ingestEvents
 * - CcMetricTile values update when ingest activity has data
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
    getPipelineRuns:   (...a) => mockGetPipelineRuns(...a),
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

vi.mock("@/components/process/CcLiveActivityFeed.vue", () => ({
  default: {
    name: "CcLiveActivityFeed",
    template: '<div data-testid="cc-live-activity-feed" :data-count="events.length" />',
    props: ["events", "maxHeight"],
  },
}));

vi.mock("@/components/process/CcDagChart.vue", () => ({
  default: { template: '<div />', props: ["nodes", "edges", "activeNodeId", "loading"] },
}));

vi.mock("@/components/process/CcStatusTimeline.vue", () => ({
  default: { template: '<div />', props: ["lanes", "events", "loading"] },
}));

vi.mock("@/components/dashboard/CcMetricTile.vue", () => ({
  default: {
    name: "CcMetricTile",
    template: '<div data-testid="metric-tile" :data-label="label" :data-value="String(value)" />',
    props: ["label", "value", "status"],
  },
}));

vi.mock("@/components/pipeline/ExecutionDetail.vue", () => ({
  default: { template: '<div />', props: ["execution", "live"] },
}));

vi.mock("vue-router", () => ({
  useRoute:  () => ({ query: {}, params: {} }),
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

import ProcessActivityView from "../../../src/views/activity/ProcessActivityView.vue";

const INGEST_ACTIVITY = [
  {
    id: "frame-1",
    event_type: "frame_received",
    timestamp: "2026-05-29T10:00:00Z",
    sensor_id: "recamera_kitchen1",
  },
  {
    id: "rule-1",
    event_type: "rule_triggered",
    timestamp: "2026-05-29T10:00:01Z",
    sensor_id: "recamera_kitchen1",
    trigger_type: "sensor_event",
    rule_name: "motion-alert",
  },
];

const stubs = {
  "v-row":               { template: '<div><slot /></div>' },
  "v-col":               { template: '<div><slot /></div>', props: ["cols", "sm", "md"] },
  "v-card":              { template: '<div><slot /></div>' },
  "v-card-title":        { template: '<div><slot /></div>' },
  "v-card-text":         { template: '<div><slot /></div>' },
  "v-alert":             { template: '<div />', props: ["type", "variant", "density"] },
  "v-btn":               { template: '<button />', props: ["size", "variant", "color", "to", "prepend-icon", "icon"] },
  "v-chip":              { template: '<span />', props: ["color", "size", "variant", "prepend-icon"] },
  "v-spacer":            { template: '<div />' },
  "v-tabs":              { template: '<div><slot /></div>', props: ["modelValue", "color"] },
  "v-tab":               { template: '<button />', props: ["value"] },
  "v-window":            { template: '<div><slot /></div>', props: ["modelValue"] },
  "v-window-item":       { template: '<div><slot /></div>', props: ["value"] },
  "v-list":              { template: '<ul><slot /></ul>', props: ["density"] },
  "v-list-item":         { template: '<li />', props: ["title", "subtitle", "active"] },
  "v-divider":           { template: '<hr />' },
  "v-icon":              { template: '<i />', props: ["color", "size", "class"] },
  "v-progress-circular": { template: '<div />', props: ["indeterminate", "size"] },
  "v-navigation-drawer": { template: '<div />', props: ["modelValue", "location", "temporary", "width", "class"] },
  "router-link":         { template: '<a />' },
};

function mountView() {
  mockGetPipelineRuns.mockResolvedValue([]);
  mockGetIngestActivity.mockResolvedValue(INGEST_ACTIVITY);
  mockGetWorkflowDetail.mockResolvedValue(null);
  capturedOnMessage = null;
  return mount(ProcessActivityView, { global: { stubs } });
}

describe("Ingest feed — REST data (D1: single ingest source)", () => {
  it("CcLiveActivityFeed receives events derived from ingest activity", async () => {
    const w = mountView();
    await flushPromises();

    const feed = w.find('[data-testid="cc-live-activity-feed"]');
    const count = parseInt(feed.attributes("data-count") || "0", 10);
    expect(count).toBeGreaterThan(0);
  });

  it("CcMetricTile for rules triggered shows non-zero count", async () => {
    const w = mountView();
    await flushPromises();

    const tiles = w.findAll('[data-testid="metric-tile"]');
    const rulesTile = tiles.find((t) => t.attributes("data-label") === "Rules triggered");
    expect(rulesTile).toBeDefined();
    const val = parseInt(rulesTile?.attributes("data-value") || "0", 10);
    expect(val).toBeGreaterThan(0);
  });
});

describe("Ingest feed — WebSocket events appended", () => {
  it("pipeline_started WS event is recorded in ingestEvents", async () => {
    const w = mountView();
    await flushPromises();

    capturedOnMessage?.({
      type: "pipeline_event",
      event_type: "pipeline_started",
      execution_id: 20,
      rule_id: 2,
      rule_name: "new-rule",
      status: "running",
      started_at: "2026-05-29T11:00:00Z",
      sequence: 1,
    });

    await w.vm.$nextTick();

    // ingestEvents is a ref exposed via defineExpose → unwrapped by test-utils.
    const wsEvents = w.vm.ingestEvents;
    const eventList = Array.isArray(wsEvents) ? wsEvents : (wsEvents?.value ?? []);
    expect(eventList.length).toBeGreaterThan(0);
  });
});
