import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const mocks = vi.hoisted(() => ({
  getPipelineRuns: vi.fn(),
  getWorkflows: vi.fn(),
  getIngestActivity: vi.fn(),
  replace: vi.fn(),
  connectionState: { __v_isRef: true, value: "open" },
  activeRuns: { __v_isRef: true, value: [] },
  ingestEvents: { __v_isRef: true, value: [] },
  refreshSocket: vi.fn(),
}));

vi.mock("@/services/api.js", () => ({
  api: {
    getPipelineRuns: (...args) => mocks.getPipelineRuns(...args),
    getWorkflows: (...args) => mocks.getWorkflows(...args),
    getIngestActivity: (...args) => mocks.getIngestActivity(...args),
  },
}));

vi.mock("@/composables/useLivePipeline.js", () => ({
  useLivePipeline: () => ({
    connectionState: mocks.connectionState,
    activeRuns: mocks.activeRuns,
    ingestEvents: mocks.ingestEvents,
    refresh: mocks.refreshSocket,
  }),
}));

vi.mock("@/composables/useNotify.js", () => ({
  useNotify: () => ({ notify: { error: vi.fn(), success: vi.fn() } }),
}));

vi.mock("@/services/timezone.js", () => ({
  DATETIME_COLUMN_WIDTH: 180,
  formatDateTime: (iso) => iso || "",
  formatDateTimeShort: (iso) => iso || "",
}));

vi.mock("vue-router", () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ replace: mocks.replace }),
}));

vi.mock("@/components/pipeline/ExecutionInspector.vue", () => ({
  default: {
    name: "ExecutionInspector",
    props: ["executionId", "source", "ruleId", "liveRun"],
    template: '<div data-testid="execution-inspector">{{ executionId }}:{{ source }}</div>',
  },
}));

vi.mock("@/components/process/CcLiveActivityFeed.vue", () => ({
  default: { template: '<div data-testid="cc-live-activity-feed" />', props: ["events", "maxHeight"] },
}));

vi.mock("@/components/process/CcStatusTimeline.vue", () => ({
  default: { template: '<div />', props: ["lanes", "events", "loading"] },
}));

vi.mock("@/components/dashboard/CcMetricTile.vue", () => ({
  default: { template: '<div />', props: ["label", "value", "status"] },
}));

import ExecutionsView from "../../src/views/admin/ExecutionsView.vue";

const ACTIVE_RUN = {
  execution_id: 10,
  rule_id: 1,
  rule_name: "motion-alert",
  status: "running",
  started_at: "2026-05-29T10:00:00Z",
};

const HISTORY_ROW = {
  id: 20,
  rule_id: 2,
  rule_name: "daily-report",
  status: "completed",
  started_at: "2026-05-28T10:00:00Z",
};

const stubs = {
  "v-row": { template: '<div><slot /></div>' },
  "v-col": { template: '<div><slot /></div>', props: ["cols", "sm", "md"] },
  "v-card": { template: '<section><slot /></section>' },
  "v-card-title": { template: '<div><slot /></div>' },
  "v-card-text": { template: '<div><slot /></div>' },
  "v-alert": { template: '<div><slot /></div>', props: ["type", "variant", "density"] },
  "v-btn": { template: '<button @click="$emit(\'click\')"><slot /></button>', props: ["size", "variant", "prependIcon"] },
  "v-chip": { template: '<span><slot /></span>', props: ["color", "size", "variant", "prependIcon"] },
  "v-spacer": { template: '<div />' },
  "v-tabs": { template: '<div><slot /></div>', props: ["modelValue", "color"] },
  "v-tab": { template: '<button><slot /></button>', props: ["value"] },
  "v-window": { template: '<div><slot /></div>', props: ["modelValue"] },
  "v-window-item": { template: '<div><slot /></div>', props: ["value"] },
  "v-list": { template: '<ul><slot /></ul>', props: ["density"] },
  "v-list-item": { template: '<li @click="$emit(\'click\')">{{ title }} {{ subtitle }}<slot name="append" /></li>', props: ["title", "subtitle", "active"] },
  "v-select": { template: '<select />', props: ["modelValue", "items", "label"] },
  "v-data-table": { template: '<div data-testid="history-table"><slot name="no-data" /></div>', props: ["headers", "items", "loading", "itemValue"] },
  "v-progress-circular": { template: '<div />' },
};

function mountView() {
  return mount(ExecutionsView, { global: { stubs } });
}

beforeEach(() => {
  mocks.getPipelineRuns.mockReset();
  mocks.getWorkflows.mockReset();
  mocks.getIngestActivity.mockReset();
  mocks.replace.mockReset();
  mocks.refreshSocket.mockReset();
  mocks.connectionState.value = "open";
  mocks.activeRuns.value = [ACTIVE_RUN];
  mocks.ingestEvents.value = [];
  mocks.getPipelineRuns.mockResolvedValue([ACTIVE_RUN]);
  mocks.getWorkflows.mockResolvedValue([HISTORY_ROW]);
  mocks.getIngestActivity.mockResolvedValue([]);
});

describe("ExecutionsView", () => {
  it("renders Live and History tabs", async () => {
    const wrapper = mountView();
    await flushPromises();

    expect(wrapper.text()).toContain("Live");
    expect(wrapper.text()).toContain("History");
  });

  it("opens ExecutionInspector in live mode from an active run", async () => {
    const wrapper = mountView();
    await flushPromises();

    wrapper.vm.selectRun(ACTIVE_RUN, "live");
    await wrapper.vm.$nextTick();

    expect(wrapper.vm.selectedExecutionId).toBe(10);
    expect(wrapper.vm.selectedSource).toBe("live");
  });

  it("opens ExecutionInspector in historic mode from a history row", async () => {
    const wrapper = mountView();
    await flushPromises();

    wrapper.vm.selectHistory(HISTORY_ROW);
    await wrapper.vm.$nextTick();

    expect(wrapper.vm.selectedExecutionId).toBe(20);
    expect(wrapper.vm.selectedSource).toBe("historic");
  });

  it("History tab filters by status", async () => {
    const wrapper = mountView();
    await flushPromises();

    wrapper.vm.filter.status = "failed";
    await wrapper.vm.loadHistory();

    expect(mocks.getWorkflows).toHaveBeenLastCalledWith({ status: "failed" });
  });
});
