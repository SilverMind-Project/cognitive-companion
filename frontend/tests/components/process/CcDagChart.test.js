/**
 * U3-T5: CcDagChart
 *
 * Verifies: nodes and edges appear in the ECharts option; the activeNodeId
 * node carries the running color (not the pending color).
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

const RUNNING_COLOR = "#BRAND-SENTINEL";
const SUCCEEDED_COLOR = "#SUCCESS-SENTINEL";
const FAILED_COLOR = "#FAIL-SENTINEL";
const PENDING_COLOR = "#PENDING-SENTINEL";

vi.mock("@/composables/useChartTheme.js", () => ({
  useChartTheme: () => ({
    chartTheme: {
      value: {
        color: [RUNNING_COLOR],
        backgroundColor: "transparent",
        textStyle: { color: "#fff" },
        grid: { borderColor: "#333" },
        xAxis: { axisLine: { lineStyle: { color: "#333" } } },
        tooltip: { backgroundColor: "#111", borderColor: "#333", textStyle: { color: "#fff" } },
        _severity: {
          running: RUNNING_COLOR,
          succeeded: SUCCEEDED_COLOR,
          failed: FAILED_COLOR,
          pending: PENDING_COLOR,
          skipped: "#ccc",
        },
      },
    },
  }),
}));

const stubComponents = {
  "v-alert": { template: '<div data-testid="v-alert"><slot /></div>' },
  "v-skeleton-loader": { template: "<div />" },
};

import CcDagChart from "../../../src/components/process/CcDagChart.vue";

const NODES = [
  { id: "step-1", label: "Ingest", status: "succeeded" },
  { id: "step-2", label: "Detect", status: "running" },
  { id: "step-3", label: "Alert", status: "pending" },
];

const EDGES = [
  { source: "step-1", target: "step-2" },
  { source: "step-2", target: "step-3" },
];

describe("CcDagChart", () => {
  it("renders chart when nodes are provided", () => {
    const w = mount(CcDagChart, {
      props: { nodes: NODES, edges: EDGES },
      global: { stubs: stubComponents },
    });
    expect(w.find('[data-testid="v-chart"]').exists()).toBe(true);
  });

  it("option.series[0].data contains all nodes", () => {
    const w = mount(CcDagChart, {
      props: { nodes: NODES, edges: EDGES },
      global: { stubs: stubComponents },
    });
    const graphData = w.vm.chartOption.series[0].data;
    expect(graphData).toHaveLength(NODES.length);
    const ids = graphData.map((n) => n.id);
    expect(ids).toContain("step-1");
    expect(ids).toContain("step-2");
    expect(ids).toContain("step-3");
  });

  it("option.series[0].edges contains all edges", () => {
    const w = mount(CcDagChart, {
      props: { nodes: NODES, edges: EDGES },
      global: { stubs: stubComponents },
    });
    const graphEdges = w.vm.chartOption.series[0].edges;
    expect(graphEdges).toHaveLength(EDGES.length);
  });

  it("activeNodeId node uses the running color", () => {
    const w = mount(CcDagChart, {
      props: { nodes: NODES, edges: EDGES, activeNodeId: "step-1" },
      global: { stubs: stubComponents },
    });
    const graphData = w.vm.chartOption.series[0].data;
    const activeNode = graphData.find((n) => n.id === "step-1");
    expect(activeNode.itemStyle.color).toBe(RUNNING_COLOR);
  });

  it("node with status='running' uses the running color even without activeNodeId", () => {
    const w = mount(CcDagChart, {
      props: { nodes: NODES, edges: EDGES },
      global: { stubs: stubComponents },
    });
    const graphData = w.vm.chartOption.series[0].data;
    const runningNode = graphData.find((n) => n.id === "step-2");
    expect(runningNode.itemStyle.color).toBe(RUNNING_COLOR);
  });

  it("node with status='succeeded' uses succeeded color", () => {
    const w = mount(CcDagChart, {
      props: { nodes: NODES, edges: EDGES },
      global: { stubs: stubComponents },
    });
    const graphData = w.vm.chartOption.series[0].data;
    const succeededNode = graphData.find((n) => n.id === "step-1");
    expect(succeededNode.itemStyle.color).toBe(SUCCEEDED_COLOR);
  });

  it("shows empty state when nodes is empty", () => {
    const w = mount(CcDagChart, {
      props: { nodes: [], edges: [] },
      global: { stubs: stubComponents },
    });
    expect(w.vm.isEmpty).toBe(true);
  });

  it("uses a deterministic dagre layout", () => {
    const w = mount(CcDagChart, {
      props: { nodes: NODES, edges: EDGES },
      global: { stubs: stubComponents },
    });
    const series = w.vm.chartOption.series[0];
    expect(series.layout).toBe("none");
    expect(series.data[0].x).toEqual(expect.any(Number));
    expect(series.data[0].y).toEqual(expect.any(Number));
  });

  it("colors active edges with success color when in activeEdges set", () => {
    const w = mount(CcDagChart, {
      props: {
        nodes: NODES,
        edges: [{ source: "step-1", sourceHandle: "true", target: "step-2" }],
        activeEdges: new Set(["step-1:true"]),
      },
      global: { stubs: stubComponents },
    });
    const edge = w.vm.chartOption.series[0].edges[0];
    expect(edge.lineStyle.color).toBe(SUCCEEDED_COLOR);
    expect(edge.lineStyle.width).toBe(3);
  });

  it("shows port label on edges with non-main sourceHandle", () => {
    const w = mount(CcDagChart, {
      props: {
        nodes: NODES,
        edges: [{ source: "step-1", sourceHandle: "false", target: "step-2" }],
      },
      global: { stubs: stubComponents },
    });
    const edge = w.vm.chartOption.series[0].edges[0];
    expect(edge.label.show).toBe(true);
    expect(edge.label.formatter).toBe("false");
  });

  it("includes elapsed_ms in tooltip text when nodeTimings provided", () => {
    const w = mount(CcDagChart, {
      props: { nodes: NODES, edges: EDGES, nodeTimings: { "step-1": 1500 } },
      global: { stubs: stubComponents },
    });
    const tooltipText = w.vm.chartOption.tooltip.formatter({
      dataType: "node",
      name: "Ingest",
      data: { id: "step-1", _status: "succeeded" },
    });
    expect(tooltipText).toContain("1.5s");
  });
});
