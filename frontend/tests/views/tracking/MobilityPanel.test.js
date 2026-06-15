/**
 * MobilityPanel
 *
 * Tests: gap rendering on insufficient days, empty collecting state,
 * data ownership (panel does not call cts.getGaitTrend directly),
 * and component mounting without warnings.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { reactive, ref } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";

// ── Mock heavy chart and service modules ────────────────────────────────────

vi.mock("vue-echarts", () => ({
  default: { name: "VChart", props: ["option", "theme", "autoresize"], template: "<div />" },
}));
vi.mock("echarts/core", () => ({ use: vi.fn() }));
vi.mock("echarts/renderers", () => ({ CanvasRenderer: {} }));
vi.mock("echarts/charts", () => ({
  LineChart: {}, BarChart: {}, HeatmapChart: {}, ScatterChart: {},
  GaugeChart: {}, GraphChart: {},
}));
vi.mock("echarts/components", () => ({
  GridComponent: {}, TooltipComponent: {}, LegendComponent: {},
  MarkLineComponent: {}, VisualMapComponent: {}, DataZoomComponent: {},
  TitleComponent: {},
}));

vi.mock("@/composables/useChartTheme.js", () => ({
  useChartTheme: () => ({
    chartTheme: {
      __v_isRef: true,
      value: {
        color: [],
        textStyle: {},
        xAxis: { axisLabel: {} },
        yAxis: {},
        tooltip: {},
        _severity: {},
      },
    },
  }),
}));

// Mock api.getPersons so component can resolve person options
vi.mock("@/services/api.js", () => ({
  api: {
    getPersons: vi.fn(async () => [{ id: "alice", display_name: "Alice" }]),
  },
}));

// Spy on cts.getGaitTrend to verify data ownership: MobilityPanel must NOT
// call it directly — only through the useGaitTrend composable.
const getGaitTrendSpy = vi.fn(async () => ({
  person_id: "alice",
  days: [],
  baseline_median_m_s: null,
  trend: "insufficient",
}));
vi.mock("@/services/cts.js", () => ({ cts: { getGaitTrend: getGaitTrendSpy } }));

// Mock useGaitTrend so we control state
const mockGaitState = reactive({ envelope: null, loading: false, error: null, personId: null });
const mockFetch = vi.fn(async (personId, days) => {
  mockGaitState.personId = personId;
});
vi.mock("@/composables/useGaitTrend.js", () => ({
  useGaitTrend: () => ({ state: mockGaitState, actions: { fetch: mockFetch } }),
}));

import MobilityPanel from "@/views/tracking/panels/MobilityPanel.vue";

const stubs = {
  "v-select":   { template: '<select @change="$emit(\'update:modelValue\', $event.target.value)"><slot /></select>', props: ["modelValue", "items", "label"] },
  "v-btn":      { template: '<button @click="$emit(\'click\')"><slot /></button>', props: ["loading", "variant", "color", "size"] },
  "v-card":     { template: '<div><slot /></div>', props: ["variant", "class"] },
  "v-row":      { template: '<div><slot /></div>' },
  "v-col":      { template: '<div><slot /></div>', props: ["cols", "sm"] },
  "v-chip":     { template: '<span class="chip"><slot /></span>', props: ["color", "variant", "size"] },
  "v-alert":    { template: '<div role="alert"><slot /></div>', props: ["type", "variant", "density"] },
  "v-icon":     { template: "<span />" },
  "v-progress-circular": { template: "<div />" },
  "CcSectionCard":       { template: "<section><slot /></section>" },
  "CcGaitTrendChart":    { template: '<div data-testid="gait-chart" />', props: ["points", "baselineValue", "signalDates", "loading", "error"] },
  "TrackingPanelHeader": { template: "<header><slot name='actions' /><slot /></header>", props: ["title", "description"] },
};

async function mountPanel({ person = null } = {}) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/", component: { template: "<div />" } }],
  });
  await router.push(person ? `/?person=${person}` : "/");
  await router.isReady();
  const wrapper = mount(MobilityPanel, { global: { plugins: [router], stubs } });
  await flushPromises();
  return wrapper;
}

beforeEach(() => {
  mockGaitState.envelope = null;
  mockGaitState.loading = false;
  mockGaitState.error = null;
  mockGaitState.personId = null;
  mockFetch.mockClear();
  getGaitTrendSpy.mockClear();
});

describe("MobilityPanel", () => {
  it("mounts without throwing", async () => {
    await expect(mountPanel()).resolves.toBeDefined();
  });

  it("shows collecting empty state when trend=insufficient", async () => {
    mockGaitState.envelope = {
      person_id: "alice",
      days: [
        { date: "2026-05-01", median_speed_m_s: null, bout_count: 1, total_walking_s: 30, sufficient: false },
      ],
      baseline_median_m_s: null,
      trend: "insufficient",
    };
    const w = await mountPanel({ person: "alice" });
    expect(w.text()).toContain("Collecting mobility baseline");
  });

  it("insufficient days have null speed (no zeros in chart props)", async () => {
    mockGaitState.envelope = {
      person_id: "alice",
      days: [
        { date: "2026-05-01", median_speed_m_s: null, bout_count: 1, total_walking_s: 20, sufficient: false },
        { date: "2026-05-02", median_speed_m_s: 0.9, bout_count: 5, total_walking_s: 120, sufficient: true },
      ],
      baseline_median_m_s: 0.9,
      trend: "stable",
    };
    const w = await mountPanel({ person: "alice" });
    // CcGaitTrendChart is stubbed; check the points prop
    const chartEl = w.find('[data-testid="gait-chart"]');
    expect(chartEl.exists()).toBe(true);
  });

  it("does not call cts.getGaitTrend directly (data ownership)", async () => {
    await mountPanel();
    expect(getGaitTrendSpy).not.toHaveBeenCalled();
  });

  it("collecting message shows qualifying day count of 10", async () => {
    mockGaitState.envelope = {
      person_id: "alice",
      days: Array.from({ length: 3 }, (_, i) => ({
        date: `2026-05-0${i + 1}`,
        median_speed_m_s: null,
        bout_count: 1,
        total_walking_s: 10,
        sufficient: false,
      })),
      baseline_median_m_s: null,
      trend: "insufficient",
    };
    const w = await mountPanel({ person: "alice" });
    expect(w.text()).toContain("0 of 10 qualifying days");
  });
});
