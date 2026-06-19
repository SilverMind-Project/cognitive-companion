import { beforeEach, describe, it, expect, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { reactive } from "vue";
import RoutineMetricsView from "@/views/admin/RoutineMetricsView.vue";

// ── Composable Mock ──────────────────────────────────────────────────────────

const metricsState = reactive({
  routine: { id: 123, name: "Morning Routine", person_id: "resident-1" },
  dashboard: null,
  loading: false,
  error: null,
});

const fetchDashboardMock = vi.fn(async (id) => {
  metricsState.dashboard = {
    completion: { completion_rate: 0.85 },
    attempts_per_step: { items: [{ step_ord: 0, average_attempts: 1.2 }] },
    time_to_complete: { items: [{ routine_id: 123, average_seconds: 600 }] },
    abandonment: { abandonment_rate: 0.1 },
    escalation_breakdown: { total: 2, items: [] },
    vision_agreement: { total: 5, agreement_rate: 0.8 },
    time_of_day: { buckets: [] },
    watch_summary: {
      total_runs: 15,
      auto_advances: 3,
      agreement_rate: 0.92,
      average_model_calls: 1.5,
      average_frames: 2.1,
      average_latency_ms: 1200,
    },
    gate_cost_summary: {
      confirm_cost: { model_calls: 5, frames: 15, latency_ms: 8000 },
      watch_cost: { model_calls: 15, frames: 45, latency_ms: 24000 },
      total_cost: { model_calls: 20, frames: 60, latency_ms: 32000 },
    },
  };
});

vi.mock("@/composables/useGuidedMetrics.js", () => ({
  useGuidedMetrics: () => ({
    state: metricsState,
    actions: { fetchDashboard: fetchDashboardMock },
  }),
}));

// ── Component Stubs ─────────────────────────────────────────────────────────

const stubs = {
  CcMetricTile: {
    template: `
      <div class="cc-metric-tile" :data-label="label" :data-value="value" :data-status="status">
        <span class="tile-label">{{ label }}</span>
        <span class="tile-value">{{ value }}</span>
      </div>
    `,
    props: ["label", "value", "status"],
  },
  CcSectionCard: {
    template: `
      <div class="cc-section-card" :data-title="title">
        <h3>{{ title }}</h3>
        <slot />
      </div>
    `,
    props: ["title"],
  },
  CcBarChart: {
    template: `<div class="cc-bar-chart" />`,
    props: ["categories", "series", "unit"],
  },
  CcGaugeChart: {
    template: `<div class="cc-gauge-chart" />`,
    props: ["value", "label", "unit"],
  },
  "v-btn": { template: "<button><slot /></button>", props: ["variant", "prepend-icon", "size", "to", "loading", "icon"] },
  "v-divider": { template: "<hr />", props: ["vertical"] },
  "v-spacer": { template: "<div />" },
  "v-progress-circular": { template: "<div class='loading-spinner' />", props: ["indeterminate", "color"] },
  "v-alert": { template: "<div class='alert'><slot /></div>", props: ["type", "density"] },
  "v-row": { template: "<div class='row'><slot /></div>" },
  "v-col": { template: "<div class='col'><slot /></div>", props: ["cols", "sm", "lg"] },
  "v-table": { template: "<table><slot /></table>", props: ["density"] },
};

describe("RoutineMetricsView.vue", () => {
  beforeEach(() => {
    metricsState.dashboard = null;
    metricsState.loading = false;
    metricsState.error = null;
    fetchDashboardMock.mockClear();
  });

  it("fetches the metrics dashboard on mount and renders components", async () => {
    const wrapper = mount(RoutineMetricsView, {
      props: { id: "123" },
      global: {
        stubs,
      },
    });

    expect(fetchDashboardMock).toHaveBeenCalledWith("123");

    // Wait for the mock fetch to resolve
    await flushPromises();

    // Verify Metric Tiles
    const tiles = wrapper.findAll(".cc-metric-tile");
    
    // We expect 8 tiles now (4 original + 4 watch-related)
    expect(tiles).toHaveLength(8);

    const tileMap = {};
    tiles.forEach(tile => {
      tileMap[tile.attributes("data-label")] = tile.attributes("data-value");
    });

    expect(tileMap["Completion rate"]).toBe("85%");
    expect(tileMap["Abandonment"]).toBe("10%");
    expect(tileMap["Watch runs"]).toBe("15");
    expect(tileMap["Watch auto-advances"]).toBe("3");
    expect(tileMap["Watch agreement"]).toBe("92%");
    expect(tileMap["Total VLM cost"]).toBe("20 calls");

    // Verify the Gate Compute Cost card
    const costCard = wrapper.find('[data-title="Gate compute cost"]');
    expect(costCard.exists()).toBe(true);

    // Verify confirmation and watch cost values rendered inside table
    const text = costCard.text();
    expect(text).toContain("Confirm");
    expect(text).toContain("Watch");
    expect(text).toContain("Total");
    
    // Check row data using regexes on text content
    expect(text).toMatch(/Confirm5158\.00s/);
    expect(text).toMatch(/Watch154524\.00s/);
    expect(text).toMatch(/Total206032\.00s/);
  });
});
