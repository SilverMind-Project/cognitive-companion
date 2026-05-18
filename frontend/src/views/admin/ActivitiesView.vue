<template>
  <div>
    <div class="d-flex align-center flex-wrap ga-3 mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Person Activities</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Unified timeline of pipeline-detected activities and CTS behavioral signals.
        </div>
      </div>
      <v-spacer />

      <!-- Source toggle -->
      <v-btn-toggle v-model="filter.source" density="compact" variant="tonal" divided>
        <v-btn value="all" size="small">All</v-btn>
        <v-btn value="pipeline" size="small" prepend-icon="mdi-robot">Pipeline</v-btn>
        <v-btn value="cts" size="small" prepend-icon="mdi-cctv">CTS</v-btn>
      </v-btn-toggle>

      <v-select
        v-model="filter.person_id"
        :items="personOptions"
        item-title="title"
        item-value="value"
        label="Person"
        variant="outlined"
        density="compact"
        clearable
        hide-details
        style="max-width: 200px"
        @update:model-value="load"
      />
      <v-select
        v-model="filter.signal_type"
        :items="activityTypeOptions"
        label="Activity / Signal type"
        variant="outlined"
        density="compact"
        clearable
        hide-details
        style="max-width: 220px"
        @update:model-value="load"
      />
      <v-select
        v-model="filter.window_hours"
        :items="[6, 12, 24, 48, 168]"
        label="Window (h)"
        variant="outlined"
        density="compact"
        hide-details
        style="max-width: 120px"
        @update:model-value="load"
      />
      <v-btn variant="tonal" prepend-icon="mdi-refresh" :loading="loading" @click="load">Refresh</v-btn>
    </div>

    <v-card class="glass-card">
      <v-data-table
        :headers="headers"
        :items="merged"
        :loading="loading"
        item-value="_key"
        :sort-by="[{ key: 'detected_at', order: 'desc' }]"
      >
        <template #item.source="{ item }">
          <v-chip
            size="x-small"
            :color="item.source === 'cts' ? 'warning' : 'primary'"
            :prepend-icon="item.source === 'cts' ? 'mdi-cctv' : 'mdi-robot'"
            variant="tonal"
          >
            {{ item.source === 'cts' ? 'CTS' : 'Pipeline' }}
          </v-chip>
        </template>
        <template #item.activity_type="{ item }">
          <v-chip
            size="small"
            :color="item.source === 'cts' ? 'warning' : 'info'"
            variant="tonal"
          >
            {{ item.activity_type.replace(/_/g, ' ') }}
          </v-chip>
        </template>
        <template #item.severity="{ item }">
          <v-chip
            v-if="item.severity"
            size="x-small"
            :color="severityChipColor(item.severity)"
            variant="flat"
          >
            {{ item.severity }}
          </v-chip>
          <span v-else-if="item.confidence != null" class="text-body-2">
            {{ (item.confidence * 100).toFixed(0) }}%
          </span>
          <span v-else class="text-medium-emphasis">—</span>
        </template>
        <template #item.detected_at="{ item }">
          {{ formatDateTime(item.detected_at) }}
        </template>
        <template #no-data>
          <div class="pa-6 text-center">
            <v-icon size="48" color="medium-emphasis">mdi-timeline-outline</v-icon>
            <div class="text-body-1 text-medium-emphasis mt-2">No activities found</div>
            <div class="text-body-2 text-medium-emphasis">
              Activities appear as pipeline rules fire or CTS detects behavioral signals.
            </div>
          </div>
        </template>
      </v-data-table>
    </v-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { api } from "../../services/api.js";
import { cts } from "../../services/cts.js";
import { formatDateTime, DATETIME_COLUMN_WIDTH } from "../../services/timezone.js";

const loading = ref(false);
const pipelineItems = ref([]);
const ctsSignals = ref([]);
const persons = ref([]);

const filter = ref({
  source: "all",
  person_id: null,
  signal_type: null,
  window_hours: 24,
});

const headers = [
  { title: "Source", key: "source", width: 110 },
  { title: "Person", key: "person_id" },
  { title: "Activity / Signal", key: "activity_type" },
  { title: "Room", key: "room_name" },
  { title: "Severity / Confidence", key: "severity", width: 160 },
  { title: "Time", key: "detected_at", width: DATETIME_COLUMN_WIDTH },
];

const personOptions = computed(() => {
  const enrolled = persons.value.map((p) => ({
    title: p.display_name || p.name || p.id,
    value: p.id,
  }));
  return enrolled;
});

const activityTypeOptions = computed(() => {
  const types = new Set();
  for (const item of pipelineItems.value) {
    if (item.activity_type) types.add(item.activity_type);
  }
  for (const sig of ctsSignals.value) {
    if (sig.signal_type) types.add(sig.signal_type);
  }
  return [...types].sort();
});

const merged = computed(() => {
  const pipeline = pipelineItems.value.map((item, i) => ({
    _key: `pipeline_${item.id ?? i}`,
    source: "pipeline",
    person_id: item.person_id,
    activity_type: item.activity_type,
    room_name: item.room_name || "—",
    confidence: item.confidence,
    severity: null,
    detected_at: item.detected_at,
  }));

  const cts_ = ctsSignals.value.map((sig, i) => ({
    _key: `cts_${sig.id ?? i}`,
    source: "cts",
    person_id: sig.person_id,
    activity_type: sig.signal_type,
    room_name: sig.context_json?.room_name || "—",
    confidence: null,
    severity: sig.severity,
    detected_at: sig.window_start || sig.received_at,
  }));

  const src = filter.value.source;
  const all = [
    ...(src === "all" || src === "pipeline" ? pipeline : []),
    ...(src === "all" || src === "cts" ? cts_ : []),
  ];

  const type = filter.value.signal_type;
  return type ? all.filter((item) => item.activity_type === type) : all;
});

function severityChipColor(severity) {
  if (severity === "emergency") return "error";
  if (severity === "warning") return "warning";
  return "info";
}

async function load() {
  loading.value = true;
  try {
    const src = filter.value.source;
    const pid = filter.value.person_id || undefined;
    const hours = filter.value.window_hours;

    const tasks = [];

    if (src === "all" || src === "pipeline") {
      const params = {};
      if (pid) params.person_id = pid;
      tasks.push(
        api.getActivities(params).then((data) => {
          pipelineItems.value = Array.isArray(data) ? data : (data?.activities ?? []);
        }).catch(() => { pipelineItems.value = []; })
      );
    } else {
      pipelineItems.value = [];
    }

    if (src === "all" || src === "cts") {
      const ctsParams = { window_hours: hours, limit: 200 };
      if (pid) ctsParams.person_id = pid;
      tasks.push(
        cts.getSignals(ctsParams).then((data) => {
          ctsSignals.value = data?.signals ?? [];
        }).catch(() => { ctsSignals.value = []; })
      );
    } else {
      ctsSignals.value = [];
    }

    await Promise.all(tasks);
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  try {
    persons.value = await api.getPersons();
  } catch {
    persons.value = [];
  }
  await load();
});
</script>
