<template>
  <CcSectionCard
    title="Inference Load"
    subtitle="LLM admission-controller queue depth and call volume"
  >
    <template #actions>
      <v-btn
        variant="tonal"
        size="small"
        prepend-icon="mdi-refresh"
        :loading="state.loading"
        @click="actions.refresh"
      >
        Refresh
      </v-btn>
    </template>

    <div v-if="state.loading && !state.telemetry" class="d-flex justify-center pa-6">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <v-alert v-else-if="state.error" type="error" density="compact" class="ma-2">
      {{ state.error }}
    </v-alert>

    <div v-else-if="state.telemetry">
      <v-row>
        <v-col cols="12" sm="6" md="3">
          <CcMetricTile :label="`Vision calls (last ${windowLabel})`" :value="visionCalls" />
        </v-col>
        <v-col cols="12" sm="6" md="3">
          <CcMetricTile :label="`Text calls (last ${windowLabel})`" :value="textCalls" />
        </v-col>
        <v-col cols="12" sm="6" md="3">
          <CcMetricTile
            :label="`Timeouts (last ${windowLabel})`"
            :value="state.telemetry.timeouts_total"
            :status="state.telemetry.timeouts_total > 0 ? 'warning' : 'ok'"
          />
        </v-col>
        <v-col cols="12" sm="6" md="3">
          <CcMetricTile label="Queue wait p95" :value="queueWaitP95Label" />
        </v-col>
      </v-row>

      <v-row class="mt-2">
        <v-col cols="12" sm="6" md="3">
          <CcMetricTile label="Vision queue depth" :value="queueDepth('vision')" />
        </v-col>
        <v-col cols="12" sm="6" md="3">
          <CcMetricTile label="Text queue depth" :value="queueDepth('text')" />
        </v-col>
      </v-row>

      <div class="text-subtitle-2 text-medium-emphasis mt-6 mb-2">Calls by caller and lane</div>
      <CcBarChart :categories="callerCategories" :series="callerSeries" unit="calls" />
    </div>
  </CcSectionCard>
</template>

<script setup>
import { computed } from "vue";
import CcSectionCard from "@/components/dashboard/CcSectionCard.vue";
import CcMetricTile from "@/components/dashboard/CcMetricTile.vue";
import CcBarChart from "@/components/charts/CcBarChart.vue";
import { useInferenceTelemetry } from "@/composables/useInferenceTelemetry.js";

const { state, actions } = useInferenceTelemetry();
actions.refresh();

const windowLabel = computed(() => {
  const minutes = state.telemetry?.window_minutes;
  if (!minutes) return "window";
  return minutes % 60 === 0 ? `${minutes / 60}h` : `${minutes}m`;
});

function callsForLane(lane) {
  const rows = state.telemetry?.totals_by_caller_lane ?? [];
  return rows
    .filter((r) => r.lane === lane)
    .reduce((sum, r) => sum + r.ok + r.timeout + r.error, 0);
}

const visionCalls = computed(() => callsForLane("vision"));
const textCalls = computed(() => callsForLane("text"));

const queueWaitP95Label = computed(() => {
  const p95 = state.telemetry?.queue_wait_p95_ms;
  return p95 == null ? "—" : `${Math.round(p95)} ms`;
});

function queueDepth(lane) {
  const rows = state.telemetry?.queue_depth ?? [];
  return rows.find((r) => r.lane === lane)?.depth ?? 0;
}

const callerCategories = computed(() =>
  (state.telemetry?.totals_by_caller_lane ?? []).map((r) => `${r.caller}:${r.lane}`),
);

const callerSeries = computed(() => {
  const rows = state.telemetry?.totals_by_caller_lane ?? [];
  return [
    { name: "ok", values: rows.map((r) => r.ok) },
    { name: "timeout", values: rows.map((r) => r.timeout) },
    { name: "error", values: rows.map((r) => r.error) },
  ];
});

defineExpose({
  windowLabel,
  visionCalls,
  textCalls,
  queueWaitP95Label,
  callerCategories,
  callerSeries,
});
</script>
