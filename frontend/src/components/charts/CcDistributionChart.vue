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
        <div class="pa-6 text-center text-medium-emphasis">No distribution data yet</div>
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

const props = defineProps({
  /**
   * Histogram bins: [{ from: number, to: number, count: number }]
   * Renders as a bar per bin; the bin label is the midpoint.
   */
  bins: {
    type: Array,
    default: () => [],
  },
  /** X-axis unit label. */
  unit: {
    type: String,
    default: "",
  },
  loading: {
    type: Boolean,
    default: false,
  },
  error: {
    type: String,
    default: null,
  },
});

const { chartTheme } = useChartTheme();

const isEmpty = computed(() => !props.bins?.length);

const chartOption = computed(() => {
  const th = chartTheme.value;
  const labels = props.bins.map(
    (b) => `${b.from}${props.unit ? " " + props.unit : ""}`
  );
  const counts = props.bins.map((b) => b.count);

  return {
    color: th.color,
    backgroundColor: "transparent",
    textStyle: th.textStyle,
    tooltip: {
      ...th.tooltip,
      trigger: "axis",
      formatter: (params) => {
        const b = props.bins[params[0].dataIndex];
        if (!b) return "";
        return `${b.from}–${b.to}${props.unit ? " " + props.unit : ""}: ${b.count}`;
      },
    },
    grid: { left: "3%", right: "4%", bottom: "3%", containLabel: true },
    xAxis: {
      type: "category",
      data: labels,
      name: props.unit,
      ...th.xAxis,
    },
    yAxis: {
      type: "value",
      name: "Count",
      ...th.yAxis,
    },
    series: [
      {
        type: "bar",
        data: counts,
        barCategoryGap: "10%",
        itemStyle: { color: th.color[0] },
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
  height: 100%;
}

.cc-chart-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 120px;
}
</style>
