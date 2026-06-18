<template>
  <div>
    <div class="d-flex align-center flex-wrap ga-3 mb-6">
      <v-btn
        variant="text"
        prepend-icon="mdi-arrow-left"
        size="small"
        :to="{ name: 'admin-routine-builder', params: { id } }"
      >
        Routine
      </v-btn>
      <v-divider vertical class="mx-1" />
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">
          {{ state.routine?.name ?? "Routine Metrics" }}
        </h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Completion, stalls, escalations, and time-of-day patterns.
        </div>
      </div>
      <v-spacer />
      <v-btn
        icon="mdi-refresh"
        variant="text"
        :loading="state.loading"
        @click="actions.fetchDashboard(id)"
      />
    </div>

    <v-alert v-if="state.error" type="error" density="compact" class="mb-4">
      {{ state.error }}
    </v-alert>

    <div v-if="state.loading" class="d-flex justify-center pa-8">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <template v-else-if="state.dashboard">
      <v-row class="mb-4">
        <v-col cols="12" sm="6" lg="3">
          <CcMetricTile label="Completion rate" :value="completionRate" status="ok" />
        </v-col>
        <v-col cols="12" sm="6" lg="3">
          <CcMetricTile label="Avg duration" :value="averageDuration" status="info" />
        </v-col>
        <v-col cols="12" sm="6" lg="3">
          <CcMetricTile label="Abandonment" :value="abandonmentRate" status="warning" />
        </v-col>
        <v-col cols="12" sm="6" lg="3">
          <CcMetricTile label="Escalations" :value="state.dashboard.escalation_breakdown.total" />
        </v-col>
      </v-row>

      <v-row>
        <v-col cols="12" lg="6">
          <CcSectionCard title="Attempts by step">
            <div class="chart-box">
              <CcBarChart
                :categories="attemptCategories"
                :series="attemptSeries"
                unit="retries"
              />
            </div>
          </CcSectionCard>
        </v-col>
        <v-col cols="12" lg="6">
          <CcSectionCard title="Time of day">
            <div class="chart-box">
              <CcBarChart
                :categories="hourCategories"
                :series="hourSeries"
                unit="sessions"
              />
            </div>
          </CcSectionCard>
        </v-col>
        <v-col cols="12" lg="6">
          <CcSectionCard title="Escalation reasons">
            <div class="chart-box">
              <CcBarChart
                :categories="escalationCategories"
                :series="escalationSeries"
                unit="events"
              />
            </div>
          </CcSectionCard>
        </v-col>
        <v-col v-if="hasVisionData" cols="12" lg="6">
          <CcSectionCard title="Vision agreement">
            <div class="chart-box chart-box--gauge">
              <CcGaugeChart :value="visionAgreementPct" label="Agreement" unit="%" />
            </div>
          </CcSectionCard>
        </v-col>
      </v-row>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted } from "vue";
import CcBarChart from "@/components/charts/CcBarChart.vue";
import CcGaugeChart from "@/components/charts/CcGaugeChart.vue";
import CcMetricTile from "@/components/dashboard/CcMetricTile.vue";
import CcSectionCard from "@/components/dashboard/CcSectionCard.vue";
import { useGuidedMetrics } from "@/composables/useGuidedMetrics.js";

const props = defineProps({
  id: { type: String, required: true },
});

const { state, actions } = useGuidedMetrics();

const id = computed(() => props.id);
const completionRate = computed(() =>
  formatPercent(state.dashboard?.completion.completion_rate ?? 0),
);
const abandonmentRate = computed(() =>
  formatPercent(state.dashboard?.abandonment.abandonment_rate ?? 0),
);
const averageDuration = computed(() => {
  const first = state.dashboard?.time_to_complete.items?.[0];
  if (!first) return "0 min";
  return `${Math.round(first.average_seconds / 60)} min`;
});
const attemptCategories = computed(() =>
  (state.dashboard?.attempts_per_step.items ?? []).map((item) => `Step ${item.step_ord + 1}`),
);
const attemptSeries = computed(() => [
  {
    name: "Average retries",
    values: (state.dashboard?.attempts_per_step.items ?? []).map(
      (item) => item.average_attempts,
    ),
  },
]);
const hourCategories = computed(() =>
  (state.dashboard?.time_of_day.buckets ?? []).map((item) => `${item.hour}:00`),
);
const hourSeries = computed(() => [
  {
    name: "Completed",
    values: (state.dashboard?.time_of_day.buckets ?? []).map((item) => item.completed),
  },
  {
    name: "Abandoned",
    values: (state.dashboard?.time_of_day.buckets ?? []).map((item) => item.abandoned),
  },
]);
const escalationCategories = computed(() =>
  (state.dashboard?.escalation_breakdown.items ?? []).map((item) =>
    item.emergency ? `${item.reason} emergency` : item.reason,
  ),
);
const escalationSeries = computed(() => [
  {
    name: "Escalations",
    values: (state.dashboard?.escalation_breakdown.items ?? []).map((item) => item.count),
  },
]);
const hasVisionData = computed(() => (state.dashboard?.vision_agreement.total ?? 0) > 0);
const visionAgreementPct = computed(() =>
  Math.round((state.dashboard?.vision_agreement.agreement_rate ?? 0) * 100),
);

function formatPercent(value) {
  return `${Math.round(value * 100)}%`;
}

onMounted(() => {
  actions.fetchDashboard(id.value);
});
</script>

<style scoped>
.chart-box {
  min-height: 280px;
}

.chart-box--gauge {
  min-height: 220px;
}
</style>
