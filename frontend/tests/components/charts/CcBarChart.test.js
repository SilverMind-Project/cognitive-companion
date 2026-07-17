/**
 * U3-T2: CcBarChart
 *
 * Verifies: categories rendered in option; emits a `select` event with the
 * category payload when a bar is clicked.
 */
import { describe, it, expect, vi } from "vitest";
import { mount } from "@vue/test-utils";

vi.mock("vue-echarts", () => ({
  default: {
    name: "VChart",
    props: ["option", "loading", "autoresize"],
    emits: ["click"],
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

vi.mock("@/composables/useChartTheme.js", () => ({
  useChartTheme: () => ({
    chartTheme: {
      value: {
        color: ["#0a84ff"],
        backgroundColor: "transparent",
        textStyle: { color: "#fff" },
        xAxis: {
          axisLabel: { color: "#ccc" },
          axisLine: { lineStyle: { color: "#333" } },
          splitLine: { lineStyle: { color: "#333", type: "dashed" } },
          axisTick: { lineStyle: { color: "#333" } },
          nameTextStyle: { color: "#ccc" },
        },
        yAxis: {
          axisLabel: { color: "#ccc" },
          axisLine: { lineStyle: { color: "#333" } },
          splitLine: { lineStyle: { color: "#333", type: "dashed" } },
          axisTick: { lineStyle: { color: "#333" } },
          nameTextStyle: { color: "#ccc" },
        },
        tooltip: { backgroundColor: "#111", borderColor: "#333", textStyle: { color: "#fff" } },
        legend: { textStyle: { color: "#ccc" } },
        grid: { borderColor: "#333" },
        _severity: {},
      },
    },
  }),
}));

const stubComponents = {
  "v-alert": { template: "<div><slot /></div>" },
  "v-skeleton-loader": { template: "<div />" },
};

import CcBarChart from "../../../src/components/charts/CcBarChart.vue";

const CATEGORIES = ["Bedroom", "Kitchen", "Bathroom"];
const SERIES = [{ name: "Visits", values: [10, 5, 3] }];

describe("CcBarChart", () => {
  it("includes all categories in xAxis.data", () => {
    const w = mount(CcBarChart, {
      props: { categories: CATEGORIES, series: SERIES },
      global: { stubs: stubComponents },
    });
    expect(w.vm.chartOption.xAxis.data).toEqual(CATEGORIES);
  });

  it("series data aligns with categories", () => {
    const w = mount(CcBarChart, {
      props: { categories: CATEGORIES, series: SERIES },
      global: { stubs: stubComponents },
    });
    expect(w.vm.chartOption.series[0].data).toEqual([10, 5, 3]);
  });

  it("emits 'select' with category name when handleChartClick is called", () => {
    const w = mount(CcBarChart, {
      props: { categories: CATEGORIES, series: SERIES },
      global: { stubs: stubComponents },
    });
    w.vm.handleChartClick({ name: "Kitchen" });
    expect(w.emitted("select")).toBeTruthy();
    expect(w.emitted("select")[0]).toEqual(["Kitchen"]);
  });

  it("does not emit 'select' when params.name is undefined", () => {
    const w = mount(CcBarChart, {
      props: { categories: CATEGORIES, series: SERIES },
      global: { stubs: stubComponents },
    });
    w.vm.handleChartClick({});
    expect(w.emitted("select")).toBeFalsy();
  });

  it("shows empty state when categories or series is empty", () => {
    const w = mount(CcBarChart, {
      props: { categories: [], series: [] },
      global: { stubs: stubComponents },
    });
    expect(w.find('[data-testid="v-chart"]').exists()).toBe(false);
    expect(w.vm.isEmpty).toBe(true);
  });
});
