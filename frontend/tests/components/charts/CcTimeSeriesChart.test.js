/**
 * U3-T1: CcTimeSeriesChart
 *
 * Verifies: series rendering, #no-data empty state on empty input,
 * and time labels routed through timezone.js (never toLocaleString).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";

// ── Mock heavy/unneeded modules ───────────────────────────────────────────

vi.mock("vue-echarts", () => ({
  default: {
    name: "VChart",
    props: ["option", "theme", "loading", "autoresize"],
    template: '<div data-testid="v-chart" />',
  },
}));

vi.mock("echarts/core", () => ({ use: vi.fn() }));
vi.mock("echarts/renderers", () => ({ CanvasRenderer: {} }));
vi.mock("echarts/charts", () => ({
  LineChart: {},
  BarChart: {},
  HeatmapChart: {},
  ScatterChart: {},
  GaugeChart: {},
  GraphChart: {},
}));
vi.mock("echarts/components", () => ({
  GridComponent: {},
  TooltipComponent: {},
  LegendComponent: {},
  MarkLineComponent: {},
  VisualMapComponent: {},
  DataZoomComponent: {},
  TitleComponent: {},
}));

// Spy on timezone.js to verify it is called and never bypassed.
const fmtSpy = vi.fn((iso) => `FMT(${iso})`);
vi.mock("@/services/timezone.js", () => ({
  formatDateTimeShort: (iso) => fmtSpy(iso),
}));

const THEME_MOCK = {
  color: ["#0a84ff"],
  backgroundColor: "transparent",
  textStyle: { color: "#fff" },
  xAxis: {
    axisLabel: { color: "#ccc" },
    axisLine: { lineStyle: { color: "#333" } },
    splitLine: { lineStyle: { color: "#333" } },
    axisTick: { lineStyle: { color: "#333" } },
    nameTextStyle: { color: "#ccc" },
  },
  yAxis: {
    axisLabel: { color: "#ccc" },
    axisLine: { lineStyle: { color: "#333" } },
    splitLine: { lineStyle: { color: "#333" } },
    axisTick: { lineStyle: { color: "#333" } },
    nameTextStyle: { color: "#ccc" },
  },
  tooltip: { backgroundColor: "#111", borderColor: "#333", textStyle: { color: "#fff" } },
  legend: { textStyle: { color: "#ccc" } },
  grid: { borderColor: "#333" },
  _severity: { warning: "#ff9500", succeeded: "#30d158", failed: "#ff453a" },
};

vi.mock("@/composables/useChartTheme.js", () => ({
  useChartTheme: () => ({
    chartTheme: {
      __v_isRef: true,
      value: THEME_MOCK,
    },
  }),
}));

const stubComponents = {
  "v-alert": { template: "<div><slot /></div>", props: ["type", "variant", "density"] },
  "v-skeleton-loader": { template: "<div />" },
};

import CcTimeSeriesChart from "../../../src/components/charts/CcTimeSeriesChart.vue";

const SERIES = [
  {
    name: "Motion",
    points: [
      { t: "2026-05-29T10:00:00Z", v: 5 },
      { t: "2026-05-29T11:00:00Z", v: 8 },
    ],
  },
];

describe("CcTimeSeriesChart", () => {
  beforeEach(() => fmtSpy.mockClear());

  it("renders the VChart stub when series has data", () => {
    const w = mount(CcTimeSeriesChart, {
      props: { series: SERIES },
      global: { stubs: stubComponents },
    });
    expect(w.find('[data-testid="v-chart"]').exists()).toBe(true);
  });

  it("passes the active token theme to v-chart", () => {
    const w = mount(CcTimeSeriesChart, {
      props: { series: SERIES },
      global: { stubs: stubComponents },
    });

    expect(w.findComponent({ name: "VChart" }).props("theme")).toStrictEqual(THEME_MOCK);
  });

  it("shows empty state when series is empty", () => {
    const w = mount(CcTimeSeriesChart, {
      props: { series: [] },
      global: { stubs: stubComponents },
    });
    expect(w.find('[data-testid="v-chart"]').exists()).toBe(false);
    expect(w.vm.isEmpty).toBe(true);
  });

  it("shows empty state when all series have zero points", () => {
    const w = mount(CcTimeSeriesChart, {
      props: { series: [{ name: "A", points: [] }] },
      global: { stubs: stubComponents },
    });
    expect(w.vm.isEmpty).toBe(true);
  });

  it("x-axis labels are formatted via timezone.js formatDateTimeShort", () => {
    const w = mount(CcTimeSeriesChart, {
      props: { series: SERIES },
      global: { stubs: stubComponents },
    });
    // Each point timestamp must have been passed to our spy
    expect(fmtSpy).toHaveBeenCalledWith("2026-05-29T10:00:00Z");
    expect(fmtSpy).toHaveBeenCalledWith("2026-05-29T11:00:00Z");
    // Labels in the option must be the spy's return values
    const labels = w.vm.chartOption.xAxis.data;
    expect(labels).toContain("FMT(2026-05-29T10:00:00Z)");
    expect(labels).toContain("FMT(2026-05-29T11:00:00Z)");
  });

  it("option.series has one entry per prop series", () => {
    const w = mount(CcTimeSeriesChart, {
      props: { series: SERIES },
      global: { stubs: stubComponents },
    });
    expect(w.vm.chartOption.series).toHaveLength(1);
    expect(w.vm.chartOption.series[0].type).toBe("line");
    expect(w.vm.chartOption.series[0].data).toEqual([5, 8]);
  });

  it("renders error state when error prop is set", () => {
    const w = mount(CcTimeSeriesChart, {
      props: { series: SERIES, error: "Load failed" },
      global: { stubs: stubComponents },
    });
    expect(w.find('[data-testid="v-chart"]').exists()).toBe(false);
    expect(w.text()).toContain("Load failed");
  });

  it("loading prop hides chart", () => {
    const w = mount(CcTimeSeriesChart, {
      props: { series: SERIES, loading: true },
      global: { stubs: stubComponents },
    });
    expect(w.find('[data-testid="v-chart"]').exists()).toBe(false);
  });
});
