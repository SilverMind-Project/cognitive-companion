import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";

vi.mock("vue-echarts", () => ({
  default: {
    name: "VChart",
    props: ["option", "theme", "autoresize"],
    emits: ["click"],
    template: '<button data-testid="v-chart" @click="$emit(\'click\', { data: option.series[1].data[0] })" />',
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

const TOKEN_THEME = {
  textStyle: { color: "var(--cc-text-1)" },
  tooltip: {},
  xAxis: { axisLabel: {} },
  yAxis: { axisLabel: {} },
  _severity: {
    pending: "var(--cc-text-2)",
    succeeded: "var(--cc-success)",
    warning: "var(--cc-warning)",
    error: "var(--cc-error)",
    info: "var(--cc-info)",
  },
};

vi.mock("@/composables/useChartTheme.js", () => ({
  useChartTheme: () => ({
    chartTheme: { value: TOKEN_THEME },
  }),
}));

import CcQueueDepthChart from "@/components/charts/CcQueueDepthChart.vue";

const cameras = [{
  camera_id: "camera-1",
  label: "CTS - Hallway",
  origin: "cts",
  buffer_depth: 8,
  buffer_capacity: 20,
  images_eligible_total: 90,
  images_dropped_total: 10,
  tokens_available: 1.5,
  rate_per_second: 1,
}];

const stubs = {
  "v-progress-circular": { template: "<div data-testid='spinner' />" },
};

describe("CcQueueDepthChart", () => {
  it("mounts with a cameras fixture", () => {
    const wrapper = mount(CcQueueDepthChart, {
      props: { cameras, theme: TOKEN_THEME },
      global: { stubs },
    });

    expect(wrapper.find('[data-testid="v-chart"]').exists()).toBe(true);
  });

  it("passes the supplied useChartTheme object to v-chart", () => {
    const wrapper = mount(CcQueueDepthChart, {
      props: { cameras, theme: TOKEN_THEME },
      global: { stubs },
    });

    expect(wrapper.findComponent({ name: "VChart" }).props("theme")).toStrictEqual(TOKEN_THEME);
  });

  it("emits select with the camera id on bar click", async () => {
    const wrapper = mount(CcQueueDepthChart, {
      props: { cameras, theme: TOKEN_THEME },
      global: { stubs },
    });

    await wrapper.find('[data-testid="v-chart"]').trigger("click");

    expect(wrapper.emitted("select")).toEqual([["camera-1"]]);
  });

  it("renders the empty state when cameras is empty", () => {
    const wrapper = mount(CcQueueDepthChart, {
      props: { cameras: [], theme: TOKEN_THEME },
      global: { stubs },
    });

    expect(wrapper.text()).toContain("No cameras match these filters.");
    expect(wrapper.find('[data-testid="v-chart"]').exists()).toBe(false);
  });

  it("computes pressure colors from theme tokens", () => {
    const wrapper = mount(CcQueueDepthChart, {
      props: { cameras, theme: TOKEN_THEME },
      global: { stubs },
    });

    expect(wrapper.vm.pressureColor(cameras[0])).toBe("var(--cc-warning)");
    expect(wrapper.vm.chartOption.series[1].data[0].itemStyle.color).not.toMatch(/^#/);
  });
});
