/**
 * CcGaitTrendChart
 *
 * Tests: gap rendering for insufficient days, empty state, baseline markLine,
 * and that useChartTheme is called for theming.
 */
import { describe, it, expect, vi } from "vitest";
import { mount } from "@vue/test-utils";

vi.mock("vue-echarts", () => ({
  default: {
    name: "VChart",
    props: ["option", "theme", "autoresize"],
    template: '<div data-testid="v-chart" />',
  },
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

const THEME_MOCK = {
  color: ["#3F6B52"],
  backgroundColor: "transparent",
  textStyle: { color: "#1D1A14" },
  xAxis: { axisLabel: {} },
  yAxis: {},
  tooltip: {},
  _severity: { warning: "#C98A2E" },
};

vi.mock("@/composables/useChartTheme.js", () => ({
  useChartTheme: () => ({
    theme: "ccWarm",
    chartTheme: { value: THEME_MOCK },
  }),
}));

const stubs = {
  "v-alert": { template: '<div role="alert"><slot /></div>', props: ["type"] },
  "v-skeleton-loader": { template: "<div data-testid='skeleton' />" },
};

import CcGaitTrendChart from "@/components/charts/CcGaitTrendChart.vue";

function makePoints(n = 5, sufficientAll = true) {
  return Array.from({ length: n }, (_, i) => ({
    date: `2026-05-${String(i + 1).padStart(2, "0")}`,
    value: sufficientAll ? 0.9 : null,
    sufficient: sufficientAll,
  }));
}

describe("CcGaitTrendChart", () => {
  it("renders v-chart when points are provided", () => {
    const wrapper = mount(CcGaitTrendChart, {
      props: { points: makePoints(5) },
      global: { stubs },
    });
    expect(wrapper.find('[data-testid="v-chart"]').exists()).toBe(true);
  });

  it("shows empty slot when points array is empty", () => {
    const wrapper = mount(CcGaitTrendChart, {
      props: { points: [] },
      global: { stubs },
    });
    expect(wrapper.find('[data-testid="v-chart"]').exists()).toBe(false);
  });

  it("shows skeleton in loading state", () => {
    const wrapper = mount(CcGaitTrendChart, {
      props: { points: [], loading: true },
      global: { stubs },
    });
    expect(wrapper.find('[data-testid="skeleton"]').exists()).toBe(true);
  });

  it("shows error alert when error prop is set", () => {
    const wrapper = mount(CcGaitTrendChart, {
      props: { points: [], error: "Upstream failure" },
      global: { stubs },
    });
    expect(wrapper.find('[role="alert"]').exists()).toBe(true);
  });

  it("maps null to speeds array for insufficient days (gap rendering)", () => {
    const points = [
      { date: "2026-05-01", value: 0.9, sufficient: true },
      { date: "2026-05-02", value: null, sufficient: false },
      { date: "2026-05-03", value: 0.85, sufficient: true },
    ];
    const wrapper = mount(CcGaitTrendChart, {
      props: { points },
      global: { stubs },
    });
    const { chartOption } = wrapper.vm;
    const speeds = chartOption.series[0].data;
    expect(speeds[0]).toBeCloseTo(0.9);
    expect(speeds[1]).toBeNull();
    expect(speeds[2]).toBeCloseTo(0.85);
  });

  it("emits a markLine when baselineValue is set", () => {
    const wrapper = mount(CcGaitTrendChart, {
      props: { points: makePoints(3), baselineValue: 0.88 },
      global: { stubs },
    });
    const { chartOption } = wrapper.vm;
    const markLine = chartOption.series[0].markLine;
    expect(markLine).toBeDefined();
    expect(markLine.data[0].yAxis).toBeCloseTo(0.88);
  });

  it("passes theme from useChartTheme to v-chart", () => {
    const wrapper = mount(CcGaitTrendChart, {
      props: { points: makePoints(3) },
      global: { stubs },
    });
    const chart = wrapper.findComponent({ name: "VChart" });
    expect(chart.props("theme")).toBe("ccWarm");
  });

  it("connectNulls is false on the series (gaps, not bridging)", () => {
    const wrapper = mount(CcGaitTrendChart, {
      props: { points: makePoints(3) },
      global: { stubs },
    });
    const { chartOption } = wrapper.vm;
    expect(chartOption.series[0].connectNulls).toBe(false);
  });
});
