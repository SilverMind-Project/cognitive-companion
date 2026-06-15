<template>
  <div class="cc-queue-depth-chart">
    <div v-if="loading" class="cc-chart-state">
      <v-progress-circular indeterminate color="primary" />
    </div>
    <div v-else-if="!cameras.length" class="cc-chart-state text-medium-emphasis">
      No cameras match these filters.
    </div>
    <v-chart
      v-else
      :theme="theme"
      :option="chartOption"
      autoresize
      :style="{ width: '100%', height: chartHeight }"
      @click="onChartClick"
    />
  </div>
</template>

<script setup>
/**
 * CcQueueDepthChart
 * @prop {Array<Object>} cameras - one row per camera:
 *   { camera_id, label, origin, buffer_depth, buffer_capacity,
 *     images_eligible_total, images_dropped_total, tokens_available, rate_per_second }
 * @prop {Object} theme - the object from useChartTheme(); REQUIRED.
 * @emits select - (camera_id) when a bar is clicked (drill-in).
 */
import { computed } from "vue";
import VChart from "vue-echarts";
import "./echarts.js";
import { useChartTheme } from "@/composables/useChartTheme.js";

const props = defineProps({
  cameras: {
    type: Array,
    default: () => [],
  },
  theme: {
    type: Object,
    required: true,
  },
  loading: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["select"]);
const { chartTheme } = useChartTheme();

const chartHeight = computed(() => `${Math.max(240, props.cameras.length * 34 + 80)}px`);

function dropRatio(camera) {
  const eligible = Number(camera.images_eligible_total) || 0;
  const dropped = Number(camera.images_dropped_total) || 0;
  const total = eligible + dropped;
  return total > 0 ? dropped / total : 0;
}

function pressureColor(camera) {
  const ratio = dropRatio(camera);
  const severity = chartTheme.value._severity;
  if (ratio >= 0.5) return severity.error;
  if (ratio >= 0.1) return severity.warning;
  return severity.succeeded;
}

const chartOption = computed(() => {
  const th = chartTheme.value;
  const labels = props.cameras.map((camera) => camera.label);
  const capacities = props.cameras.map((camera) =>
    Math.max(Number(camera.buffer_capacity) || 0, Number(camera.buffer_depth) || 0)
  );

  return {
    backgroundColor: "transparent",
    textStyle: th.textStyle,
    tooltip: {
      ...th.tooltip,
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (params) => {
        const camera = props.cameras[params[0]?.dataIndex];
        if (!camera) return "";
        const capacity = camera.buffer_capacity == null ? "unbounded" : camera.buffer_capacity;
        const tokens = camera.tokens_available == null
          ? "n/a"
          : Number(camera.tokens_available).toFixed(1);
        return [
          `<strong>${camera.label}</strong>`,
          `Buffered: ${camera.buffer_depth} / ${capacity}`,
          `Image drop pressure: ${(dropRatio(camera) * 100).toFixed(1)}%`,
          `Tokens available: ${tokens}`,
        ].join("<br>");
      },
    },
    grid: { left: 16, right: 28, top: 16, bottom: 28, containLabel: true },
    xAxis: {
      type: "value",
      minInterval: 1,
      ...th.xAxis,
    },
    yAxis: {
      type: "category",
      data: labels,
      inverse: true,
      ...th.yAxis,
      axisLabel: {
        ...th.yAxis?.axisLabel,
        width: 180,
        overflow: "truncate",
      },
    },
    series: [
      {
        name: "Capacity",
        type: "bar",
        data: capacities,
        barWidth: 14,
        barGap: "-100%",
        silent: true,
        itemStyle: {
          color: th._severity.info,
          opacity: 0.18,
          borderRadius: 7,
        },
      },
      {
        name: "Buffered",
        type: "bar",
        data: props.cameras.map((camera) => ({
          value: camera.buffer_depth,
          cameraId: camera.camera_id,
          itemStyle: {
            color: pressureColor(camera),
            borderRadius: 7,
          },
        })),
        barWidth: 14,
        z: 2,
      },
      {
        name: "Tokens",
        type: "scatter",
        symbol: "diamond",
        symbolSize: 9,
        data: props.cameras
          .map((camera, index) => {
            if (camera.tokens_available == null) return null;
            return {
              value: [camera.buffer_depth, index],
              cameraId: camera.camera_id,
              itemStyle: { color: th._severity.pending },
            };
          })
          .filter(Boolean),
        z: 3,
      },
    ],
  };
});

function onChartClick(params) {
  const cameraId = params?.data?.cameraId;
  if (cameraId) emit("select", cameraId);
}

defineExpose({ chartOption, pressureColor, onChartClick });
</script>

<style scoped>
.cc-queue-depth-chart {
  width: 100%;
}

.cc-chart-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 240px;
}
</style>
