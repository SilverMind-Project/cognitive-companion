/**
 * U3-T8: Error state across all chart components
 *
 * Every chart component must render its error state (not an empty chart)
 * when passed an `error` prop. This prevents silent failures where a
 * failed U2 envelope fetch renders a blank chart with no feedback.
 */
import { describe, it, expect, vi } from "vitest";
import { mount } from "@vue/test-utils";

// ── Mock heavy dependencies ───────────────────────────────────────────────

vi.mock("vue-echarts", () => ({
  default: {
    name: "VChart",
    props: ["option", "loading", "autoresize"],
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

const THEME_STUB = {
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
      _severity: {
        running: "#0a84ff",
        succeeded: "#30d158",
        failed: "#ff453a",
        skipped: "#6e6e73",
        pending: "#a1a1a6",
        warning: "#ff9500",
      },
    },
  },
};

vi.mock("@/composables/useChartTheme.js", () => ({
  useChartTheme: () => THEME_STUB,
}));

vi.mock("@/services/timezone.js", () => ({
  formatDateTimeShort: (iso) => iso,
}));

const stubComponents = {
  "v-alert": {
    template: '<div data-testid="v-alert" class="v-alert"><slot /></div>',
    props: ["type", "variant", "density"],
  },
  "v-skeleton-loader": { template: "<div />" },
};

import CcTimeSeriesChart from "../../../src/components/charts/CcTimeSeriesChart.vue";
import CcBarChart from "../../../src/components/charts/CcBarChart.vue";
import CcHeatmapCalendar from "../../../src/components/charts/CcHeatmapCalendar.vue";
import CcDistributionChart from "../../../src/components/charts/CcDistributionChart.vue";
import CcScatterFloorCloud from "../../../src/components/charts/CcScatterFloorCloud.vue";
import CcGaugeChart from "../../../src/components/charts/CcGaugeChart.vue";
import CcDagChart from "../../../src/components/process/CcDagChart.vue";
import CcStatusTimeline from "../../../src/components/process/CcStatusTimeline.vue";

const ERROR_MSG = "CTS orchestrator unavailable";

const CHART_CASES = [
  { name: "CcTimeSeriesChart", Component: CcTimeSeriesChart, props: {} },
  { name: "CcBarChart", Component: CcBarChart, props: {} },
  { name: "CcHeatmapCalendar", Component: CcHeatmapCalendar, props: {} },
  { name: "CcDistributionChart", Component: CcDistributionChart, props: {} },
  { name: "CcScatterFloorCloud", Component: CcScatterFloorCloud, props: {} },
  { name: "CcGaugeChart", Component: CcGaugeChart, props: {} },
  { name: "CcDagChart", Component: CcDagChart, props: {} },
  { name: "CcStatusTimeline", Component: CcStatusTimeline, props: {} },
];

describe("Chart error states", () => {
  for (const { name, Component, props } of CHART_CASES) {
    it(`${name}: renders error state when error prop is set`, () => {
      const w = mount(Component, {
        props: { ...props, error: ERROR_MSG },
        global: { stubs: stubComponents },
      });
      // The chart must not render
      expect(w.find('[data-testid="v-chart"]').exists()).toBe(false);
      // An alert element must be present (error is surfaced explicitly)
      expect(w.find('[data-testid="v-alert"]').exists()).toBe(true);
      // The error message text must be visible
      expect(w.text()).toContain(ERROR_MSG);
    });

    it(`${name}: does NOT render a misleading empty chart on error`, () => {
      const w = mount(Component, {
        props: { ...props, error: ERROR_MSG },
        global: { stubs: stubComponents },
      });
      expect(w.find('[data-testid="v-chart"]').exists()).toBe(false);
    });
  }
});
