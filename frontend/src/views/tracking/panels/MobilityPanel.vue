<template>
  <div>
    <TrackingPanelHeader
      title="Mobility"
      description="Daily walking speed trend per resident. Helps detect sustained gait decline early."
    >
      <template #actions>
        <v-btn
          variant="tonal"
          prepend-icon="mdi-refresh"
          size="small"
          :loading="gait.state.loading"
          @click="personId && gait.actions.fetch(personId, days)"
        >
          Refresh
        </v-btn>
      </template>
    </TrackingPanelHeader>

    <v-alert
      v-if="gait.state.error"
      type="error"
      variant="tonal"
      density="compact"
      class="mb-4"
      closable
      @click:close="gait.state.error = ''"
    >
      {{ gait.state.error }}
    </v-alert>

    <!-- Controls -->
    <v-card variant="tonal" class="pa-2 mb-4">
      <v-row dense align="center">
        <v-col cols="12" sm="5">
          <v-select
            v-model="personId"
            :items="personOptions"
            label="Household member"
            variant="outlined"
            density="compact"
            hide-details
            @update:model-value="onPersonChange"
          />
        </v-col>
        <v-col cols="auto">
          <div class="d-flex ga-2">
            <v-btn
              v-for="opt in dayOptions"
              :key="opt.value"
              size="small"
              :variant="days === opt.value ? 'flat' : 'outlined'"
              :color="days === opt.value ? 'primary' : undefined"
              @click="onDaysChange(opt.value)"
            >
              {{ opt.label }}
            </v-btn>
          </div>
        </v-col>
      </v-row>
    </v-card>

    <!-- Summary chips -->
    <v-row v-if="envelope" class="mb-4" dense>
      <v-col cols="auto">
        <v-chip :color="trendColor" variant="tonal" size="small" prepend-icon="mdi-walk">
          {{ trendLabel }}
        </v-chip>
      </v-col>
      <v-col v-if="envelope.baseline_median_m_s != null" cols="auto">
        <v-chip variant="outlined" size="small">
          Baseline {{ envelope.baseline_median_m_s.toFixed(2) }} m/s
        </v-chip>
      </v-col>
      <v-col cols="auto">
        <v-chip variant="outlined" size="small" color="default">
          {{ sufficientCount }} qualifying days
        </v-chip>
      </v-col>
    </v-row>

    <!-- Chart or collecting state -->
    <CcSectionCard>
      <!-- No person selected -->
      <div v-if="!personId" class="pa-6 text-center text-medium-emphasis">
        Select a household member to view mobility trend.
      </div>

      <!-- Loading -->
      <div v-else-if="gait.state.loading" class="d-flex justify-center pa-6">
        <v-progress-circular indeterminate color="primary" />
      </div>

      <!-- Collecting baseline empty state (< 10 qualifying days) -->
      <div v-else-if="isCollecting" class="pa-6 text-center">
        <v-icon size="40" color="primary" class="mb-2">mdi-chart-timeline-variant</v-icon>
        <div class="text-subtitle-2 mb-1">Collecting mobility baseline</div>
        <div class="text-body-2 text-medium-emphasis">
          {{ collectingMessage }}
        </div>
      </div>

      <!-- Chart -->
      <CcGaitTrendChart
        v-else
        :points="chartPoints"
        :baseline-value="envelope?.baseline_median_m_s ?? null"
        :signal-dates="signalDates"
        :loading="gait.state.loading"
        :error="gait.state.error"
      />
    </CcSectionCard>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { useRoute } from "vue-router";
import { api } from "@/services/api.js";
import { useGaitTrend } from "@/composables/useGaitTrend.js";
import CcGaitTrendChart from "@/components/charts/CcGaitTrendChart.vue";
import CcSectionCard from "@/components/dashboard/CcSectionCard.vue";
import TrackingPanelHeader from "@/components/tracking/TrackingPanelHeader.vue";

const route = useRoute();

const personId = ref(null);
const personOptions = ref([]);
const days = ref(56);

const dayOptions = [
  { value: 28, label: "28d" },
  { value: 56, label: "56d" },
  { value: 90, label: "90d" },
];

const gait = useGaitTrend();

const envelope = computed(() => gait.state.envelope);

const sufficientCount = computed(
  () => (envelope.value?.days ?? []).filter((d) => d.sufficient).length,
);

const isCollecting = computed(
  () => envelope.value != null && envelope.value.trend === "insufficient",
);

const collectingMessage = computed(() => {
  const n = sufficientCount.value;
  return `${n} of 10 qualifying days recorded. Come back after more days of mobility data.`;
});

const trendColor = computed(() => {
  if (!envelope.value) return "default";
  if (envelope.value.trend === "declining") return "warning";
  if (envelope.value.trend === "stable") return "success";
  return "default";
});

const trendLabel = computed(() => {
  if (!envelope.value) return "";
  if (envelope.value.trend === "declining") return "Declining";
  if (envelope.value.trend === "stable") return "Stable";
  return "Collecting data";
});

const chartPoints = computed(() =>
  (envelope.value?.days ?? []).map((d) => ({
    date: d.date,
    value: d.median_speed_m_s,
    sufficient: d.sufficient,
  })),
);

/** Dates where gait_slowing signals are present (from the envelope days context). */
const signalDates = computed(() => []);

function onPersonChange(id) {
  personId.value = id;
  if (id) gait.actions.fetch(id, days.value);
}

function onDaysChange(d) {
  days.value = d;
  if (personId.value) gait.actions.fetch(personId.value, d);
}

onMounted(async () => {
  try {
    const persons = await api.getPersons();
    personOptions.value = (persons || []).map((p) => ({
      title: p.display_name || p.name || p.id,
      value: p.id,
    }));
  } catch {
    // Non-fatal
  }

  const routePerson = route.query.person || "";
  if (routePerson) {
    personId.value = routePerson;
    gait.actions.fetch(routePerson, days.value);
  }
});
</script>
