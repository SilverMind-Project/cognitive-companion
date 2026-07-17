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
        <div class="pa-6 text-center text-medium-emphasis">No timeline events yet</div>
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
import "@/components/charts/echarts.js";
import { useChartTheme } from "@/composables/useChartTheme.js";
import { formatDateTimeShort } from "@/services/timezone.js";

const props = defineProps({
  /** Swimlanes: [{ id: string, label: string }] */
  lanes: {
    type: Array,
    default: () => [],
  },
  /**
   * Events to place on the timeline:
   * [{ laneId: string, t: ISO string, label: string }]
   */
  events: {
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

const isEmpty = computed(() => !props.events?.length || !props.lanes?.length);

const chartOption = computed(() => {
  const th = chartTheme.value;
  const laneLabels = props.lanes.map((l) => l.label);
  const laneIndex = Object.fromEntries(props.lanes.map((l, i) => [l.id, i]));

  // Pre-format time labels via timezone.js so no raw Date methods are used.
  const data = props.events.map((e) => ({
    value: [formatDateTimeShort(e.t), laneIndex[e.laneId] ?? 0],
    name: e.label,
    // Keep raw for tooltip
    _rawT: e.t,
    _lane: e.laneId,
  }));

  return {
    backgroundColor: "transparent",
    textStyle: th.textStyle,
    tooltip: {
      ...th.tooltip,
      formatter: (p) => {
        const d = p.data;
        return `${d.name}<br/>${formatDateTimeShort(d._rawT)}`;
      },
    },
    grid: { left: 80, right: 20, bottom: 40, top: 20 },
    xAxis: {
      type: "category",
      data: [...new Set(data.map((d) => d.value[0]))].sort(),
      ...th.xAxis,
      axisLabel: { ...th.xAxis.axisLabel, rotate: 30 },
    },
    yAxis: {
      type: "category",
      data: laneLabels,
      ...th.yAxis,
    },
    series: [
      {
        type: "scatter",
        data: data.map((d) => ({
          ...d,
          value: [d.value[0], d.value[1]],
        })),
        symbolSize: 10,
        itemStyle: { color: th.color[0] },
        label: {
          show: false,
        },
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
