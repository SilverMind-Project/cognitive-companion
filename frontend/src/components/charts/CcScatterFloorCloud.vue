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
        <div class="pa-6 text-center text-medium-emphasis">No position data yet</div>
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
   * Floor position cloud: [{ x: number, y: number, quality: number (0–1) }]
   * Quality maps to point opacity and size.
   */
  points: {
    type: Array,
    default: () => [],
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

const isEmpty = computed(() => !props.points?.length);

const chartOption = computed(() => {
  const th = chartTheme.value;

  const data = props.points.map((p) => ({
    value: [p.x, p.y],
    symbolSize: 6 + (p.quality ?? 0.5) * 10,
    itemStyle: {
      color: th.color[0],
      opacity: 0.3 + (p.quality ?? 0.5) * 0.7,
    },
  }));

  return {
    backgroundColor: "transparent",
    textStyle: th.textStyle,
    tooltip: {
      ...th.tooltip,
      formatter: (p) => `x: ${p.value[0].toFixed(2)}, y: ${p.value[1].toFixed(2)}`,
    },
    grid: { left: "3%", right: "4%", bottom: "3%", containLabel: true },
    xAxis: { type: "value", scale: true, ...th.xAxis },
    yAxis: { type: "value", scale: true, ...th.yAxis },
    series: [
      {
        type: "scatter",
        data,
        large: true,
        largeThreshold: 500,
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
