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
      @click="handleChartClick"
    />
  </div>
</template>

<script setup>
import { computed } from "vue";
import VChart from "vue-echarts";
import "../charts/echarts.js";
import { useChartTheme } from "@/composables/useChartTheme.js";

const props = defineProps({
  /** Category labels for the x-axis. */
  categories: {
    type: Array,
    default: () => [],
  },
  /** List of { name: string, values: number[] } series. values aligns with categories. */
  series: {
    type: Array,
    default: () => [],
  },
  /** Y-axis unit label. */
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

const emit = defineEmits(["select"]);

const { chartTheme } = useChartTheme();

const isEmpty = computed(
  () => !props.categories?.length || !props.series?.length
);

const chartOption = computed(() => {
  const th = chartTheme.value;
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
      data: props.categories,
      ...th.xAxis,
    },
    yAxis: {
      type: "value",
      name: props.unit,
      ...th.yAxis,
    },
    series: props.series.map((s) => ({
      name: s.name,
      type: "bar",
      data: s.values,
      barMaxWidth: 48,
    })),
  };
});

function handleChartClick(params) {
  // params.name is the category label when clicking a bar
  if (params?.name !== undefined) {
    emit("select", params.name);
  }
}

defineExpose({ chartOption, isEmpty, handleChartClick });
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
