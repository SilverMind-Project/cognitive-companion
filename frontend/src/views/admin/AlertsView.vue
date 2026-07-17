<template>
  <div>
    <!-- Page header -->
    <div class="d-flex align-center flex-wrap ga-3 mb-4">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Alert Center</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Rule-based alerts and CTS behavioural signals.
        </div>
      </div>
      <v-spacer />
      <v-btn
        v-if="selected.length > 0"
        color="error"
        variant="tonal"
        prepend-icon="mdi-delete"
        :loading="deleting"
        @click="confirmBulkDelete"
      >
        Delete {{ selected.length }} selected
      </v-btn>
      <v-btn variant="tonal" prepend-icon="mdi-refresh" :loading="loading" @click="reload">
        Refresh
      </v-btn>
    </div>

    <!-- Filter bar -->
    <v-card variant="tonal" class="mb-4 pa-3">
      <div class="d-flex flex-wrap align-center ga-3">
        <v-chip-group v-model="sourceFilter" mandatory @update:model-value="onSourceChange">
          <v-chip value="all" filter variant="tonal">All</v-chip>
          <v-chip value="rule" filter variant="tonal" color="primary">Rules</v-chip>
          <v-chip value="cts" filter variant="tonal" color="info">CTS signals</v-chip>
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
          @update:model-value="onFilterChange"
        />
        <v-select
          v-model="statusFilter"
          :items="statusOptions"
          label="Status"
          variant="outlined"
          density="compact"
          hide-details
          style="width: 180px"
          @update:model-value="onFilterChange"
        />
        <v-select
          v-model="severityFilter"
          :items="severityOptions"
          label="Severity"
          variant="outlined"
          density="compact"
          clearable
          hide-details
          style="width: 150px"
          @update:model-value="onFilterChange"
        />
        <v-select
          v-if="sourceFilter !== 'rule'"
          v-model="windowHours"
          :items="windowOptions"
          label="CTS window"
          variant="outlined"
          density="compact"
          hide-details
          style="width: 150px"
          @update:model-value="onFilterChange"
        />
      </div>
    </v-card>

    <!-- Data table -->
    <v-card class="glass-card">
      <!-- Bulk action bar (shown when rows are selected) -->
      <v-expand-transition>
        <div
          v-if="selected.length > 0"
          class="d-flex align-center pa-3 ga-2 bg-error-lighten-5 border-b"
        >
          <v-icon color="error" size="18">mdi-checkbox-marked</v-icon>
          <span class="text-body-2 font-weight-medium">{{ selected.length }} selected</span>
          <v-btn
            size="small"
            variant="outlined"
            color="error"
            prepend-icon="mdi-delete"
            :loading="deleting"
            @click="confirmBulkDelete"
          >
            Delete selected
          </v-btn>
          <v-btn size="small" variant="text" @click="selected = []">Clear</v-btn>
        </div>
      </v-expand-transition>

      <v-data-table
        v-model="selected"
        :headers="headers"
        :items="displayRows"
        :loading="loading"
        item-value="_id"
        show-select
        :items-per-page="sourceFilter === 'cts' ? ctsPageSize : 25"
        :items-per-page-options="sourceFilter === 'cts' ? [] : [25, 50, 100]"
      >
        <template #item._source="{ item }">
          <v-chip
            size="x-small"
            :color="item._source === 'cts' ? 'deep-purple' : 'primary'"
            variant="tonal"
          >
            {{ item._source === "cts" ? "CTS" : "Rule" }}
          </v-chip>
        </template>

        <template #item.type="{ item }">
          {{ item.type.replace(/_/g, " ") }}
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
          <div class="d-flex align-center ga-1 justify-end">
            <v-btn
              v-if="item._source === 'cts' && item.status === 'pending'"
              size="x-small"
              variant="text"
              color="primary"
              @click.stop="acknowledge(item._raw)"
            >
              <v-icon start>mdi-check</v-icon>Ack
            </v-btn>
            <v-btn
              v-if="item._source === 'cts'"
              icon="mdi-delete-outline"
              size="x-small"
              variant="text"
              color="error"
              @click.stop="deleteSingle(item)"
            />
            <span v-else class="text-caption text-disabled">read-only</span>
          </div>
        </template>

        <template #no-data>
          <div class="pa-8 text-center">
            <v-icon size="48" color="medium-emphasis" class="mb-2">mdi-bell-off-outline</v-icon>
            <div class="text-h6 text-medium-emphasis">No alerts</div>
            <div class="text-body-2 text-disabled mt-1">
              Alerts and signals will appear here when conditions need attention.
            </div>
          </div>
        </template>

        <!-- CTS server-side pagination footer -->
        <template v-if="sourceFilter === 'cts'" #bottom>
          <div class="d-flex align-center justify-space-between pa-3 border-t">
            <span class="text-caption text-medium-emphasis">
              {{ ctsTotal }} signals · page {{ ctsPage }} of {{ ctsTotalPages || 1 }}
            </span>
            <div class="d-flex align-center ga-2">
              <v-select
                v-model="ctsPageSize"
                :items="[25, 50, 100]"
                density="compact"
                hide-details
                variant="outlined"
                style="width: 90px"
                @update:model-value="onCtsSizeChange"
              />
              <v-btn
                icon="mdi-chevron-left"
                size="small"
                variant="text"
                :disabled="ctsPage <= 1"
                @click="
                  ctsPage--;
                  loadCts();
                "
              />
              <v-btn
                icon="mdi-chevron-right"
                size="small"
                variant="text"
                :disabled="ctsPage >= ctsTotalPages"
                @click="
                  ctsPage++;
                  loadCts();
                "
              />
            </div>
          </div>
        </template>
      </v-data-table>

      <!-- CTS 7-day trend (person selected, CTS visible) -->
      <template v-if="personFilter && sourceFilter !== 'rule' && trend.length">
        <v-divider />
        <v-card-text class="pa-4">
          <div class="d-flex align-center mb-3">
            <v-icon start size="18">mdi-chart-timeline</v-icon>
            <span class="text-subtitle-2 font-weight-medium"
              >7-Day CTS Signal Trend: {{ personFilter }}</span
            >
          </div>
          <v-table density="compact">
            <thead>
              <tr>
                <th>Date</th>
                <th class="text-right">Total</th>
                <th class="text-right">Info</th>
                <th class="text-right">Warning</th>
                <th class="text-right">Emergency</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="day in trend" :key="day.date">
                <td>{{ day.date }}</td>
                <td class="text-right font-weight-bold">{{ day.count }}</td>
                <td class="text-right">{{ day.by_severity.info || 0 }}</td>
                <td class="text-right">{{ day.by_severity.warning || 0 }}</td>
                <td class="text-right">{{ day.by_severity.emergency || 0 }}</td>
              </tr>
            </tbody>
          </v-table>
        </v-card-text>
      </template>
    </v-card>

    <!-- Confirm delete dialog -->
    <v-dialog v-model="deleteDialog" max-width="420">
      <v-card>
        <v-card-title class="d-flex align-center ga-2">
          <v-icon color="error">mdi-delete-alert</v-icon>
          Delete {{ deleteTarget.length }} item{{ deleteTarget.length === 1 ? "" : "s" }}?
        </v-card-title>
        <v-card-text>
          This action is permanent and cannot be undone. CTS signals may be re-inserted by the
          orchestrator if it replays the same event.
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog = false">Cancel</v-btn>
          <v-btn color="error" variant="flat" :loading="deleting" @click="executeDelete">
            Delete
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { useRoute } from "vue-router";
import { api } from "../../services/api.js";
import { cts } from "../../services/cts.js";
import { useNotify } from "../../composables/useNotify.js";
import { formatDateTime, DATETIME_COLUMN_WIDTH } from "../../services/timezone.js";

const route = useRoute();
const { notify } = useNotify();

const loading = ref(false);
const deleting = ref(false);
const ruleRows = ref([]);
const ctsRows = ref([]);
const trend = ref([]);

const ctsPage = ref(1);
const ctsPageSize = ref(50);
const ctsTotal = ref(0);
const ctsTotalPages = computed(() => Math.max(1, Math.ceil(ctsTotal.value / ctsPageSize.value)));

const selected = ref([]);
const deleteDialog = ref(false);
const deleteTarget = ref([]);

const initialSource =
  route.query.source === "cts" ? "cts" : route.query.source === "rule" ? "rule" : "all";
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
const severityOptions = ["critical", "warning", "info"];
const windowOptions = [
  { title: "1 h", value: 1 },
  { title: "6 h", value: 6 },
  { title: "12 h", value: 12 },
  { title: "24 h", value: 24 },
  { title: "48 h", value: 48 },
  { title: "7 d", value: 168 },
];

const headers = [
  { title: "Time", key: "time", width: DATETIME_COLUMN_WIDTH },
  { title: "Source", key: "_source", width: "80px", sortable: false },
  { title: "Type", key: "type" },
  { title: "Person", key: "person" },
  { title: "Room", key: "room" },
  { title: "Severity", key: "severity", width: "110px" },
  { title: "Status", key: "status", width: "150px" },
  { title: "", key: "actions", sortable: false, width: "120px", align: "end" },
];

// ── Row normalizers ────────────────────────────────────────────────────────

function normalizeSeverity(sev) {
  return !sev ? null : sev === "emergency" ? "critical" : sev;
}

function toRuleRow(item) {
  // item is a unified-feed SignalEnvelope with source === "pipeline_rule".
  return {
    _id: item.id, // already unique: "rule:<event_log_id>"
    _source: "rule",
    _raw: item,
    time: item.created_at,
    type: item.kind || "",
    person: item.person_id || null,
    room: item.room_name || null,
    severity: normalizeSeverity(item.severity),
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

// ── Computed ────────────────────────────────────────────────────────────────

const allRows = computed(() =>
  [...ruleRows.value, ...ctsRows.value].sort((a, b) => new Date(b.time) - new Date(a.time)),
);

const filteredRules = computed(() =>
  ruleRows.value.filter((row) => {
    if (personFilter.value && row.person !== personFilter.value) return false;
    if (severityFilter.value && row.severity !== severityFilter.value) return false;
    if (statusFilter.value === "active") return row.status === "active";
    if (statusFilter.value === "resolved") return row.status === "resolved";
    return true;
  }),
);

const filteredCts = computed(() =>
  ctsRows.value.filter((row) => {
    if (severityFilter.value && row.severity !== severityFilter.value) return false;
    if (statusFilter.value === "active") return row.status === "pending";
    if (statusFilter.value === "resolved") return row.status === "acknowledged";
    return true;
  }),
);

const displayRows = computed(() => {
  if (sourceFilter.value === "rule") return filteredRules.value;
  if (sourceFilter.value === "cts") return filteredCts.value;
  // Combined: rules + current CTS page (sorted by time)
  return [...filteredRules.value, ...filteredCts.value].sort(
    (a, b) => new Date(b.time) - new Date(a.time),
  );
});

const personOptions = computed(() => {
  const ids = new Set(allRows.value.map((r) => r.person).filter(Boolean));
  return Array.from(ids).sort();
});

// ── Helpers ─────────────────────────────────────────────────────────────────

function severityChipColor(sev) {
  return { critical: "error", warning: "orange", info: "blue-grey" }[sev] || "grey";
}

function statusColor(row) {
  return row.status === "active" || row.status === "pending" ? "warning" : "success";
}

// ── Data loading ─────────────────────────────────────────────────────────────

async function loadRules() {
  // Pipeline-rule alerts come from the unified signals feed (read-only).
  const params = { source: "pipeline_rule", limit: 100 };
  if (severityFilter.value) {
    params.severity_min = severityFilter.value === "critical" ? "emergency" : severityFilter.value;
  }
  try {
    const data = await api.getSignalsFeed(params);
    ruleRows.value = (data || []).map(toRuleRow);
  } catch {
    ruleRows.value = [];
  }
}

async function loadCts() {
  const params = {
    person_id: personFilter.value || undefined,
    window_hours: windowHours.value,
    limit: ctsPageSize.value,
    offset: (ctsPage.value - 1) * ctsPageSize.value,
  };
  if (severityFilter.value) {
    params.severity = severityFilter.value === "critical" ? "emergency" : severityFilter.value;
  }
  try {
    const data = await cts.getSignals(params);
    ctsRows.value = (data.signals || []).map(toCtsRow);
    ctsTotal.value = data.total ?? data.count ?? 0;
  } catch {
    ctsRows.value = [];
    ctsTotal.value = 0;
  }
}

async function loadTrend() {
  if (!personFilter.value || sourceFilter.value === "rule") {
    trend.value = [];
    return;
  }
  try {
    const data = await cts.getSignalTrend(personFilter.value, 7);
    trend.value = data.trend || [];
  } catch {
    trend.value = [];
  }
}

async function reload() {
  loading.value = true;
  selected.value = [];
  const tasks = [];
  if (sourceFilter.value !== "cts") tasks.push(loadRules());
  if (sourceFilter.value !== "rule") tasks.push(loadCts());
  tasks.push(loadTrend());
  await Promise.allSettled(tasks);
  loading.value = false;
}

function onSourceChange() {
  ctsPage.value = 1;
  selected.value = [];
  reload();
}

function onFilterChange() {
  ctsPage.value = 1;
  selected.value = [];
  reload();
}

function onCtsSizeChange() {
  ctsPage.value = 1;
  selected.value = [];
  loadCts();
}

// ── Actions ──────────────────────────────────────────────────────────────────

async function acknowledge(raw) {
  try {
    await cts.acknowledgeSignal(raw.id);
    ctsRows.value = ctsRows.value.map((r) =>
      r._raw.id === raw.id ? { ...r, status: "acknowledged" } : r,
    );
    notify("Signal acknowledged", "success");
    window.dispatchEvent(new CustomEvent("cc:alerts-changed"));
  } catch (e) {
    notify(e.message, "error");
  }
}

function deleteSingle(item) {
  deleteTarget.value = [item];
  deleteDialog.value = true;
}

function confirmBulkDelete() {
  // Only CTS signals are deletable; pipeline-rule feed rows are read-only.
  const items = displayRows.value.filter(
    (r) => selected.value.includes(r._id) && r._source === "cts",
  );
  deleteTarget.value = items;
  deleteDialog.value = true;
}

async function executeDelete() {
  deleting.value = true;
  try {
    const ctsItems = deleteTarget.value.filter((r) => r._source === "cts");
    if (ctsItems.length === 0) {
      notify("Only CTS signals can be deleted", "info");
      return;
    }

    if (ctsItems.length === 1) {
      await cts.deleteSignal(ctsItems[0]._raw.id);
    } else {
      await cts.batchDeleteSignals(ctsItems.map((r) => r._raw.id));
    }

    const deletedIds = new Set(ctsItems.map((r) => r._id));
    ctsRows.value = ctsRows.value.filter((r) => !deletedIds.has(r._id));
    ctsTotal.value = Math.max(0, ctsTotal.value - ctsItems.length);
    selected.value = selected.value.filter((id) => !deletedIds.has(id));
    notify(`Deleted ${ctsItems.length} signal${ctsItems.length === 1 ? "" : "s"}`, "success");
    window.dispatchEvent(new CustomEvent("cc:alerts-changed"));
  } catch (e) {
    notify(e.message || "Delete failed", "error");
  } finally {
    deleting.value = false;
    deleteDialog.value = false;
    deleteTarget.value = [];
  }
}

// ── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(reload);
</script>
