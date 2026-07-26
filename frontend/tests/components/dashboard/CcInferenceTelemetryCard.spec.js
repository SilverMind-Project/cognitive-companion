import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { reactive } from "vue";
import CcInferenceTelemetryCard from "@/components/dashboard/CcInferenceTelemetryCard.vue";

const mockRefresh = vi.fn();
let mockState;

vi.mock("@/composables/useInferenceTelemetry.js", () => ({
  useInferenceTelemetry: () => ({
    state: mockState,
    actions: { refresh: mockRefresh },
  }),
}));

const stubs = {
  CcSectionCard: {
    template: '<div><slot name="actions" /><slot /></div>',
  },
  CcMetricTile: {
    template: '<div class="metric-tile" :data-status="status">{{ label }}: {{ value }}</div>',
    props: ["label", "value", "status"],
  },
  CcBarChart: {
    template: '<div class="bar-chart" />',
    props: ["categories", "series", "unit"],
  },
  "v-btn": { template: "<button><slot /></button>" },
  "v-progress-circular": { template: "<div />" },
  "v-alert": { template: '<div class="v-alert"><slot /></div>' },
  "v-row": { template: "<div><slot /></div>" },
  "v-col": { template: "<div><slot /></div>" },
};

function _makeState(overrides) {
  return reactive({
    loading: false,
    error: null,
    telemetry: null,
    ...overrides,
  });
}

describe("CcInferenceTelemetryCard", () => {
  it("calls refresh on mount", () => {
    mockState = _makeState({});
    mount(CcInferenceTelemetryCard, { global: { stubs } });
    expect(mockRefresh).toHaveBeenCalled();
  });

  it("shows the warning treatment when timeouts occurred", () => {
    mockState = _makeState({
      telemetry: {
        window_minutes: 60,
        totals_by_caller_lane: [
          { caller: "rule:tea_intent", lane: "vision", ok: 3, timeout: 1, error: 0 },
        ],
        queue_depth: [
          { lane: "vision", depth: 0 },
          { lane: "text", depth: 0 },
        ],
        queue_wait_p50_ms: 10,
        queue_wait_p95_ms: 40,
        timeouts_total: 1,
        calls_per_hour: [],
        ring_buffer_size: 4,
        ring_buffer_capacity: 2000,
      },
    });
    const wrapper = mount(CcInferenceTelemetryCard, { global: { stubs } });

    const tiles = wrapper.findAll(".metric-tile");
    const timeoutsTile = tiles.find((t) => t.text().includes("Timeouts"));
    expect(timeoutsTile.attributes("data-status")).toBe("warning");
    expect(timeoutsTile.text()).toContain("1");
  });

  it("renders vision/text call totals and queue wait p95", () => {
    mockState = _makeState({
      telemetry: {
        window_minutes: 60,
        totals_by_caller_lane: [
          { caller: "rule:tea_intent", lane: "vision", ok: 3, timeout: 0, error: 0 },
          { caller: "gate:confirm", lane: "text", ok: 2, timeout: 0, error: 0 },
        ],
        queue_depth: [
          { lane: "vision", depth: 1 },
          { lane: "text", depth: 0 },
        ],
        queue_wait_p50_ms: 10,
        queue_wait_p95_ms: 40,
        timeouts_total: 0,
        calls_per_hour: [],
        ring_buffer_size: 5,
        ring_buffer_capacity: 2000,
      },
    });
    const wrapper = mount(CcInferenceTelemetryCard, { global: { stubs } });

    const tiles = wrapper.findAll(".metric-tile");
    const visionTile = tiles.find((t) => t.text().includes("Vision calls"));
    const textTile = tiles.find((t) => t.text().includes("Text calls"));
    const p95Tile = tiles.find((t) => t.text().includes("Queue wait p95"));
    const visionDepthTile = tiles.find((t) => t.text().includes("Vision queue depth"));

    expect(visionTile.text()).toContain("3");
    expect(textTile.text()).toContain("2");
    expect(p95Tile.text()).toContain("40");
    expect(visionDepthTile.text()).toContain("1");
  });

  it("shows loading state before data arrives", () => {
    mockState = _makeState({ loading: true });
    const wrapper = mount(CcInferenceTelemetryCard, { global: { stubs } });
    expect(wrapper.find(".metric-tile").exists()).toBe(false);
  });

  it("shows an error alert on failure", () => {
    mockState = _makeState({ error: "upstream unavailable" });
    const wrapper = mount(CcInferenceTelemetryCard, { global: { stubs } });
    expect(wrapper.find(".v-alert").text()).toContain("upstream unavailable");
  });
});
