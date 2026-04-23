<template>
  <div>
    <v-row>
      <!-- Signal Summary Card -->
      <v-col cols="12" md="4">
        <v-card>
          <v-card-title>
            <v-icon start>mdi-chart-bar</v-icon>
            24h Signal Summary
          </v-card-title>
          <v-card-text v-if="summary && summary.total_signals > 0">
            <div class="text-h4 font-weight-bold mb-2">
              {{ summary.total_signals }}
              <span class="text-body-2 text-medium-emphasis">signals</span>
            </div>
            <v-chip-group orientation="horizontal" wrap>
              <v-chip
                v-for="(data, type) in summary.by_type"
                :key="type"
                :color="severityColor(data.max_severity)"
                variant="tonal"
              >
                {{ type.replace(/_/g, " ") }}
                <v-icon start size="small">mdi-circle-small</v-icon>
                {{ data.count }}
              </v-chip>
            </v-chip-group>
          </v-card-text>
          <v-card-text v-else class="text-center text-medium-emphasis py-8">
            <v-icon size="64">mdi-inbox-outline</v-icon>
            <div class="mt-2">No signals in the last 24 hours</div>
          </v-card-text>
        </v-card>
      </v-col>

      <!-- Unacknowledged Alerts -->
      <v-col cols="12" md="8">
        <v-card>
          <v-card-title>
            <v-icon start>mdi-alert-circle-outline</v-icon>
            Active Alerts
            <v-spacer />
            <v-btn size="small" variant="text" @click="loadUnacknowledged">
              <v-icon start>mdi-refresh</v-icon>
              Refresh
            </v-btn>
          </v-card-title>
          <v-data-table
            :headers="alertHeaders"
            :items="unacknowledged"
            item-value="id"
            :search="search"
            v-model:search="search"
            class="elevation-0"
            no-data-text="No active alerts"
          >
            <template v-slot:item.signal_type="{ value }">
              <v-chip :color="severityColor(value)" size="small" variant="tonal">
                {{ value.replace(/_/g, " ") }}
              </v-chip>
            </template>
            <template v-slot:item.severity="{ value }">
              <v-chip :color="severityColor(value)" size="small" density="compact">
                {{ value }}
              </v-chip>
            </template>
            <template v-slot:item.actions="{ item }">
              <v-btn size="x-small" variant="text" @click="acknowledge(item.id)">
                <v-icon start>mdi-check</v-icon>
                Acknowledge
              </v-btn>
            </template>
          </v-data-table>
        </v-card>
      </v-col>

      <!-- Signals Timeline -->
      <v-col cols="12">
        <v-card>
          <v-card-title>
            <v-icon start>mdi-timeline</v-icon>
            Signals Timeline (Last 24h)
          </v-card-title>
          <v-card-text>
            <v-timeline density="compact" side="end" align="start" density="compact">
              <v-timeline-item
                v-for="signal in recentSignals"
                :key="signal.id"
                :color="severityColor(signal.severity)"
                :dot-icon="signalDot(signal)"
                size="x-small"
              >
                <v-card variant="text" class="pa-2">
                  <div class="d-flex align-center ga-2">
                    <v-chip size="x-small" variant="tonal" :color="severityColor(signal.severity)">
                      {{ signal.signal_type.replace(/_/g, " ") }}
                    </v-chip>
                    <span class="text-caption">{{ signal.person_id }}</span>
                    <span class="text-caption text-medium-emphasis">
                      {{ formatTime(signal.received_at) }}
                    </span>
                  </div>
                </v-card>
              </v-timeline-item>
            </v-timeline>
            <div v-if="recentSignals.length === 0" class="text-center text-medium-emphasis py-6">
              No signals recorded yet.
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { cts } from "../../services/cts.js";

const summary = ref(null);
const unacknowledged = ref([]);
const recentSignals = ref([]);
const search = ref("");

const alertHeaders = [
  { title: "Type", key: "signal_type", width: "20%" },
  { title: "Person", key: "person_id", width: "15%" },
  { title: "Severity", key: "severity", width: "12%" },
  { title: "Value", key: "value", width: "10%" },
  { title: "Window", key: "window_start", width: "20%" },
  { title: "Received", key: "received_at", width: "15%" },
  { title: "Actions", key: "actions", width: "8%", sortable: false },
];

onMounted(() => {
  loadSummary();
  loadUnacknowledged();
  loadRecentSignals();
});

async function loadSummary() {
  try {
    summary.value = await cts.getSignalSummary();
  } catch (e) {
    console.error("Failed to load signal summary:", e);
  }
}

async function loadUnacknowledged() {
  try {
    const data = await cts.getUnacknowledged({ window_hours: 24, limit: 50 });
    unacknowledged.value = data.signals || [];
  } catch (e) {
    console.error("Failed to load unacknowledged signals:", e);
  }
}

async function loadRecentSignals() {
  try {
    const data = await cts.getSignals({ window_hours: 24, limit: 100 });
    recentSignals.value = data.signals || [];
  } catch (e) {
    console.error("Failed to load recent signals:", e);
  }
}

async function acknowledge(signalId) {
  try {
    await cts.acknowledgeSignal(signalId);
    unacknowledged.value = unacknowledged.value.filter((s) => s.id !== signalId);
    await loadSummary();
  } catch (e) {
    console.error("Failed to acknowledge signal:", e);
  }
}

function severityColor(severity) {
  const map = { info: "grey", warning: "orange", emergency: "red" };
  return map[severity] || "grey";
}

function signalDot(signal) {
  const icons = {
    pacing: "mdi-walk",
    sundowning_index: "mdi-weather-night",
    bathroom_dwell_anomaly: "mdi-toilet",
    stillness_anomaly: "mdi-bed",
    nighttime_movement: "mdi-moon-waning-crescent",
  };
  return icons[signal.signal_type] || "mdi-alert";
}

function formatTime(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleTimeString();
  } catch {
    return iso;
  }
}
</script>
