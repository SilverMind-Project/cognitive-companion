<template>
  <div>
    <div class="d-flex align-center flex-wrap ga-3 mb-4">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Alert Center</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Rule-based alerts and CTS behavioural signals in one view.
        </div>
      </div>
      <v-spacer />
      <v-btn variant="tonal" prepend-icon="mdi-refresh" @click="load" :loading="loading">
        Refresh
      </v-btn>
    </div>

    <!-- Filter bar -->
    <div class="d-flex flex-wrap align-center ga-3 mb-4">
      <v-chip-group v-model="sourceFilter" mandatory>
        <v-chip value="all" filter variant="tonal">All</v-chip>
        <v-chip value="rule" filter variant="tonal" color="primary">Rules</v-chip>
        <v-chip value="cts" filter variant="tonal" color="deep-purple">CTS</v-chip>
      </v-chip-group>

      <v-select
        v-model="personFilter"
        :items="personOptions"
        label="Person"
        variant="outlined"
        density="compact"
        clearable
        hide-details
        style="width: 200px"
      />
      <v-select
        v-model="statusFilter"
        :items="statusOptions"
        label="Status"
        variant="outlined"
        density="compact"
        hide-details
        style="width: 180px"
      />
      <v-select
        v-model="severityFilter"
        :items="['critical', 'warning', 'info']"
        label="Severity"
        variant="outlined"
        density="compact"
        clearable
        hide-details
        style="width: 150px"
      />
      <v-select
        v-if="sourceFilter !== 'rule'"
        v-model="windowHours"
        :items="[1, 6, 12, 24, 48, 168]"
        label="CTS Window (h)"
        variant="outlined"
        density="compact"
        hide-details
        style="width: 160px"
        @update:model-value="load"
      />
    </div>

    <v-card class="glass-card">
      <v-data-table
        :headers="headers"
        :items="filteredRows"
        :loading="loading"
        item-value="_id"
        :footer-props="{ 'items-per-page-options': [20, 50, 100] }"
      >
        <template #item._source="{ item }">
          <v-chip
            size="x-small"
            :color="item._source === 'cts' ? 'deep-purple' : 'primary'"
            variant="tonal"
          >
            {{ item._source === 'cts' ? 'CTS' : 'Rule' }}
          </v-chip>
        </template>
        <template #item.type="{ item }">
          {{ item.type.replace(/_/g, ' ') }}
        </template>
        <template #item.severity="{ item }">
          <v-chip
            v-if="item.severity"
            :color="severityChipColor(item.severity)"
            size="small"
            density="compact"
            variant="flat"
          >
            {{ item.severity }}
          </v-chip>
          <span v-else class="text-medium-emphasis">—</span>
        </template>
        <template #item.status="{ item }">
          <v-chip :color="statusColor(item)" size="small" variant="tonal">
            {{ item.status }}
          </v-chip>
        </template>
        <template #item.time="{ item }">
          {{ formatDateTime(item.time) }}
        </template>
        <template #item.actions="{ item }">
          <v-btn
            v-if="item._source === 'rule' && item.status === 'active'"
            size="x-small"
            variant="text"
            color="success"
            @click="dismiss(item._raw)"
          >
            Dismiss
          </v-btn>
          <v-btn
            v-else-if="item._source === 'cts' && item.status === 'pending'"
            size="x-small"
            variant="text"
            color="primary"
            @click="acknowledge(item._raw)"
          >
            <v-icon start>mdi-check</v-icon>
            Ack
          </v-btn>
        </template>
        <template #no-data>
          <div class="pa-6 text-center">
            <v-card flat>
              <v-card-text class="text-grey text-h6">No alerts</v-card-text>
              <v-card-text class="text-grey">
                Alerts and signals will appear here when conditions need attention.
              </v-card-text>
            </v-card>
          </div>
        </template>
      </v-data-table>

      <!-- CTS 7-day trend when a person is selected and CTS source is visible -->
      <template v-if="personFilter && sourceFilter !== 'rule' && trend.length">
        <v-divider />
        <v-card-text class="pa-4">
          <div class="d-flex align-center mb-3">
            <v-icon start size="18">mdi-chart-timeline</v-icon>
            <span class="text-subtitle-2 font-weight-semibold">
              7-Day CTS Signal Trend: {{ personFilter }}
            </span>
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
        </v-card-text>
      </template>
    </v-card>

    <v-snackbar v-model="snack" :color="snackColor" timeout="3000">{{ snackText }}</v-snackbar>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from "vue";
import { useRoute } from "vue-router";
import { api } from "../../services/api.js";
import { cts } from "../../services/cts.js";
import { useNotify } from "../../composables/useNotify.js";
import { formatDateTime, DATETIME_COLUMN_WIDTH } from "../../services/timezone.js";

const route = useRoute();
const { snack, snackText, snackColor, notify } = useNotify();

const loading = ref(false);
const ruleRows = ref([]);
const ctsRows = ref([]);
const trend = ref([]);

// Initialize source filter from ?source= query param (for redirects from /cts/signals)
const initialSource = route.query.source === "cts" ? "cts" : route.query.source === "rule" ? "rule" : "all";
const sourceFilter = ref(initialSource);
const personFilter = ref(null);
const statusFilter = ref("");
const severityFilter = ref(null);
const windowHours = ref(24);

const statusOptions = [
  { title: "All", value: "" },
  { title: "Active / Pending", value: "active" },
  { title: "Resolved / Acknowledged", value: "resolved" },
];

const headers = [
  { title: "Time", key: "time", width: DATETIME_COLUMN_WIDTH },
  { title: "Source", key: "_source", width: "80px", sortable: false },
  { title: "Type", key: "type" },
  { title: "Person", key: "person" },
  { title: "Room", key: "room" },
  { title: "Severity", key: "severity", width: "110px" },
  { title: "Status", key: "status", width: "150px" },
  { title: "Actions", key: "actions", sortable: false, width: "90px" },
];

function normalizeSeverity(sev) {
  if (!sev) return null;
  return sev === "emergency" ? "critical" : sev;
}

function toRuleRow(item) {
  return {
    _id: `rule-${item.id}`,
    _source: "rule",
    _raw: item,
    time: item.timestamp,
    type: item.alert_type || "",
    person: null,
    room: item.room_name || null,
    severity: null,
    status: item.resolved ? "resolved" : "active",
  };
}

function toCtsRow(item) {
  return {
    _id: `cts-${item.id}`,
    _source: "cts",
    _raw: item,
    time: item.received_at || item.window_start,
    type: item.signal_type || "",
    person: item.person_id || null,
    room: null,
    severity: normalizeSeverity(item.severity),
    status: item.acknowledged_at ? "acknowledged" : "pending",
  };
}

const allRows = computed(() =>
  [...ruleRows.value, ...ctsRows.value].sort(
    (a, b) => new Date(b.time) - new Date(a.time)
  )
);

const filteredRows = computed(() => {
  return allRows.value.filter((row) => {
    if (sourceFilter.value !== "all" && row._source !== sourceFilter.value) return false;
    if (personFilter.value && row.person !== personFilter.value) return false;
    if (severityFilter.value && row.severity !== severityFilter.value) return false;
    if (statusFilter.value === "active") return row.status === "active" || row.status === "pending";
    if (statusFilter.value === "resolved") return row.status === "resolved" || row.status === "acknowledged";
    return true;
  });
});

const personOptions = computed(() => {
  const ids = new Set(allRows.value.map((r) => r.person).filter(Boolean));
  return Array.from(ids).sort();
});

function severityChipColor(sev) {
  const map = { critical: "error", warning: "orange", info: "blue-grey" };
  return map[sev] || "grey";
}

function statusColor(row) {
  return row.status === "active" || row.status === "pending" ? "warning" : "success";
}

async function load() {
  loading.value = true;
  const ruleParams = statusFilter.value
    ? { resolved: statusFilter.value === "resolved" ? "true" : "false" }
    : {};
  const ctsParams = {
    person_id: personFilter.value || undefined,
    window_hours: windowHours.value,
  };
  const [ruleResult, ctsResult] = await Promise.allSettled([
    api.getAlerts(ruleParams),
    cts.getSignals(ctsParams),
  ]);
  ruleRows.value =
    ruleResult.status === "fulfilled" ? ruleResult.value.map(toRuleRow) : [];
  const signals =
    ctsResult.status === "fulfilled" ? ctsResult.value.signals || [] : [];
  ctsRows.value = signals.map(toCtsRow);
  loading.value = false;
}

async function dismiss(raw) {
  try {
    await api.alertAction(raw.id, { action: "dismiss" });
    ruleRows.value = ruleRows.value.filter((r) => r._raw.id !== raw.id);
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function acknowledge(raw) {
  try {
    await cts.acknowledgeSignal(raw.id);
    ctsRows.value = ctsRows.value.map((r) =>
      r._raw.id === raw.id ? { ...r, status: "acknowledged" } : r
    );
  } catch (e) {
    notify(e.message, "error");
  }
}

watch(personFilter, async (personId) => {
  if (personId && sourceFilter.value !== "rule") {
    try {
      const data = await cts.getSignalTrend(personId, 7);
      trend.value = data.trend || [];
    } catch {
      trend.value = [];
    }
  } else {
    trend.value = [];
  }
  load();
});

onMounted(load);
</script>
