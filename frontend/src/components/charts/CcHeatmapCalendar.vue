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
        <div class="pa-6 text-center text-medium-emphasis">No activity data yet</div>
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
   * Activity cells: [{ day: 'YYYY-MM-DD', hour: 0-23, value: number }]
   * Sparse input is handled: missing day/hour combinations render as empty.
   */
  cells: {
    type: Array,
    default: () => [],
  },
  /** Label for the visual-map legend. */
  valueLabel: {
    type: String,
    default: "Activity",
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

const isEmpty = computed(() => !props.cells?.length);

const HOURS = Array.from({ length: 24 }, (_, i) => `${i}:00`);

const days = computed(() => {
  const seen = new Set();
  for (const c of props.cells) {
    if (c.day) seen.add(c.day);
  }
  return [...seen].sort();
});

const chartOption = computed(() => {
  const th = chartTheme.value;
  const dayList = days.value;

  const data = props.cells.map((c) => {
    const dayIdx = dayList.indexOf(c.day);
    return [c.hour, dayIdx < 0 ? 0 : dayIdx, c.value ?? 0];
  });

  const maxVal = data.reduce((m, d) => Math.max(m, d[2]), 0) || 1;

  return {
    backgroundColor: "transparent",
    textStyle: th.textStyle,
    tooltip: {
      ...th.tooltip,
      position: "top",
      formatter: (p) => `${p.data[2]} ${props.valueLabel}`,
    },
    grid: { left: 60, right: 20, bottom: 40, top: 20 },
    xAxis: {
      type: "category",
      data: HOURS,
      splitArea: { show: true },
      ...th.xAxis,
      axisLabel: { ...th.xAxis.axisLabel, interval: 2 },
    },
    yAxis: {
      type: "category",
      data: dayList,
      splitArea: { show: true },
      ...th.yAxis,
    },
    visualMap: {
      min: 0,
      max: maxVal,
      calculable: true,
      orient: "horizontal",
      left: "center",
      bottom: 0,
      textStyle: { color: th.textStyle.color },
      inRange: {
        color: [th.color[6] ?? "#ccc", th.color[0] ?? "#0a84ff"],
      },
    },
    series: [
      {
        type: "heatmap",
        data,
        label: { show: false },
        emphasis: { itemStyle: { shadowBlur: 10 } },
      },
    ],
  };
});

defineExpose({ chartOption, isEmpty, days });
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
