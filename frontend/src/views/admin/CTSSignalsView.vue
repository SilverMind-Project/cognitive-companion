<template>
  <div>
    <v-row>
      <!-- Filters -->
      <v-col cols="12">
        <v-card>
          <v-card-title>Filters</v-card-title>
          <v-card-text>
            <v-row>
              <v-col cols="12" sm="4">
                <v-select
                  v-model="filters.person_id"
                  :items="persons"
                  label="Person"
                  clearable
                  @update:modelValue="loadSignals"
                />
              </v-col>
              <v-col cols="12" sm="3">
                <v-select
                  v-model="filters.signal_type"
                  :items="signalTypes"
                  label="Signal Type"
                  clearable
                  @update:modelValue="loadSignals"
                />
              </v-col>
              <v-col cols="12" sm="3">
                <v-select
                  v-model="filters.severity"
                  :items="['info', 'warning', 'emergency']"
                  label="Severity"
                  clearable
                  @update:modelValue="loadSignals"
                />
              </v-col>
              <v-col cols="12" sm="2">
                <v-select
                  v-model="filters.window_hours"
                  :items="[1, 6, 12, 24, 48, 168]"
                  label="Window (h)"
                  @update:modelValue="loadSignals"
                />
              </v-col>
            </v-row>
          </v-card-text>
        </v-card>
      </v-col>

      <!-- Signals Table -->
      <v-col cols="12">
        <v-card>
          <v-card-title>
            Dementia Signals
            <v-spacer />
            <v-text-field
              v-model="search"
              label="Search"
              prepend-inner-icon="mdi-magnify"
              density="compact"
              variant="solo-filled"
              hide-details
              style="max-width: 240px"
            />
          </v-card-title>
          <v-data-table
            :headers="headers"
            :items="signals"
            :search="search"
            item-value="id"
            class="elevation-0"
            :footer-props="{ 'items-per-page-options': [20, 50, 100] }"
          >
            <template v-slot:item.signal_type="{ value }">
              <v-chip :color="severityColor(value)" size="small" variant="tonal">
                {{ signalIcons[value] }} {{ value.replace(/_/g, " ") }}
              </v-chip>
            </template>
            <template v-slot:item.severity="{ value }">
              <v-chip :color="severityColor(value)" size="small" density="compact" variant="flat">
                {{ value }}
              </v-chip>
            </template>
            <template v-slot:item.acknowledged_at="{ value }">
              <v-icon v-if="value" color="green" size="small">mdi-check-circle</v-icon>
              <v-icon v-else color="orange" size="small">mdi-alert-circle</v-icon>
            </template>
            <template v-slot:item.actions="{ item }">
              <v-btn
                v-if="!item.acknowledged_at"
                size="x-small"
                variant="text"
                color="primary"
                @click="acknowledge(item.id)"
              >
                <v-icon start>mdi-check</v-icon>
                Ack
              </v-btn>
            </template>
          </v-data-table>
        </v-card>
      </v-col>

      <!-- Trend Chart -->
      <v-col cols="12" v-if="selectedPerson">
        <v-card>
          <v-card-title>
            <v-icon start>mdi-chart-timeline</v-icon>
            7-Day Trend: {{ selectedPerson }}
          </v-card-title>
          <v-card-text>
            <v-simple-table v-if="trend.length > 0" density="compact">
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
            </v-simple-table>
            <div v-else class="text-center text-medium-emphasis py-6">
              No trend data available.
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from "vue";
import { cts } from "../../services/cts.js";

const signals = ref([]);
const trend = ref([]);
const search = ref("");
const selectedPerson = ref(null);

const filters = ref({
  person_id: null,
  signal_type: null,
  severity: null,
  window_hours: 24,
});

const signalTypes = [
  "pacing",
  "room_revisit_rate",
  "bathroom_dwell_anomaly",
  "sundowning_index",
  "nighttime_movement",
  "stillness_anomaly",
  "absence",
];

const signalIcons = {
  pacing: "🚶",
  room_revisit_rate: "🔄",
  bathroom_dwell_anomaly: "🚽",
  sundowning_index: "🌅",
  nighttime_movement: "🌙",
  stillness_anomaly: "😴",
  absence: "❓",
};

const persons = computed(() => {
  const ids = new Set(signals.value.map((s) => s.person_id));
  return Array.from(ids).sort();
});

const headers = [
  { title: "Type", key: "signal_type", width: "20%" },
  { title: "Person", key: "person_id", width: "12%" },
  { title: "Severity", key: "severity", width: "10%" },
  { title: "Value", key: "value", width: "8%" },
  { title: "Z-Score", key: "z_score", width: "8%" },
  { title: "Window Start", key: "window_start", width: "15%" },
  { title: "Window End", key: "window_end", width: "15%" },
  { title: "Acknowledged", key: "acknowledged_at", width: "10%" },
  { title: "Received", key: "received_at", width: "10%" },
  { title: "Actions", key: "actions", width: "7%", sortable: false },
];

onMounted(() => {
  loadSignals();
});

async function loadSignals() {
  try {
    const data = await cts.getSignals({
      person_id: filters.value.person_id,
      signal_type: filters.value.signal_type,
      severity: filters.value.severity,
      window_hours: filters.value.window_hours,
    });
    signals.value = data.signals || [];
  } catch (e) {
    console.error("Failed to load signals:", e);
  }
}

async function loadTrend(personId) {
  try {
    const data = await cts.getSignalTrend(personId, 7);
    trend.value = data.trend || [];
  } catch (e) {
    console.error("Failed to load trend:", e);
  }
}

async function acknowledge(signalId) {
  try {
    await cts.acknowledgeSignal(signalId);
    signals.value = signals.value.filter((s) => s.id !== signalId);
  } catch (e) {
    console.error("Failed to acknowledge signal:", e);
  }
}

function severityColor(severity) {
  const map = { info: "grey", warning: "orange", emergency: "red" };
  return map[severity] || "grey";
}

watch(selectedPerson, (personId) => {
  if (personId) {
    loadTrend(personId);
  } else {
    trend.value = [];
  }
});
</script>
