<template>
  <div>
    <div class="d-flex align-center mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Continuous Tracking Dashboard</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Real-time tracking, signals, and dwell data for monitored persons.
        </div>
      </div>
    </div>

    <!-- Presence widgets -->
    <div class="mb-6">
      <div class="d-flex align-center mb-2">
        <div class="text-subtitle-2 font-weight-bold">Current Presence</div>
        <div class="text-caption text-medium-emphasis ml-2">Click a card to load details</div>
      </div>
      <v-row dense>
        <v-col v-for="person in trackedPersons" :key="person.id" cols="12" sm="6" md="4">
          <PresenceWidget
            :person-id="person.id"
            :person-label="person.display_name"
            :poll-seconds="10"
            :selected="selectedPerson === person.id"
            @click="onPresenceClick(person.id)"
          />
        </v-col>
        <v-col v-if="!trackedPersons.length" cols="12">
          <v-card class="glass-card">
            <v-card-text class="text-center text-medium-emphasis py-6">
              No persons configured for tracking. Add household members in
              <router-link to="/admin/persons">Persons</router-link>.
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>
    </div>

    <!-- Filters -->
    <v-card variant="tonal" class="mb-4 pa-3">
      <v-row dense align="center">
        <v-col cols="12" sm="auto" class="d-flex align-center">
          <v-chip
            v-if="selectedPerson"
            color="primary"
            variant="flat"
            closable
            @click:close="clearPerson"
          >
            <v-icon start size="18">mdi-account</v-icon>
            {{ selectedPersonLabel }}
          </v-chip>
          <span v-else class="text-body-2 text-medium-emphasis">
            <v-icon size="18" class="mr-1">mdi-account-multiple</v-icon>
            All persons
          </span>
        </v-col>

        <v-col cols="12" sm="auto">
          <v-text-field
            v-model="selectedDate"
            type="date"
            label="Date"
            prepend-inner-icon="mdi-calendar"
            density="compact"
            hide-details
            clearable
            @update:modelValue="loadDwellSummary"
          />
        </v-col>

        <v-col cols="12" sm="auto" class="d-flex align-center">
          <div class="text-body-2 text-medium-emphasis mr-2">Signal window:</div>
          <div class="d-flex ga-2">
            <v-btn
              v-for="opt in windowOptions"
              :key="opt.value"
              size="small"
              :variant="windowHours === opt.value ? 'flat' : 'outlined'"
              :color="windowHours === opt.value ? 'primary' : undefined"
              @click="windowHours = opt.value; reloadSignals()"
            >{{ opt.label }}</v-btn>
          </div>
        </v-col>

        <v-spacer />

        <v-col cols="12" sm="auto">
          <v-btn prepend-icon="mdi-refresh" variant="tonal" :loading="loading" @click="refreshAll">
            Refresh
          </v-btn>
        </v-col>
      </v-row>
    </v-card>

    <!-- Signal summary chips (derived from the same CC signals source) -->
    <v-row class="mb-2">
      <v-col v-for="(info, kind) in signalSummary" :key="kind" cols="6" sm="4" md="2">
        <v-card :color="severityColor(info.max_severity)" variant="tonal">
          <v-card-text class="text-center pa-3">
            <div class="text-h5 font-weight-bold">{{ info.count }}</div>
            <div class="text-caption">{{ kind.replace(/_/g, " ") }}</div>
            <v-chip :color="severityColor(info.max_severity)" size="x-small" class="mt-1">
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

    <v-row>
      <!-- Signal timeline (left column) -->
      <v-col cols="12" md="7">
        <v-card height="100%">
          <v-card-title class="d-flex align-center">
            <v-icon start>mdi-timeline-alert</v-icon>
            Signal Timeline
            <v-spacer />
            <span class="text-caption text-medium-emphasis font-weight-regular">
              {{ signalTotal }} total
            </span>
          </v-card-title>
          <v-card-text class="pa-0">
            <v-list v-if="signals.length > 0" lines="two" density="compact">
              <v-list-item
                v-for="sig in signals"
                :key="sig.id"
                :subtitle="`${sig.person_id || ''} · value: ${sig.value}`"
              >
                <template #prepend>
                  <v-icon :color="severityColor(sig.severity)" size="small">
                    {{ severityIcon(sig.severity) }}
                  </v-icon>
                </template>
                <template #title>
                  <span class="text-body-2 font-weight-medium">
                    {{ sig.signal_type.replace(/_/g, " ") }}
                  </span>
                  <v-chip
                    :color="severityColor(sig.severity)"
                    size="x-small"
                    class="ml-2"
                    variant="flat"
                  >
                    {{ sig.severity }}
                  </v-chip>
                  <v-chip
                    v-if="sig.acknowledged_at"
                    size="x-small"
                    class="ml-1"
                    variant="tonal"
                    color="success"
                  >
                    acked
                  </v-chip>
                </template>
                <template #append>
                  <div class="d-flex align-center ga-1">
                    <span class="text-caption text-medium-emphasis">
                      {{ formatTime(sig.received_at) }}
                    </span>
                    <v-btn
                      icon="mdi-delete-outline"
                      size="x-small"
                      variant="text"
                      color="error"
                      :loading="deletingId === sig.id"
                      @click.stop="deleteSignal(sig)"
                    />
                  </div>
                </template>
              </v-list-item>
            </v-list>
            <div v-else-if="!signalLoading" class="text-center text-medium-emphasis py-8">
              No signals found.
            </div>
            <v-progress-linear v-if="signalLoading" indeterminate color="primary" />
          </v-card-text>
          <!-- Signal pagination (server-side) -->
          <div v-if="signalTotal > signalPageSize" class="d-flex align-center justify-space-between pa-3 border-t">
            <span class="text-caption text-medium-emphasis">
              Page {{ signalPage }} of {{ signalTotalPages }}
            </span>
            <div class="d-flex ga-1">
              <v-btn
                icon="mdi-chevron-left"
                size="small"
                variant="text"
                :disabled="signalPage <= 1"
                @click="signalPage--; loadSignals()"
              />
              <v-btn
                icon="mdi-chevron-right"
                size="small"
                variant="text"
                :disabled="signalPage >= signalTotalPages"
                @click="signalPage++; loadSignals()"
              />
            </div>
          </div>
        </v-card>
      </v-col>

      <!-- Right column: posture + dwell + trajectory -->
      <v-col cols="12" md="5">

        <!-- Posture distribution (selected person) -->
        <v-card class="mb-4">
          <v-card-title>
            <v-icon start>mdi-human-greeting-variant</v-icon>
            Posture Distribution
            <v-chip
              v-if="latestPosture && latestPosture !== 'unknown'"
              :color="postureColor(latestPosture)"
              size="x-small"
              variant="flat"
              class="ml-2"
            >
              {{ latestPosture }}
            </v-chip>
          </v-card-title>
          <v-card-text>
            <template v-if="selectedPerson">
              <PostureDistributionBar v-if="trajectoryPoints.length" :points="trajectoryPoints" />
              <div v-else class="text-caption text-medium-emphasis text-center py-2">
                No trajectory data for posture analysis.
              </div>
            </template>
            <div v-else class="text-caption text-medium-emphasis text-center py-2">
              Select a person to view their posture distribution.
            </div>
          </v-card-text>
        </v-card>

        <!-- Room dwell -->
        <v-card class="mb-4">
          <v-card-title>
            <v-icon start>mdi-door-open</v-icon>
            Room Dwell: {{ selectedDate || "Today" }}
          </v-card-title>
          <v-card-text>
            <div v-if="dwellRooms.length > 0">
              <div v-for="room in dwellRooms" :key="room.room_name" class="mb-2">
                <div class="d-flex justify-space-between text-body-2 mb-1">
                  <span>{{ room.room_name }}</span>
                  <span class="text-medium-emphasis">{{ formatDuration(room.duration_seconds) }}</span>
                </div>
                <v-progress-linear :model-value="room.fraction * 100" color="primary" height="8" rounded />
              </div>
            </div>
            <div v-else class="text-center text-medium-emphasis py-4">
              {{ selectedPerson ? "No dwell data for this day." : "Select a person to view dwell data." }}
            </div>
          </v-card-text>
        </v-card>

        <!-- Floor-plan trajectory -->
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
                <line v-for="x in [100, 200, 300]" :key="`vg-${x}`" :x1="x" y1="0" :x2="x" y2="300" style="stroke: var(--cc-divider); stroke-width: 1" />
                <line v-for="y in [75, 150, 225]"  :key="`hg-${y}`" x1="0" :y1="y" x2="400" :y2="y"  style="stroke: var(--cc-divider); stroke-width: 1" />
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
                {{ trajectoryPoints.length }} points · last seen {{ formatTime(trajectoryPoints[0]?.observed_at) }}
              </div>
            </div>
            <div v-else class="text-center text-medium-emphasis py-4">
              {{ selectedPerson ? "No trajectory data." : "Select a person to view trajectory." }}
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <v-snackbar v-model="snack" :color="snackColor" timeout="3000">{{ snackText }}</v-snackbar>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { cts } from "../../services/cts.js";
import { api } from "../../services/api.js";
import PresenceWidget from "../../components/cts/PresenceWidget.vue";
import PostureDistributionBar from "../../components/cts/identity/PostureDistributionBar.vue";
import { severityColor, severityIcon } from "../../composables/useCtsSeverity";
import { formatTimeOnly } from "../../services/timezone.js";
import { useNotify } from "../../composables/useNotify.js";

const { snack, snackText, snackColor, notify } = useNotify();

const selectedPerson = ref(null);
const selectedDate   = ref(null);
const windowHours    = ref(24);
const loading        = ref(false);
const signalLoading  = ref(false);
const deletingId     = ref(null);
const trackedPersons = ref([]);

// Signals: server-side pagination via /cts/signals (CC table, consistent with summary)
const signals        = ref([]);
const signalTotal    = ref(0);
const signalPage     = ref(1);
const signalPageSize = 25;
const signalTotalPages = computed(() => Math.max(1, Math.ceil(signalTotal.value / signalPageSize)));

// Summary is derived client-side from the 24h full count (separate call covers full window)
const signalSummary  = ref({});

const trajectoryPoints = ref([]);
const dwellRooms       = ref([]);

const windowOptions = [
  { label: "6h",  value: 6 },
  { label: "12h", value: 12 },
  { label: "24h", value: 24 },
  { label: "48h", value: 48 },
  { label: "7d",  value: 168 },
];

const selectedPersonLabel = computed(() => {
  if (!selectedPerson.value) return "";
  const person = trackedPersons.value.find((p) => p.id === selectedPerson.value);
  return person?.display_name || person?.name || selectedPerson.value;
});

const svgPath = computed(() => {
  if (trajectoryPoints.value.length < 2) return null;
  const pts = [...trajectoryPoints.value].sort((a, b) => new Date(a.observed_at) - new Date(b.observed_at));
  return pts.map((p) => `${toSvgX(p.ground_x)},${toSvgY(p.ground_y)}`).join(" ");
});

const latestPoint   = computed(() => {
  if (!trajectoryPoints.value.length) return null;
  const p = trajectoryPoints.value[0];
  return { svgX: toSvgX(p.ground_x), svgY: toSvgY(p.ground_y) };
});
const latestPosture = computed(() => trajectoryPoints.value[0]?.posture || null);

function toSvgX(x) { return Math.max(20, Math.min(380, 20 + (x / 10) * 360)); }
function toSvgY(y) { return Math.max(20, Math.min(280, 280 - (y / 8) * 260)); }

onMounted(async () => {
  try {
    trackedPersons.value = await api.getPersons();
  } catch (e) {
    console.error("Failed to load persons:", e);
  }
  await Promise.all([loadSignals(), loadSummary()]);
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

function onPresenceClick(personId) {
  selectedPerson.value = selectedPerson.value === personId ? null : personId;
  if (!selectedPerson.value) {
    trajectoryPoints.value = [];
    dwellRooms.value = [];
  }
  reloadSignals();
  loadSummary();
  if (selectedPerson.value) {
    loadTrajectory();
    loadDwellSummary();
  }
}

function clearPerson() {
  selectedPerson.value = null;
  trajectoryPoints.value = [];
  dwellRooms.value = [];
  reloadSignals();
  loadSummary();
}

// Reset page and reload signals (used when filters change)
function reloadSignals() {
  signalPage.value = 1;
  loadSignals();
}

// Load the current page of signals from the CC-side signal store.
// Using /cts/signals (not /cts/dashboard/signals) so the data source matches
// the summary endpoint and delete operations work against the same table.
async function loadSignals() {
  signalLoading.value = true;
  try {
    const data = await cts.getSignals({
      person_id:    selectedPerson.value || undefined,
      window_hours: windowHours.value,
      limit:        signalPageSize,
      offset:       (signalPage.value - 1) * signalPageSize,
    });
    signals.value     = data.signals || [];
    signalTotal.value = data.total ?? data.count ?? 0;
  } catch (e) {
    console.error("Failed to load signals:", e);
  } finally {
    signalLoading.value = false;
  }
}

// Summary reads the full window count (not just the current page) from the same CC table.
async function loadSummary() {
  try {
    const data = await cts.getSignalSummary(selectedPerson.value);
    signalSummary.value = data.by_type || {};
  } catch (e) {
    console.error("Failed to load signal summary:", e);
  }
}

async function loadTrajectory() {
  if (!selectedPerson.value) { trajectoryPoints.value = []; return; }
  try {
    const data = await cts.getDashboardTrajectory(selectedPerson.value, { limit: 200 });
    trajectoryPoints.value = data.points || [];
  } catch (e) {
    console.error("Failed to load trajectory:", e);
  }
}

async function loadDwellSummary() {
  if (!selectedPerson.value) { dwellRooms.value = []; return; }
  try {
    const data = await cts.getDashboardDwellSummary(selectedPerson.value, selectedDate.value || undefined);
    dwellRooms.value = data.rooms || [];
  } catch (e) {
    console.error("Failed to load dwell summary:", e);
  }
}

async function deleteSignal(sig) {
  deletingId.value = sig.id;
  try {
    await cts.deleteSignal(sig.id);
    signals.value     = signals.value.filter((s) => s.id !== sig.id);
    signalTotal.value = Math.max(0, signalTotal.value - 1);
    // Refresh summary chips to reflect the deletion.
    loadSummary();
    notify("Signal deleted", "success");
  } catch (e) {
    notify(e.message || "Delete failed", "error");
  } finally {
    deletingId.value = null;
  }
}

function formatTime(iso)     { return formatTimeOnly(iso); }

function formatDuration(seconds) {
  if (!seconds) return "0m";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function postureColor(posture) {
  return { standing: "teal", sitting: "amber", walking: "blue", lying: "purple" }[posture] || undefined;
}
</script>
