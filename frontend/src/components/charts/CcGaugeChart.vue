<template>
  <div class="cc-chart-wrapper">
    <div v-if="error" class="cc-chart-state">
      <v-alert type="error" variant="tonal" density="compact" class="ma-2">
        {{ error }}
      </v-alert>
    </div>
    <div v-else-if="loading" class="cc-chart-state">
      <v-skeleton-loader type="image" height="160" />
    </div>
    <div v-else-if="isEmpty" class="cc-chart-state">
      <slot name="empty">
        <div class="pa-6 text-center text-medium-emphasis">No value</div>
      </slot>
    </div>
    <v-chart
      v-else
      :option="chartOption"
      autoresize
      style="width: 100%; height: 100%; min-height: 160px"
    />
  </div>
</template>

<script setup>
import { computed } from "vue";
import VChart from "vue-echarts";
import "../charts/echarts.js";
import { useChartTheme } from "@/composables/useChartTheme.js";

const props = defineProps({
  /** Current value (must be within [min, max]). Pass null to show empty state. */
  value: {
    type: Number,
    default: null,
  },
  min: {
    type: Number,
    default: 0,
  },
  max: {
    type: Number,
    default: 100,
  },
  label: {
    type: String,
    default: "",
  },
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

const isEmpty = computed(() => props.value === null || props.value === undefined);

const chartOption = computed(() => {
  const th = chartTheme.value;
  const pct = ((props.value - props.min) / (props.max - props.min)) * 100;
  const color =
    pct >= 80
      ? th._severity.succeeded
      : pct >= 50
        ? th.color[0]
        : pct >= 30
          ? th._severity.warning
          : th._severity.failed;

  return {
    backgroundColor: "transparent",
    series: [
      {
        type: "gauge",
        min: props.min,
        max: props.max,
        data: [
          {
            value: props.value,
            name: props.label,
          },
        ],
        detail: {
          formatter: `{value}${props.unit}`,
          color: th.textStyle.color,
          fontSize: 18,
          fontWeight: "600",
        },
        title: {
          color: th.tooltip.textStyle.color,
          fontSize: 12,
        },
        axisLabel: { color: th.xAxis.axisLabel.color },
        axisLine: {
          lineStyle: {
            color: [[1, color]],
            width: 10,
          },
        },
        splitLine: { lineStyle: { color: th.xAxis.axisLine.lineStyle.color } },
        axisTick: { lineStyle: { color: th.xAxis.axisLine.lineStyle.color } },
        pointer: { itemStyle: { color } },
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
