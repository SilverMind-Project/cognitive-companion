/**
 * U3-T3: CcHeatmapCalendar
 *
 * Verifies: day×hour data maps to cells; sparse input does not throw.
 */
import { describe, it, expect, vi } from "vitest";
import { mount } from "@vue/test-utils";

vi.mock("vue-echarts", () => ({
  default: {
    name: "VChart",
    props: ["option", "loading", "autoresize"],
    template: '<div data-testid="v-chart" />',
  },
}));
vi.mock("echarts/core", () => ({ use: vi.fn() }));
vi.mock("echarts/renderers", () => ({ CanvasRenderer: {} }));
vi.mock("echarts/charts", () => ({ LineChart: {}, BarChart: {}, HeatmapChart: {}, ScatterChart: {}, GaugeChart: {}, GraphChart: {} }));
vi.mock("echarts/components", () => ({ GridComponent: {}, TooltipComponent: {}, LegendComponent: {}, MarkLineComponent: {}, VisualMapComponent: {}, DataZoomComponent: {}, TitleComponent: {} }));

vi.mock("@/composables/useChartTheme.js", () => ({
  useChartTheme: () => ({
    chartTheme: {
      value: {
        color: ["#ff453a", "#0a84ff"],
        backgroundColor: "transparent",
        textStyle: { color: "#fff" },
        xAxis: { axisLabel: { color: "#ccc" }, axisLine: { lineStyle: { color: "#333" } }, splitLine: { lineStyle: { color: "#333", type: "dashed" } }, axisTick: { lineStyle: { color: "#333" } }, nameTextStyle: { color: "#ccc" } },
        yAxis: { axisLabel: { color: "#ccc" }, axisLine: { lineStyle: { color: "#333" } }, splitLine: { lineStyle: { color: "#333", type: "dashed" } }, axisTick: { lineStyle: { color: "#333" } }, nameTextStyle: { color: "#ccc" } },
        tooltip: { backgroundColor: "#111", borderColor: "#333", textStyle: { color: "#fff" } },
        _severity: {},
      },
    },
  }),
}));

const stubComponents = {
  "v-alert": { template: "<div><slot /></div>" },
  "v-skeleton-loader": { template: "<div />" },
};

import CcHeatmapCalendar from "../../../src/components/charts/CcHeatmapCalendar.vue";

const FULL_WEEK = [
  { day: "2026-05-25", hour: 22, value: 3 },
  { day: "2026-05-25", hour: 23, value: 5 },
  { day: "2026-05-26", hour: 0, value: 1 },
  { day: "2026-05-26", hour: 3, value: 7 },
];

const SPARSE_WEEK = [
  { day: "2026-05-28", hour: 2, value: 9 },
];

describe("CcHeatmapCalendar", () => {
  it("renders chart when cells are provided", () => {
    const w = mount(CcHeatmapCalendar, {
      props: { cells: FULL_WEEK },
      global: { stubs: stubComponents },
    });
    expect(w.find('[data-testid="v-chart"]').exists()).toBe(true);
  });

  it("yAxis.data contains all unique days from cells", () => {
    const w = mount(CcHeatmapCalendar, {
      props: { cells: FULL_WEEK },
      global: { stubs: stubComponents },
    });
    const yDays = w.vm.chartOption.yAxis.data;
    expect(yDays).toContain("2026-05-25");
    expect(yDays).toContain("2026-05-26");
  });

  it("series data count matches number of cells", () => {
    const w = mount(CcHeatmapCalendar, {
      props: { cells: FULL_WEEK },
      global: { stubs: stubComponents },
    });
    expect(w.vm.chartOption.series[0].data).toHaveLength(FULL_WEEK.length);
  });

  it("handles a sparse week (single cell) without throwing", () => {
    expect(() => {
      const w = mount(CcHeatmapCalendar, {
        props: { cells: SPARSE_WEEK },
        global: { stubs: stubComponents },
      });
      // Access the option to trigger the computed
      void w.vm.chartOption;
    }).not.toThrow();
  });

  it("shows empty state when cells array is empty", () => {
    const w = mount(CcHeatmapCalendar, {
      props: { cells: [] },
      global: { stubs: stubComponents },
    });
    expect(w.vm.isEmpty).toBe(true);
    expect(w.find('[data-testid="v-chart"]').exists()).toBe(false);
  });

  it("xAxis has 24 hour slots", () => {
    const w = mount(CcHeatmapCalendar, {
      props: { cells: FULL_WEEK },
      global: { stubs: stubComponents },
    });
    expect(w.vm.chartOption.xAxis.data).toHaveLength(24);
  });
});
