<template>
  <div>
    <!-- Header -->
    <div class="d-flex align-center flex-wrap ga-3 mb-6">
      <v-btn
        icon="mdi-arrow-left"
        variant="text"
        size="small"
        :to="{ name: 'admin-persons' }"
        aria-label="Back to members"
      />
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">
          {{ person?.name || personId }}
        </h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          <span v-if="person?.is_guest">Guest</span>
          <span v-else>Household member</span>
          <span class="mx-1">·</span>
          <span>ID: {{ personId }}</span>
        </div>
      </div>
      <v-spacer />
      <v-chip
        v-if="person"
        :color="person.is_active ? 'success' : 'grey'"
        size="small"
        variant="tonal"
      >
        {{ person.is_active ? 'Active' : 'Inactive' }}
      </v-chip>
    </div>

    <!-- Presence summary bar -->
    <PresenceWidget
      v-if="person"
      :person-id="personId"
      :person-label="person.name || personId"
      :poll-seconds="20"
      class="mb-4"
    />

    <!-- Profile tabs -->
    <v-tabs v-model="activeTab" color="primary" class="mb-4">
      <v-tab value="timeline">
        <v-icon start size="16">mdi-timeline-text-outline</v-icon>
        Timeline
      </v-tab>
      <v-tab value="signals">
        <v-icon start size="16">mdi-alert-circle-outline</v-icon>
        Signals
      </v-tab>
      <v-tab value="where">
        <v-icon start size="16">mdi-door-open</v-icon>
        Where
      </v-tab>
      <v-tab value="identity">
        <v-icon start size="16">mdi-face-recognition</v-icon>
        Identity
      </v-tab>
    </v-tabs>

    <v-window v-model="activeTab">
      <!-- Timeline tab -->
      <v-window-item value="timeline">
        <v-card class="glass-card">
          <v-card-text class="pa-2">
            <div class="d-flex align-center flex-wrap ga-2 pa-2 pb-0">
              <v-select
                v-model="timelineHours"
                :items="[6, 12, 24, 48, 168]"
                label="Window"
                variant="outlined"
                density="compact"
                hide-details
                style="max-width: 130px"
                @update:model-value="refreshTimeline"
              />
              <v-chip-group>
                <v-chip
                  v-for="src in timelineSources"
                  :key="src.value"
                  :color="activeTimelineSources.includes(src.value) ? src.color : ''"
                  :variant="activeTimelineSources.includes(src.value) ? 'flat' : 'tonal'"
                  size="small"
                  rounded="pill"
                  @click="toggleTimelineSource(src.value)"
                >
                  <v-icon start size="14">{{ src.icon }}</v-icon>
                  {{ src.label }}
                </v-chip>
              </v-chip-group>
              <v-spacer />
              <v-btn
                variant="text"
                size="small"
                prepend-icon="mdi-refresh"
                :loading="timelineLoading"
                @click="refreshTimeline"
              >
                Refresh
              </v-btn>
            </div>
          </v-card-text>
          <PersonTimeline
            ref="timelineRef"
            :person-id="personId"
            :hours="timelineHours"
            :event-types="activeTimelineSources"
          />
        </v-card>
      </v-window-item>

      <!-- Signals tab -->
      <v-window-item value="signals">
        <v-card class="glass-card">
          <v-card-text>
            <div class="d-flex align-center flex-wrap ga-3 mb-4">
              <v-select
                v-model="signalType"
                :items="signalTypeItems"
                label="Signal Type"
                variant="outlined"
                density="compact"
                clearable
                hide-details
                style="width: 220px"
                @update:model-value="loadSignals"
              />
              <v-select
                v-model="signalSeverity"
                :items="['info', 'warning', 'emergency']"
                label="Severity"
                variant="outlined"
                density="compact"
                clearable
                hide-details
                style="width: 150px"
                @update:model-value="loadSignals"
              />
              <v-select
                v-model="signalWindowHours"
                :items="[1, 6, 12, 24, 48, 168]"
                label="Window (h)"
                variant="outlined"
                density="compact"
                hide-details
                style="width: 130px"
                @update:model-value="loadSignals"
              />
              <v-spacer />
              <v-btn
                variant="tonal"
                prepend-icon="mdi-open-in-new"
                size="small"
                :to="{ name: 'admin-alerts', query: { source: 'cts' } }"
              >
                Alert Center
              </v-btn>
              <v-btn
                variant="text"
                size="small"
                prepend-icon="mdi-refresh"
                :loading="signalsLoading"
                @click="loadSignals"
              >
                Refresh
              </v-btn>
            </div>

            <v-data-table
              :headers="signalHeaders"
              :items="signals"
              :loading="signalsLoading"
              item-value="id"
              density="compact"
            >
              <template #item.signal_type="{ value }">
                <v-chip :color="severityColor(value)" size="small" variant="tonal">
                  {{ value.replace(/_/g, ' ') }}
                </v-chip>
              </template>
              <template #item.severity="{ value }">
                <v-chip :color="severityColor(value)" size="small" density="compact" variant="flat">
                  {{ value }}
                </v-chip>
              </template>
              <template #item.acknowledged_at="{ value }">
                <v-icon v-if="value" color="success" size="small">mdi-check-circle</v-icon>
                <v-icon v-else color="orange" size="small">mdi-alert-circle</v-icon>
              </template>
              <template #item.actions="{ item }">
                <v-btn
                  v-if="!item.acknowledged_at"
                  size="small"
                  variant="text"
                  color="primary"
                  @click="acknowledgeSignal(item.id)"
                >
                  <v-icon start>mdi-check</v-icon>
                  Ack
                </v-btn>
              </template>
              <template #no-data>
                <div class="pa-4 text-center text-medium-emphasis">
                  No signals in the selected window.
                </div>
              </template>
            </v-data-table>

            <!-- 7-day trend -->
            <template v-if="trend.length">
              <v-divider class="my-4" />
              <div class="d-flex align-center mb-3">
                <v-icon start size="18">mdi-chart-timeline</v-icon>
                <span class="text-subtitle-2 font-weight-semibold">7-Day Signal Trend</span>
              </div>
              <v-table density="compact">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Count</th>
                    <th>Info</th>
                    <th>Warning</th>
                    <th>Emergency</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="day in trend" :key="day.date">
                    <td>{{ day.date }}</td>
                    <td class="font-weight-bold">{{ day.count }}</td>
                    <td>{{ day.by_severity.info || 0 }}</td>
                    <td>{{ day.by_severity.warning || 0 }}</td>
                    <td>{{ day.by_severity.emergency || 0 }}</td>
                  </tr>
                </tbody>
              </v-table>
            </template>
          </v-card-text>
        </v-card>
      </v-window-item>

      <!-- Where tab -->
      <v-window-item value="where">
        <v-row>
          <v-col cols="12" md="6">
            <v-card class="glass-card">
              <v-card-title class="text-subtitle-1 font-weight-bold pa-4 pb-2">
                <v-icon start size="18">mdi-door-open</v-icon>
                Room Dwell
              </v-card-title>
              <v-card-text>
                <div class="d-flex align-center ga-3 mb-4">
                  <v-text-field
                    v-model="dwellDate"
                    label="Date (YYYY-MM-DD)"
                    density="compact"
                    variant="outlined"
                    hide-details
                    clearable
                    style="max-width: 200px"
                    @change="loadDwell"
                  />
                  <v-btn
                    variant="text"
                    size="small"
                    prepend-icon="mdi-refresh"
                    :loading="dwellLoading"
                    @click="loadDwell"
                  >
                    Refresh
                  </v-btn>
                </div>
                <div v-if="dwellRooms.length">
                  <div
                    v-for="room in dwellRooms"
                    :key="room.room_name"
                    class="mb-3"
                  >
                    <div class="d-flex justify-space-between text-body-2 mb-1">
                      <span>{{ room.room_name }}</span>
                      <span class="text-medium-emphasis">{{ formatDuration(room.duration_seconds) }}</span>
                    </div>
                    <v-progress-linear
                      :model-value="room.fraction * 100"
                      color="primary"
                      height="8"
                      rounded
                    />
                  </div>
                </div>
                <div v-else class="text-center text-medium-emphasis py-6">
                  No dwell data for this day.
                </div>
              </v-card-text>
            </v-card>
          </v-col>
          <v-col cols="12" md="6">
            <v-card class="glass-card">
              <v-card-title class="text-subtitle-1 font-weight-bold pa-4 pb-2">
                <v-icon start size="18">mdi-map-marker-path</v-icon>
                Trajectory
              </v-card-title>
              <v-card-text>
                <div v-if="trajectoryPoints.length" class="trajectory-canvas">
                  <svg
                    viewBox="0 0 400 300"
                    width="100%"
                    style="background: var(--cc-surface-3); border-radius: 4px"
                    aria-label="Floor-plan trajectory overlay"
                  >
                    <line
                      v-for="x in [100, 200, 300]"
                      :key="`vg-${x}`"
                      :x1="x" y1="0" :x2="x" y2="300"
                      style="stroke: var(--cc-divider); stroke-width: 1"
                    />
                    <line
                      v-for="y in [75, 150, 225]"
                      :key="`hg-${y}`"
                      x1="0" :y1="y" x2="400" :y2="y"
                      style="stroke: var(--cc-divider); stroke-width: 1"
                    />
                    <polyline
                      v-if="svgPath"
                      :points="svgPath"
                      fill="none"
                      style="stroke: var(--cc-brand); stroke-width: 2; opacity: 0.7"
                      stroke-linejoin="round"
                      stroke-linecap="round"
                    />
                    <circle
                      v-if="latestPoint"
                      :cx="latestPoint.svgX"
                      :cy="latestPoint.svgY"
                      r="6"
                      style="fill: var(--cc-brand); stroke: var(--cc-bg-elevated); stroke-width: 2"
                    />
                  </svg>
                  <div class="text-caption text-medium-emphasis mt-1 text-center">
                    {{ trajectoryPoints.length }} points
                    <!-- TODO: overlay on floor plan image when CTSFloorPlanView's SVG is extracted to a reusable component -->
                  </div>
                </div>
                <div v-else class="text-center text-medium-emphasis py-6">
                  No trajectory data for this period.
                </div>
              </v-card-text>
            </v-card>
          </v-col>
        </v-row>
      </v-window-item>

      <!-- Identity tab -->
      <v-window-item value="identity">
        <v-row>
          <v-col cols="12" md="6">
            <v-card class="glass-card">
              <v-card-title class="text-subtitle-1 font-weight-bold pa-4 pb-2">
                <v-icon start size="18">mdi-face-recognition</v-icon>
                Face Recognition Enrollment
              </v-card-title>
              <v-card-text>
                <v-progress-linear v-if="identityLoading" indeterminate class="mb-3" />
                <template v-if="enrollment">
                  <v-alert
                    v-if="enrollment.embedding_count > 0"
                    type="success"
                    variant="tonal"
                    density="compact"
                    class="mb-3"
                  >
                    Enrolled with {{ enrollment.embedding_count }} reference photo(s).
                  </v-alert>
                  <v-alert v-else type="warning" variant="tonal" density="compact" class="mb-3">
                    Not yet enrolled. Go to Members &amp; Enrollment to add reference photos.
                  </v-alert>
                </template>
                <v-btn
                  variant="tonal"
                  prepend-icon="mdi-face-recognition"
                  :to="{ name: 'admin-persons' }"
                  class="mt-2"
                >
                  Manage Enrollment
                </v-btn>
              </v-card-text>
            </v-card>
          </v-col>
          <v-col cols="12" md="6">
            <v-card class="glass-card">
              <v-card-title class="text-subtitle-1 font-weight-bold pa-4 pb-2">
                <v-icon start size="18">mdi-image-search-outline</v-icon>
                ReID Gallery (Appearance Tracking)
              </v-card-title>
              <v-card-text>
                <p class="text-body-2 text-medium-emphasis mb-4">
                  Appearance embeddings let the camera tracking system recognise this person
                  by their silhouette and clothing, independent of face recognition.
                  Enroll keyframes from the Keyframes view.
                </p>
                <v-btn
                  variant="tonal"
                  prepend-icon="mdi-image-search-outline"
                  :to="{ name: 'cts-keyframes' }"
                >
                  Open Keyframes
                </v-btn>
              </v-card-text>
            </v-card>
          </v-col>
        </v-row>
      </v-window-item>
    </v-window>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from "vue";
import { api } from "../../services/api.js";
import { cts } from "../../services/cts.js";
import PersonTimeline from "../../components/person/PersonTimeline.vue";
import PresenceWidget from "../../components/cts/PresenceWidget.vue";
import { severityColor } from "../../composables/useCtsSeverity.js";
import { useNotify } from "../../composables/useNotify.js";
import { formatDateTime, DATETIME_COLUMN_WIDTH } from "../../services/timezone.js";

const { notify } = useNotify();

const props = defineProps({
  id: { type: String, required: true },
});

const personId = computed(() => props.id);
const person = ref(null);
const activeTab = ref("timeline");

// ── Person load ──────────────────────────────────────────────────────────────
async function loadPerson() {
  try {
    person.value = await api.getPerson(personId.value);
  } catch {
    // Non-fatal: header degrades to ID.
  }
}

// ── Timeline tab ─────────────────────────────────────────────────────────────
const timelineRef = ref(null);
const timelineHours = ref(24);
const timelineLoading = ref(false);
const activeTimelineSources = ref(["activity", "session", "location", "sighting"]);

const timelineSources = [
  { value: "activity", label: "Activity", icon: "mdi-check-circle", color: "primary" },
  { value: "session", label: "Session", icon: "mdi-play-circle", color: "success" },
  { value: "location", label: "Location", icon: "mdi-door", color: "info" },
  { value: "sighting", label: "Sighting", icon: "mdi-camera", color: "warning" },
];

function toggleTimelineSource(src) {
  const idx = activeTimelineSources.value.indexOf(src);
  if (idx >= 0) {
    if (activeTimelineSources.value.length > 1) activeTimelineSources.value.splice(idx, 1);
  } else {
    activeTimelineSources.value.push(src);
  }
  refreshTimeline();
}

async function refreshTimeline() {
  await nextTick();
  if (!timelineRef.value) return;
  timelineLoading.value = true;
  try {
    await timelineRef.value.load();
  } finally {
    timelineLoading.value = false;
  }
}

// ── Signals tab ──────────────────────────────────────────────────────────────
const signals = ref([]);
const trend = ref([]);
const signalsLoading = ref(false);
const signalType = ref(null);
const signalSeverity = ref(null);
const signalWindowHours = ref(24);
let signalsLoaded = false;

const signalTypeItems = [
  "pacing", "room_revisit_rate", "bathroom_dwell_anomaly",
  "sundowning_index", "nighttime_movement", "stillness_anomaly", "absence", "fall_suspected",
];

const signalHeaders = [
  { title: "Type", key: "signal_type" },
  { title: "Severity", key: "severity", width: "110px" },
  { title: "Value", key: "value", width: "80px" },
  { title: "Z-Score", key: "z_score", width: "90px" },
  { title: "Window Start", key: "window_start", width: DATETIME_COLUMN_WIDTH },
  { title: "Acknowledged", key: "acknowledged_at", width: "115px" },
  { title: "Actions", key: "actions", sortable: false, width: "80px" },
];

async function loadSignals() {
  signalsLoading.value = true;
  try {
    const [sigData, trendData] = await Promise.allSettled([
      cts.getSignals({
        person_id: personId.value,
        signal_type: signalType.value || undefined,
        severity: signalSeverity.value || undefined,
        window_hours: signalWindowHours.value,
      }),
      cts.getSignalTrend(personId.value, 7),
    ]);
    signals.value = sigData.status === "fulfilled" ? sigData.value.signals || [] : [];
    trend.value = trendData.status === "fulfilled" ? trendData.value.trend || [] : [];
    signalsLoaded = true;
  } finally {
    signalsLoading.value = false;
  }
}

async function acknowledgeSignal(id) {
  try {
    await cts.acknowledgeSignal(id);
    signals.value = signals.value.map((s) =>
      s.id === id ? { ...s, acknowledged_at: new Date().toISOString() } : s
    );
  } catch (e) {
    notify(e?.message || "Failed to acknowledge signal", "error");
  }
}

// ── Where tab ────────────────────────────────────────────────────────────────
const dwellRooms = ref([]);
const trajectoryPoints = ref([]);
const dwellLoading = ref(false);
const dwellDate = ref(null);
let dwellLoaded = false;

const svgPath = computed(() => {
  if (trajectoryPoints.value.length < 2) return null;
  const pts = [...trajectoryPoints.value].sort(
    (a, b) => new Date(a.observed_at) - new Date(b.observed_at)
  );
  const xs = pts.map((p) => p.ground_x ?? 0);
  const ys = pts.map((p) => p.ground_y ?? 0);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const rangeX = maxX - minX || 1;
  const rangeY = maxY - minY || 1;
  return pts
    .map((p) => {
      const sx = ((( p.ground_x ?? 0) - minX) / rangeX) * 360 + 20;
      const sy = (((p.ground_y ?? 0) - minY) / rangeY) * 260 + 20;
      return `${sx},${sy}`;
    })
    .join(" ");
});

const latestPoint = computed(() => {
  if (!trajectoryPoints.value.length) return null;
  const sorted = [...trajectoryPoints.value].sort(
    (a, b) => new Date(b.observed_at) - new Date(a.observed_at)
  );
  const p = sorted[0];
  const xs = trajectoryPoints.value.map((pt) => pt.ground_x ?? 0);
  const ys = trajectoryPoints.value.map((pt) => pt.ground_y ?? 0);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const rangeX = maxX - minX || 1;
  const rangeY = maxY - minY || 1;
  return {
    svgX: (((p.ground_x ?? 0) - minX) / rangeX) * 360 + 20,
    svgY: (((p.ground_y ?? 0) - minY) / rangeY) * 260 + 20,
  };
});

function formatDuration(seconds) {
  if (!seconds) return "0m";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

async function loadDwell() {
  dwellLoading.value = true;
  const [dwellData, trajData] = await Promise.allSettled([
    cts.getDashboardDwellSummary(personId.value, dwellDate.value || undefined),
    cts.getDashboardTrajectory(personId.value, { limit: 200 }),
  ]);
  dwellRooms.value =
    dwellData.status === "fulfilled" ? dwellData.value.rooms || [] : [];
  trajectoryPoints.value =
    trajData.status === "fulfilled" ? trajData.value.points || [] : [];
  dwellLoaded = true;
  dwellLoading.value = false;
}

// ── Identity tab ─────────────────────────────────────────────────────────────
const enrollment = ref(null);
const identityLoading = ref(false);
let identityLoaded = false;

async function loadIdentity() {
  if (identityLoaded) return;
  identityLoading.value = true;
  try {
    enrollment.value = await api.getEnrollmentStatus(personId.value);
  } catch {
    enrollment.value = null;
  } finally {
    identityLoading.value = false;
    identityLoaded = true;
  }
}

// Lazy-load tabs on first selection.
function onTabChange(tab) {
  if (tab === "signals" && !signalsLoaded) loadSignals();
  if (tab === "where" && !dwellLoaded) loadDwell();
  if (tab === "identity" && !identityLoaded) loadIdentity();
}

function ensureTabLoaded(tab) {
  if (tab === "timeline") {
    refreshTimeline();
  } else if (tab === "signals" && !signalsLoaded) {
    loadSignals();
  } else if (tab === "where" && !dwellLoaded) {
    loadDwell();
  } else if (tab === "identity" && !identityLoaded) {
    loadIdentity();
  }
}

watch(activeTab, ensureTabLoaded);

// Vue Router reuses this component when only the :id param changes.
// Reset per-person state and re-load whatever tab the user is on.
watch(personId, () => {
  signalsLoaded = false;
  dwellLoaded = false;
  identityLoaded = false;
  signals.value = [];
  trend.value = [];
  dwellRooms.value = [];
  trajectoryPoints.value = [];
  enrollment.value = null;
  loadPerson();
  ensureTabLoaded(activeTab.value);
});

onMounted(() => {
  loadPerson();
  ensureTabLoaded(activeTab.value);
});
</script>
