import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { reactive } from "vue";
import CcDailyLivingHealthCard from "@/components/dashboard/CcDailyLivingHealthCard.vue";

const mockRefresh = vi.fn();
let mockState;

vi.mock("@/composables/useDailyLivingHealth.js", () => ({
  useDailyLivingHealth: () => ({
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
    health: null,
    ...overrides,
  });
}

describe("CcDailyLivingHealthCard", () => {
  it("calls refresh on mount", () => {
    mockState = _makeState({});
    mount(CcDailyLivingHealthCard, { global: { stubs } });
    expect(mockRefresh).toHaveBeenCalled();
  });

  it("shows the warning treatment when semantic memory is stale", () => {
    mockState = _makeState({
      health: {
        semantic_memory: {
          reachable: true,
          last_observation_at: "2026-07-19T14:00:00Z",
          last_movement_at: null,
          observations_by_day: [],
          total_observations: 5,
          total_movements: 0,
          stale: true,
        },
        activity_ledger: { by_type: [], stale: true },
      },
    });
    const wrapper = mount(CcDailyLivingHealthCard, { global: { stubs } });

    const tiles = wrapper.findAll(".metric-tile");
    const memoryTile = tiles.find((t) => t.text().includes("Last memory write"));
    expect(memoryTile.attributes("data-status")).toBe("warning");
    expect(wrapper.find(".v-alert").exists()).toBe(true);
  });

  it("shows an error status when semantic memory is unreachable", () => {
    mockState = _makeState({
      health: {
        semantic_memory: {
          reachable: false,
          last_observation_at: null,
          last_movement_at: null,
          observations_by_day: [],
          total_observations: 0,
          total_movements: 0,
          stale: true,
        },
        activity_ledger: { by_type: [], stale: true },
      },
    });
    const wrapper = mount(CcDailyLivingHealthCard, { global: { stubs } });

    const tiles = wrapper.findAll(".metric-tile");
    const memoryTile = tiles.find((t) => t.text().includes("Last memory write"));
    expect(memoryTile.attributes("data-status")).toBe("error");
    expect(memoryTile.text()).toContain("Unreachable");
  });

  it("shows an ok status and no stale banner when everything is fresh", () => {
    mockState = _makeState({
      health: {
        semantic_memory: {
          reachable: true,
          last_observation_at: "2026-07-21T13:59:00Z",
          last_movement_at: null,
          observations_by_day: [{ day: "2026-07-21T00:00:00Z", source: "scene_intel", count: 4 }],
          total_observations: 4,
          total_movements: 0,
          stale: false,
        },
        activity_ledger: {
          by_type: [{ activity_type: "sleep", count: 1, last_opened_at: "2026-07-21T06:00:00Z" }],
          stale: false,
        },
      },
    });
    const wrapper = mount(CcDailyLivingHealthCard, { global: { stubs } });

    const tiles = wrapper.findAll(".metric-tile");
    const memoryTile = tiles.find((t) => t.text().includes("Last memory write"));
    expect(memoryTile.attributes("data-status")).toBe("ok");
    expect(wrapper.find(".v-alert").exists()).toBe(false);
  });
});
