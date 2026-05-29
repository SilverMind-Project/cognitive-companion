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
        <div class="pa-6 text-center text-medium-emphasis">No data yet</div>
      </slot>
    </div>
    <v-chart
      v-else
      :option="chartOption"
      autoresize
      style="width: 100%; height: 100%; min-height: 200px"
    />
  </div>
</template>

<script setup>
import { computed } from "vue";
import VChart from "vue-echarts";
import "../charts/echarts.js";
import { useChartTheme } from "@/composables/useChartTheme.js";
import { formatDateTimeShort } from "@/services/timezone.js";

const props = defineProps({
  /** List of named series. Each point has { t: ISO string, v: number }. */
  series: {
    type: Array,
    default: () => [],
  },
  /** Y-axis unit label. */
  unit: {
    type: String,
    default: "",
  },
  /** Optional horizontal threshold markers: [{ value: number, name: string }] */
  thresholds: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
  /** Pass a string to render the error state instead of the chart. */
  error: {
    type: String,
    default: null,
  },
});

const { chartTheme } = useChartTheme();

const isEmpty = computed(
  () => !props.series || props.series.every((s) => !s.points?.length)
);

// Pre-format time labels via timezone.js so no toLocaleString or new Date methods
// are used in the chart rendering path. Tests can mock formatDateTimeShort to
// verify the call.
const xLabels = computed(() => {
  const firstSeries = props.series[0];
  if (!firstSeries?.points?.length) return [];
  return firstSeries.points.map((p) => formatDateTimeShort(p.t));
});

const chartOption = computed(() => {
  const th = chartTheme.value;
  const markLineData = props.thresholds.map((t) => ({
    yAxis: t.value,
    name: t.name,
    lineStyle: { color: th._severity.warning, type: "dashed" },
    label: { formatter: `{b}: ${t.value}`, color: th.textStyle.color },
  }));

  return {
    color: th.color,
    backgroundColor: "transparent",
    textStyle: th.textStyle,
    tooltip: {
      ...th.tooltip,
      trigger: "axis",
    },
    legend: {
      ...th.legend,
      show: props.series.length > 1,
    },
    grid: { left: "3%", right: "4%", bottom: "3%", containLabel: true },
    xAxis: {
      type: "category",
      data: xLabels.value,
      ...th.xAxis,
    },
    yAxis: {
      type: "value",
      name: props.unit,
      ...th.yAxis,
    },
    series: props.series.map((s) => ({
      name: s.name,
      type: "line",
      data: s.points?.map((p) => p.v) ?? [],
      smooth: true,
      areaStyle: { opacity: 0.1 },
      markLine:
        markLineData.length && s === props.series[0]
          ? { data: markLineData, silent: true }
          : undefined,
    })),
  };
});

defineExpose({ chartOption, isEmpty });
</script>

<style scoped>
.cc-chart-wrapper {
  position: relative;
  width: 100%;
  height: 100%;
}

.cc-chart-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 120px;
}
</style>
