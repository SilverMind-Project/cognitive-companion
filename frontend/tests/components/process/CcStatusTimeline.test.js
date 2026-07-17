/**
 * U3-T6: CcStatusTimeline
 *
 * Verifies: events are placed on the correct lane and time position;
 * time labels are localised via timezone.js (never raw Date methods).
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
          axisLabel: { color: "#ccc", rotate: 0 },
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
        _severity: {},
      },
    },
  }),
}));

// Spy on timezone.js to assert it is called for time formatting.
const fmtSpy = vi.fn((iso) => `TZ(${iso})`);
vi.mock("@/services/timezone.js", () => ({
  formatDateTimeShort: (iso) => fmtSpy(iso),
}));

const stubComponents = {
  "v-alert": { template: '<div data-testid="v-alert"><slot /></div>' },
  "v-skeleton-loader": { template: "<div />" },
};

import CcStatusTimeline from "../../../src/components/process/CcStatusTimeline.vue";

const LANES = [
  { id: "camera-1", label: "Camera 1" },
  { id: "pipeline", label: "Pipeline" },
];

const EVENTS = [
  { laneId: "camera-1", t: "2026-05-29T10:00:00Z", label: "Frame A" },
  { laneId: "pipeline", t: "2026-05-29T10:01:00Z", label: "Step ran" },
  { laneId: "camera-1", t: "2026-05-29T10:02:00Z", label: "Frame B" },
];

describe("CcStatusTimeline", () => {
  it("renders chart when lanes and events are provided", () => {
    fmtSpy.mockClear();
    const w = mount(CcStatusTimeline, {
      props: { lanes: LANES, events: EVENTS },
      global: { stubs: stubComponents },
    });
    expect(w.find('[data-testid="v-chart"]').exists()).toBe(true);
  });

  it("yAxis.data contains lane labels", () => {
    const w = mount(CcStatusTimeline, {
      props: { lanes: LANES, events: EVENTS },
      global: { stubs: stubComponents },
    });
    const yLabels = w.vm.chartOption.yAxis.data;
    expect(yLabels).toContain("Camera 1");
    expect(yLabels).toContain("Pipeline");
  });

  it("series data has one point per event", () => {
    const w = mount(CcStatusTimeline, {
      props: { lanes: LANES, events: EVENTS },
      global: { stubs: stubComponents },
    });
    expect(w.vm.chartOption.series[0].data).toHaveLength(EVENTS.length);
  });

  it("time labels are formatted via timezone.js formatDateTimeShort", () => {
    fmtSpy.mockClear();
    const w = mount(CcStatusTimeline, {
      props: { lanes: LANES, events: EVENTS },
      global: { stubs: stubComponents },
    });
    // The composable pre-formats timestamps; verify fmtSpy was called
    expect(fmtSpy).toHaveBeenCalledWith("2026-05-29T10:00:00Z");
    expect(fmtSpy).toHaveBeenCalledWith("2026-05-29T10:01:00Z");
    expect(fmtSpy).toHaveBeenCalledWith("2026-05-29T10:02:00Z");
    // x-axis data must contain the formatted string, not the raw ISO
    const xData = w.vm.chartOption.xAxis.data;
    for (const t of ["2026-05-29T10:00:00Z", "2026-05-29T10:01:00Z", "2026-05-29T10:02:00Z"]) {
      expect(xData).toContain(`TZ(${t})`);
    }
  });

  it("camera-1 events map to y-index 0 (first lane)", () => {
    const w = mount(CcStatusTimeline, {
      props: { lanes: LANES, events: EVENTS },
      global: { stubs: stubComponents },
    });
    const seriesData = w.vm.chartOption.series[0].data;
    // First event: camera-1 → y-index 0
    expect(seriesData[0].value[1]).toBe(0);
    // Second event: pipeline → y-index 1
    expect(seriesData[1].value[1]).toBe(1);
  });

  it("shows empty state when events list is empty", () => {
    const w = mount(CcStatusTimeline, {
      props: { lanes: LANES, events: [] },
      global: { stubs: stubComponents },
    });
    expect(w.vm.isEmpty).toBe(true);
  });
});
