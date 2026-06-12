<template>
  <div class="cc-chart-wrapper">
    <div v-if="error" class="cc-chart-state">
      <v-alert type="error" variant="tonal" density="compact" class="ma-2">
        {{ error }}
      </v-alert>
    </div>
    <div v-else-if="loading" class="cc-chart-state">
      <v-skeleton-loader type="image" height="200" />
    </div>
    <div v-else-if="isEmpty" class="cc-chart-state">
      <slot name="empty">
        <div class="pa-6 text-center text-medium-emphasis">No mobility data yet</div>
      </slot>
    </div>
    <v-chart
      v-else
      :theme="theme"
      :option="chartOption"
      autoresize
      style="width: 100%; height: 260px"
    />
  </div>
</template>

<script setup>
import { computed } from "vue";
import VChart from "vue-echarts";
import "./echarts.js";
import { useChartTheme } from "@/composables/useChartTheme.js";

const props = defineProps({
  /**
   * Array of daily data points: { date: string, value: number|null, sufficient: boolean }
   * Null value → gap (insufficient day).
   */
  points: {
    type: Array,
    default: () => [],
  },
  /** Baseline median speed in m/s; renders as a horizontal reference line. */
  baselineValue: {
    type: Number,
    default: null,
  },
  /** ISO date strings where gait_slowing signals fired. */
  signalDates: {
    type: Array,
    default: () => [],
  },
  loading: { type: Boolean, default: false },
  error: { type: String, default: null },
});

const { theme, chartTheme } = useChartTheme();

const isEmpty = computed(() => !props.points || props.points.length === 0);

const chartOption = computed(() => {
  const th = chartTheme.value;
  const dates = props.points.map((p) => p.date);
  const speeds = props.points.map((p) => (p.sufficient ? p.value : null));

  const signalDateSet = new Set(props.signalDates);

  const markPoints = props.points
    .filter((p) => signalDateSet.has(p.date) && p.sufficient)
    .map((p) => ({
      name: "Gait slowing",
      coord: [p.date, p.value],
      symbol: "triangle",
      symbolSize: 10,
      itemStyle: { color: th._severity?.warning || "var(--cc-warning)" },
      label: { show: false },
    }));

  const markLines = [];
  if (props.baselineValue != null) {
    markLines.push({
      yAxis: props.baselineValue,
      name: "Baseline",
      lineStyle: { color: th.color?.[1] || "var(--cc-brand)", type: "dashed", width: 1 },
      label: {
        formatter: `Baseline ${props.baselineValue.toFixed(2)} m/s`,
        color: th.textStyle?.color || "var(--cc-text-2)",
        fontSize: 11,
      },
    });
  }

  return {
    color: th.color,
    backgroundColor: "transparent",
    textStyle: th.textStyle,
    tooltip: {
      ...th.tooltip,
      trigger: "axis",
      formatter: (params) => {
        const p = params[0];
        if (p.value == null) return `${p.name}<br/>Insufficient data`;
        return `${p.name}<br/>Speed: <b>${Number(p.value).toFixed(2)} m/s</b>`;
      },
    },
    grid: { left: "3%", right: "5%", bottom: "3%", top: "10%", containLabel: true },
    xAxis: {
      type: "category",
      data: dates,
      ...th.xAxis,
      axisLabel: {
        ...th.xAxis?.axisLabel,
        rotate: 30,
        interval: Math.floor(dates.length / 8),
      },
    },
    yAxis: {
      type: "value",
      name: "m/s",
      min: 0,
      ...th.yAxis,
    },
    series: [
      {
        name: "Daily speed",
        type: "line",
        data: speeds,
        smooth: false,
        connectNulls: false,
        symbol: "circle",
        symbolSize: 5,
        lineStyle: { width: 2 },
        markLine: markLines.length
          ? { data: markLines, silent: true, symbol: ["none", "none"] }
          : undefined,
        markPoint: markPoints.length
          ? { data: markPoints, silent: true }
          : undefined,
      },
    ],
  };
});

defineExpose({ chartOption, isEmpty });
</script>

<style scoped>
.cc-chart-wrapper {
  position: relative;
  width: 100%;
}

.cc-chart-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 120px;
}
</style>
