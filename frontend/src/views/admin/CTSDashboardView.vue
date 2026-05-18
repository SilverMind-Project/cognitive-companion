<template>
  <div>
    <div class="d-flex align-center mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">CTS Dashboard</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Real-time tracking, signals, and dwell data for monitored persons.
        </div>
      </div>
    </div>

    <!-- Current presence widgets -->
    <div class="mb-6">
      <div class="text-subtitle-2 font-weight-bold mb-2">Current Presence</div>
      <v-row dense>
        <v-col v-for="person in trackedPersons" :key="person.id" cols="12" sm="6" md="4">
          <PresenceWidget :person-id="person.id" :person-label="person.display_name" :poll-seconds="10" />
        </v-col>
        <v-col v-if="!trackedPersons.length" cols="12">
          <v-card class="glass-card">
            <v-card-text class="text-center text-medium-emphasis py-6">
              No persons configured for tracking. Add household members in <router-link to="/admin/persons">Persons</router-link>.
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>
    </div>

    <!-- Filters -->
    <v-card variant="tonal" class="mb-4 pa-3">
      <v-row dense align="center">
        <v-col cols="12" sm="4">
          <v-select
            v-model="selectedPerson"
            :items="personOptions"
            item-title="title"
            item-value="value"
            label="Person"
            prepend-inner-icon="mdi-account"
            density="compact"
            clearable
            hide-details
            @update:modelValue="onPersonChange"
          />
        </v-col>
        <v-col cols="12" sm="3">
          <v-text-field
            v-model="selectedDate"
            label="Date (YYYY-MM-DD)"
            prepend-inner-icon="mdi-calendar"
            density="compact"
            hide-details
            clearable
            @change="loadDwellSummary"
          />
        </v-col>
        <v-col cols="12" sm="2">
          <v-select
            v-model="windowHours"
            :items="[6, 12, 24, 48, 168]"
            label="Signal window (h)"
            density="compact"
            hide-details
            @update:modelValue="loadSignals"
          />
        </v-col>
        <v-col cols="12" sm="3" class="d-flex align-center">
          <v-btn
            prepend-icon="mdi-refresh"
            variant="tonal"
            :loading="loading"
            block
            @click="refreshAll"
          >
            Refresh
          </v-btn>
        </v-col>
      </v-row>
    </v-card>

    <v-row>
      <!-- Signal summary cards -->
      <v-col cols="12">
        <v-row>
          <v-col
            v-for="(info, kind) in signalSummary"
            :key="kind"
            cols="6"
            sm="4"
            md="2"
          >
            <v-card :color="severityColor(info.max_severity)" variant="tonal">
              <v-card-text class="text-center pa-3">
                <div class="text-h5 font-weight-bold">{{ info.count }}</div>
                <div class="text-caption">{{ kind.replace(/_/g, " ") }}</div>
                <v-chip
                  :color="severityColor(info.max_severity)"
                  size="x-small"
                  class="mt-1"
                >
                  {{ info.max_severity }}
                </v-chip>
              </v-card-text>
            </v-card>
          </v-col>
          <v-col v-if="Object.keys(signalSummary).length === 0" cols="12">
            <v-alert type="info" variant="tonal" density="compact">
              No signals in the last {{ windowHours }} hours.
            </v-alert>
          </v-col>
        </v-row>
      </v-col>

      <!-- Signal timeline -->
      <v-col cols="12" md="7">
        <v-card>
          <v-card-title>
            <v-icon start>mdi-timeline-alert</v-icon>
            Signal Timeline
          </v-card-title>
          <v-card-text class="pa-0">
            <v-list v-if="signals.length > 0" lines="two" density="compact">
              <v-list-item
                v-for="sig in signals"
                :key="sig.signal_id"
                :subtitle="`${sig.identity_id} · value: ${sig.value}`"
              >
                <template v-slot:prepend>
                  <v-icon :color="severityColor(sig.severity)" size="small">
                    {{ severityIcon(sig.severity) }}
                  </v-icon>
                </template>
                <template v-slot:title>
                  <span class="text-body-2 font-weight-medium">
                    {{ sig.signal_kind.replace(/_/g, " ") }}
                  </span>
                  <v-chip
                    :color="severityColor(sig.severity)"
                    size="x-small"
                    class="ml-2"
                    variant="flat"
                  >
                    {{ sig.severity }}
                  </v-chip>
                </template>
                <template v-slot:append>
                  <span class="text-caption text-medium-emphasis">
                    {{ formatTime(sig.emitted_at) }}
                  </span>
                </template>
              </v-list-item>
            </v-list>
            <div v-else class="text-center text-medium-emphasis py-8">
              No signals found.
            </div>
          </v-card-text>
        </v-card>
      </v-col>

      <!-- Room dwell bar chart + floor-plan trajectory -->
      <v-col cols="12" md="5">
        <!-- Dwell summary -->
        <v-card class="mb-4">
          <v-card-title>
            <v-icon start>mdi-door-open</v-icon>
            Room Dwell: {{ selectedDate || "Today" }}
          </v-card-title>
          <v-card-text>
            <div v-if="dwellRooms.length > 0">
              <div
                v-for="room in dwellRooms"
                :key="room.room_name"
                class="mb-2"
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
            <div v-else class="text-center text-medium-emphasis py-4">
              No dwell data for this day.
            </div>
          </v-card-text>
        </v-card>

        <!-- Floor-plan trajectory (SVG overlay) -->
        <v-card>
          <v-card-title>
            <v-icon start>mdi-map-marker-path</v-icon>
            Trajectory
          </v-card-title>
          <v-card-text>
            <div v-if="trajectoryPoints.length > 0" class="trajectory-canvas">
              <svg
                viewBox="0 0 400 300"
                width="100%"
                style="background: var(--cc-surface-3); border-radius: 4px"
                aria-label="Floor-plan trajectory overlay"
              >
                <!-- Grid lines -->
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
                <!-- Trajectory path -->
                <polyline
                  v-if="svgPath"
                  :points="svgPath"
                  fill="none"
                  style="stroke: var(--cc-brand); stroke-width: 2; opacity: 0.7"
                  stroke-linejoin="round"
                  stroke-linecap="round"
                />
                <!-- Most recent position dot -->
                <circle
                  v-if="latestPoint"
                  :cx="latestPoint.svgX"
                  :cy="latestPoint.svgY"
                  r="6"
                  style="fill: var(--cc-brand); stroke: var(--cc-bg-elevated); stroke-width: 2"
                />
              </svg>
              <div class="text-caption text-medium-emphasis mt-1 text-center">
                {{ trajectoryPoints.length }} points · last seen {{ formatTime(trajectoryPoints[0]?.observed_at) }}
              </div>
            </div>
            <div v-else class="text-center text-medium-emphasis py-4">
              No trajectory data.
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { cts } from "../../services/cts.js";
import { api } from "../../services/api.js";
import PresenceWidget from "../../components/cts/PresenceWidget.vue";
import { severityColor, severityIcon } from "../../composables/useCtsSeverity";
import { formatTimeOnly, formatDateTimeShort } from "../../services/timezone.js";

const selectedPerson = ref(null);
const selectedDate = ref(null);
const windowHours = ref(24);
const loading = ref(false);
const trackedPersons = ref([]);

const signals = ref([]);
const signalSummary = ref({});
const trajectoryPoints = ref([]);
const dwellRooms = ref([]);

// Person options: prefer enrolled household members (loaded on mount);
// augment with any identity_ids seen in recent signals that aren't enrolled.
const personOptions = computed(() => {
  const enrolled = trackedPersons.value.map((p) => ({
    title: p.display_name || p.name || p.id,
    value: p.id,
  }));
  const enrolledIds = new Set(enrolled.map((p) => p.value));
  const fromSignals = signals.value
    .map((s) => s.identity_id)
    .filter((id) => id && !enrolledIds.has(id));
  const extra = [...new Set(fromSignals)].map((id) => ({ title: id, value: id }));
  return [...enrolled, ...extra];
});

// SVG trajectory helpers: map ground_x/y (meters) to SVG coords.
const svgPath = computed(() => {
  if (trajectoryPoints.value.length < 2) return null;
  // Sort ascending by time.
  const pts = [...trajectoryPoints.value].sort(
    (a, b) => new Date(a.observed_at) - new Date(b.observed_at)
  );
  return pts.map((p) => `${toSvgX(p.ground_x)},${toSvgY(p.ground_y)}`).join(" ");
});

const latestPoint = computed(() => {
  if (!trajectoryPoints.value.length) return null;
  const p = trajectoryPoints.value[0]; // already sorted desc
  return { svgX: toSvgX(p.ground_x), svgY: toSvgY(p.ground_y) };
});

function toSvgX(x) {
  // Map 0..10m to 20..380px.
  return Math.max(20, Math.min(380, 20 + (x / 10) * 360));
}
function toSvgY(y) {
  // Map 0..8m to 20..280px (inverted Y).
  return Math.max(20, Math.min(280, 280 - (y / 8) * 260));
}

onMounted(async () => {
  try {
    trackedPersons.value = await api.getPersons();
  } catch (e) {
    console.error("Failed to load persons for presence widgets:", e);
  }
  loadSignals();
  loadSummary();
});

async function refreshAll() {
  loading.value = true;
  try {
    await Promise.all([
      loadSignals(),
      loadSummary(),
      selectedPerson.value ? loadTrajectory() : Promise.resolve(),
      selectedPerson.value ? loadDwellSummary() : Promise.resolve(),
    ]);
  } finally {
    loading.value = false;
  }
}

function onPersonChange() {
  loadTrajectory();
  loadDwellSummary();
}

async function loadSignals() {
  try {
    const data = await cts.getDashboardSignals({
      person_id: selectedPerson.value,
      window_hours: windowHours.value,
    });
    signals.value = data.signals || [];
  } catch (e) {
    console.error("Failed to load dashboard signals:", e);
  }
}

async function loadSummary() {
  try {
    const data = await cts.getSignalSummary(selectedPerson.value);
    signalSummary.value = data.by_type || {};
  } catch (e) {
    console.error("Failed to load signal summary:", e);
  }
}

async function loadTrajectory() {
  if (!selectedPerson.value) {
    trajectoryPoints.value = [];
    return;
  }
  try {
    const data = await cts.getDashboardTrajectory(selectedPerson.value, { limit: 200 });
    trajectoryPoints.value = data.points || [];
  } catch (e) {
    console.error("Failed to load trajectory:", e);
  }
}

async function loadDwellSummary() {
  if (!selectedPerson.value) {
    dwellRooms.value = [];
    return;
  }
  try {
    const data = await cts.getDashboardDwellSummary(
      selectedPerson.value,
      selectedDate.value || undefined
    );
    dwellRooms.value = data.rooms || [];
  } catch (e) {
    console.error("Failed to load dwell summary:", e);
  }
}


function formatTime(iso) {
  return formatTimeOnly(iso);
}

function formatDuration(seconds) {
  if (!seconds) return "0m";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}
</script>
