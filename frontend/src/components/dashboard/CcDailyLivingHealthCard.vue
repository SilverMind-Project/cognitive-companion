<template>
  <CcSectionCard
    title="Daily Living Health"
    subtitle="Semantic memory and activity ledger write recency"
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

    <div v-if="state.loading && !state.health" class="d-flex justify-center pa-6">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <v-alert v-else-if="state.error" type="error" density="compact" class="ma-2">
      {{ state.error }}
    </v-alert>

    <div v-else-if="state.health">
      <!-- Semantic memory row -->
      <div class="text-subtitle-2 text-medium-emphasis mb-2">Semantic memory</div>
      <v-row>
        <v-col cols="12" sm="6" md="3">
          <CcMetricTile
            label="Last memory write"
            :value="memoryLastWriteLabel"
            :status="memoryStatus"
          />
        </v-col>
        <v-col cols="12" sm="6" md="3">
          <CcMetricTile
            label="Total observations"
            :value="state.health.semantic_memory.total_observations"
            :status="memoryStatus"
          />
        </v-col>
        <v-col cols="12" md="6">
          <CcBarChart
            :categories="observationsByDayCategories"
            :series="observationsByDaySeries"
            unit="observations"
          />
        </v-col>
      </v-row>

      <!-- Activity ledger row -->
      <div class="text-subtitle-2 text-medium-emphasis mt-6 mb-2">Activity ledger</div>
      <v-alert v-if="ledgerStale" type="warning" density="compact" variant="tonal" class="mb-3">
        Activity ledger has no recent writes.
      </v-alert>
      <div v-if="!state.health.activity_ledger.by_type.length" class="text-medium-emphasis pa-2">
        No activity sessions recorded yet.
      </div>
      <v-row v-else>
        <v-col
          v-for="row in state.health.activity_ledger.by_type"
          :key="row.activity_type"
          cols="12"
          sm="6"
          md="3"
        >
          <CcMetricTile
            :label="row.activity_type"
            :value="formatRelative(row.last_opened_at)"
            :status="ledgerStale ? 'warning' : 'ok'"
          />
        </v-col>
      </v-row>
    </div>
  </CcSectionCard>
</template>

<script setup>
import { computed } from "vue";
import CcSectionCard from "@/components/dashboard/CcSectionCard.vue";
import CcMetricTile from "@/components/dashboard/CcMetricTile.vue";
import CcBarChart from "@/components/charts/CcBarChart.vue";
import { useDailyLivingHealth } from "@/composables/useDailyLivingHealth.js";
import { formatRelative } from "@/composables/useFormatRelative.js";

const { state, actions } = useDailyLivingHealth();
actions.refresh();

const memoryStatus = computed(() => {
  const mem = state.health?.semantic_memory;
  if (!mem) return null;
  if (!mem.reachable) return "error";
  return mem.stale ? "warning" : "ok";
});

const memoryLastWriteLabel = computed(() => {
  const mem = state.health?.semantic_memory;
  if (!mem) return "—";
  if (!mem.reachable) return "Unreachable";
  return formatRelative(mem.last_observation_at) || "Never";
});

const ledgerStale = computed(() => state.health?.activity_ledger?.stale ?? true);

const observationsByDayCategories = computed(() => {
  const days = new Set(
    (state.health?.semantic_memory?.observations_by_day ?? []).map((b) => b.day.slice(0, 10)),
  );
  return [...days].sort();
});

const observationsByDaySeries = computed(() => {
  const buckets = state.health?.semantic_memory?.observations_by_day ?? [];
  const categories = observationsByDayCategories.value;
  const bySource = new Map();
  for (const bucket of buckets) {
    const day = bucket.day.slice(0, 10);
    if (!bySource.has(bucket.source)) {
      bySource.set(bucket.source, new Map(categories.map((c) => [c, 0])));
    }
    bySource.get(bucket.source).set(day, bucket.count);
  }
  return [...bySource.entries()].map(([name, dayCounts]) => ({
    name,
    values: categories.map((c) => dayCounts.get(c) ?? 0),
  }));
});

defineExpose({ memoryStatus, memoryLastWriteLabel, ledgerStale });
</script>
