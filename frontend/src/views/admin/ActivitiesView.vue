<template>
  <div>
    <!-- Page header -->
    <div class="d-flex align-center flex-wrap ga-3 mb-4">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Activities</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Pipeline detections and CTS behavioural signals.
        </div>
      </div>
      <v-spacer />

      <!-- View mode toggle -->
      <CcSegmentedToggle v-model="viewMode" :options="VIEW_MODE_OPTIONS" />
    </div>

    <!-- Filter bar -->
    <v-card variant="tonal" class="mb-4 pa-3">
      <div class="d-flex flex-wrap align-center ga-3">
        <!-- Source toggle (table mode only) -->
        <CcSegmentedToggle
          v-if="viewMode === 'table'"
          v-model="filter.source"
          :options="SOURCE_OPTIONS"
        />

        <!-- Person selector -->
        <v-select
          v-model="filter.person_id"
          :items="personOptions"
          item-title="title"
          item-value="value"
          :label="viewMode === 'timeline' ? 'Person (required)' : 'Person'"
          variant="outlined"
          density="compact"
          clearable
          hide-details
          style="min-width: 200px; max-width: 240px"
          @update:model-value="onPersonChange"
        />

        <!-- Activity type filter (table mode only) -->
        <v-select
          v-if="viewMode === 'table'"
          v-model="filter.signal_type"
          :items="activityTypeOptions"
          label="Activity / Signal type"
          variant="outlined"
          density="compact"
          clearable
          hide-details
          style="min-width: 200px; max-width: 240px"
          @update:model-value="load"
        />

        <!-- Window hours -->
        <v-select
          v-model="filter.window_hours"
          :items="windowOptions"
          label="Window"
          variant="outlined"
          density="compact"
          hide-details
          style="min-width: 120px; max-width: 140px"
          @update:model-value="onWindowChange"
        />

        <!-- Timeline event type chips (timeline mode) -->
        <template v-if="viewMode === 'timeline'">
          <v-chip
            v-for="src in allTimelineSources"
            :key="src.value"
            :color="activeSources.includes(src.value) ? src.color : undefined"
            :variant="activeSources.includes(src.value) ? 'flat' : 'tonal'"
            size="small"
            rounded="pill"
            class="cursor-pointer"
            @click="toggleSource(src.value)"
          >
            <v-icon start size="14">{{ src.icon }}</v-icon>
            {{ src.label }}
          </v-chip>
        </template>

        <v-btn variant="tonal" prepend-icon="mdi-refresh" :loading="loading" @click="refresh">
          Refresh
        </v-btn>
      </div>
    </v-card>

    <!-- Table mode -->
    <v-card v-if="viewMode === 'table'" class="glass-card">
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
            {{ item.source === "cts" ? "CTS" : "Pipeline" }}
          </v-chip>
        </template>
        <template #item.activity_type="{ item }">
          <v-chip size="small" :color="item.source === 'cts' ? 'warning' : 'info'" variant="tonal">
            {{ item.activity_type.replace(/_/g, " ") }}
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
          <div class="pa-8 text-center">
            <v-icon size="48" color="medium-emphasis">mdi-timeline-outline</v-icon>
            <div class="text-body-1 text-medium-emphasis mt-2">No activities found</div>
            <div class="text-body-2 text-medium-emphasis">
              Activities appear as pipeline rules fire or CTS detects behavioural signals.
            </div>
          </div>
        </template>
      </v-data-table>
    </v-card>

    <!-- Timeline mode -->
    <v-card v-else class="glass-card">
      <template v-if="filter.person_id">
        <PersonTimeline
          ref="timelineRef"
          :person-id="filter.person_id"
          :hours="filter.window_hours"
          :event-types="activeSources"
        />
      </template>
      <template v-else>
        <div class="pa-8 text-center">
          <v-icon size="48" color="medium-emphasis" class="mb-2">mdi-account-clock-outline</v-icon>
          <div class="text-h6 text-medium-emphasis">Select a person</div>
          <div class="text-body-2 text-disabled mt-1">
            Choose a person above to view their chronological activity timeline.
          </div>
        </div>
      </template>
    </v-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { useRoute } from "vue-router";
import { api } from "../../services/api.js";
import { cts } from "../../services/cts.js";
import { formatDateTime, DATETIME_COLUMN_WIDTH } from "../../services/timezone.js";
import PersonTimeline from "../../components/person/PersonTimeline.vue";
import CcSegmentedToggle from "../../components/common/CcSegmentedToggle.vue";

const route = useRoute();

// DS segmented pickers (replace v-btn-toggle).
const VIEW_MODE_OPTIONS = [
  { value: "table", label: "Table", icon: "mdi-table" },
  { value: "timeline", label: "Timeline", icon: "mdi-timeline-text-outline" },
];
const SOURCE_OPTIONS = [
  { value: "all", label: "All" },
  { value: "pipeline", label: "Pipeline", icon: "mdi-robot" },
  { value: "cts", label: "CTS", icon: "mdi-cctv" },
];

const loading = ref(false);
const viewMode = ref("table");
const pipelineItems = ref([]);
const ctsSignals = ref([]);
const persons = ref([]);
const timelineRef = ref(null);

const filter = ref({
  source: "all",
  person_id: null,
  signal_type: null,
  window_hours: 24,
});

const activeSources = ref(["activity", "session", "location", "sighting"]);

const allTimelineSources = [
  { value: "activity", label: "Activity", color: "primary", icon: "mdi-check-circle" },
  { value: "session", label: "Session", color: "success", icon: "mdi-play-circle" },
  { value: "location", label: "Location", color: "info", icon: "mdi-door" },
  { value: "sighting", label: "Sighting", color: "warning", icon: "mdi-camera" },
];

const windowOptions = [
  { title: "6 h", value: 6 },
  { title: "12 h", value: 12 },
  { title: "24 h", value: 24 },
  { title: "48 h", value: 48 },
  { title: "7 d", value: 168 },
];

const headers = [
  { title: "Source", key: "source", width: 110 },
  { title: "Person", key: "person_id" },
  { title: "Activity / Signal", key: "activity_type" },
  { title: "Room", key: "room_name" },
  { title: "Severity / Confidence", key: "severity", width: 160 },
  { title: "Time", key: "detected_at", width: DATETIME_COLUMN_WIDTH },
];

const personOptions = computed(() =>
  persons.value.map((p) => ({ title: p.display_name || p.name || p.id, value: p.id })),
);

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

  const ctsList = ctsSignals.value.map((sig, i) => ({
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
    ...(src === "all" || src === "cts" ? ctsList : []),
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
  if (viewMode.value === "timeline") {
    if (!filter.value.person_id) return;
    loading.value = true;
    try {
      if (timelineRef.value) await timelineRef.value.load();
    } finally {
      loading.value = false;
    }
    return;
  }

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
        api
          .getActivities(params)
          .then((data) => {
            pipelineItems.value = Array.isArray(data) ? data : (data?.activities ?? []);
          })
          .catch(() => {
            pipelineItems.value = [];
          }),
      );
    } else {
      pipelineItems.value = [];
    }

    if (src === "all" || src === "cts") {
      const ctsParams = { window_hours: hours, limit: 200 };
      if (pid) ctsParams.person_id = pid;
      tasks.push(
        cts
          .getSignals(ctsParams)
          .then((data) => {
            ctsSignals.value = data?.signals ?? [];
          })
          .catch(() => {
            ctsSignals.value = [];
          }),
      );
    } else {
      ctsSignals.value = [];
    }

    await Promise.all(tasks);
  } finally {
    loading.value = false;
  }
}

async function refresh() {
  await load();
}

function onPersonChange() {
  load();
}

function onWindowChange() {
  load();
}

function toggleSource(src) {
  const idx = activeSources.value.indexOf(src);
  if (idx >= 0) {
    if (activeSources.value.length > 1) activeSources.value.splice(idx, 1);
  } else {
    activeSources.value.push(src);
    load();
  }
}

onMounted(async () => {
  // If redirected from /admin/timeline, switch to timeline mode
  if (route.query.view === "timeline") {
    viewMode.value = "timeline";
  }
  try {
    persons.value = await api.getPersons();
  } catch {
    persons.value = [];
  }
  await load();
});
</script>
