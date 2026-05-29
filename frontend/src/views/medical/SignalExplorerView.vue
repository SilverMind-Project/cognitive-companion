<template>
  <div>
    <div class="d-flex align-center mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold">Signal Explorer</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Review dementia signals with evidence drill-down for clinical validation.
        </div>
      </div>
      <v-spacer />
      <v-btn variant="tonal" prepend-icon="mdi-refresh" :loading="loading" @click="fetch()">Refresh</v-btn>
    </div>

    <v-alert v-if="error" type="error" class="mb-4" closable @click:close="error = ''">{{ error }}</v-alert>

    <!-- Filter bar -->
    <v-card variant="flat" class="mb-4 px-4 py-2" border>
      <v-row dense align="center">
        <v-col cols="12" sm="4" md="3">
          <v-select
            v-model="filters.kind"
            :items="kindOptions"
            label="Signal kind"
            variant="outlined"
            density="compact"
            multiple
            clearable
            hide-details
            @update:model-value="fetch()"
          />
        </v-col>
        <v-col cols="6" sm="4" md="2">
          <v-select
            v-model="filters.severity"
            :items="['info','warning','emergency']"
            label="Severity"
            variant="outlined"
            density="compact"
            multiple
            clearable
            hide-details
            @update:model-value="fetch()"
          />
        </v-col>
        <v-col cols="6" sm="4" md="2">
          <v-select
            v-model="filters.timeRange"
            :items="timeRangeOptions"
            label="Time range"
            variant="outlined"
            density="compact"
            hide-details
            @update:model-value="onTimeRange()"
          />
        </v-col>
      </v-row>
    </v-card>

    <!-- Aggregates -->
    <v-row class="mb-4" v-if="aggregates.by_kind && Object.keys(aggregates.by_kind).length">
      <v-col cols="12" md="8">
        <v-card class="glass-card pa-3">
          <div class="text-subtitle-2 mb-2">Signal counts by kind</div>
          <svg :viewBox="`0 0 ${Math.max(chartWidth, 200)} 120`" width="100%" height="120">
            <g v-for="(bar, i) in kindBars" :key="bar.kind">
              <rect
                :x="i * barWidth + 4"
                :y="120 - bar.height - 20"
                :width="barWidth - 8"
                :height="bar.height"
                rx="3"
                :fill="bar.color"
              />
              <text
                :x="i * barWidth + barWidth / 2"
                :y="120 - bar.height - 24"
                text-anchor="middle"
                font-size="9"
                fill="#888"
              >{{ bar.count }}</text>
              <text
                :x="i * barWidth + barWidth / 2"
                :y="115"
                text-anchor="middle"
                font-size="8"
                fill="#888"
              >{{ bar.kind.replace(/_/g, ' ') }}</text>
            </g>
          </svg>
        </v-card>
      </v-col>
      <v-col cols="12" md="4">
        <v-card class="glass-card pa-3">
          <div class="text-subtitle-2 mb-2">Top rooms</div>
          <div v-for="(count, room) in topRooms" :key="room" class="d-flex align-center ga-2 mb-1">
            <span class="text-caption" style="min-width: 80px;">{{ room }}</span>
            <v-progress-linear :model-value="(count / maxRoomCount) * 100" height="6" rounded color="primary" />
            <span class="text-caption text-medium-emphasis">{{ count }}</span>
          </div>
        </v-card>
      </v-col>
    </v-row>

    <!-- Signal table -->
    <v-card class="glass-card">
      <v-data-table
        :headers="headers"
        :items="signals"
        :loading="loading"
        items-per-page-text="Signals per page"
        item-value="id"
        @click:row="openEvidence"
      >
        <template #item.signal_type="{ item }">
          <v-chip size="x-small" variant="tonal">{{ (item.signal_type || '').replace(/_/g, ' ') }}</v-chip>
        </template>
        <template #item.severity="{ item }">
          <v-chip
            size="x-small"
            :color="item.severity === 'emergency' ? 'error' : item.severity === 'warning' ? 'warning' : 'info'"
            variant="tonal"
          >{{ item.severity }}</v-chip>
        </template>
        <template #item.fired_at="{ item }">
          <span class="text-caption">{{ formatTime(item.fired_at) }}</span>
        </template>
        <template #item.actions="{ item }">
          <v-btn size="x-small" variant="text" @click.stop="openEvidence(null, { item })">Evidence</v-btn>
        </template>
        <template #no-data>
          <div class="pa-4 text-center text-medium-emphasis">No signals match the current filters.</div>
        </template>
      </v-data-table>
    </v-card>

    <!-- Evidence drawer -->
    <v-navigation-drawer v-model="drawerOpen" location="right" width="480" temporary class="cc-drawer-right">
      <div v-if="evidenceLoading" class="pa-4 text-center">
        <v-progress-circular indeterminate />
      </div>
      <div v-else-if="evidence" class="pa-4 d-flex flex-column" style="height: 100%;">
        <div class="d-flex align-center ga-2 mb-3">
          <v-chip size="small" variant="tonal" :color="evidence.signal?.severity === 'emergency' ? 'error' : 'warning'">
            {{ (evidence.signal?.signal_type || '').replace(/_/g, ' ') }}
          </v-chip>
          <span class="text-caption">{{ formatTime(evidence.signal?.fired_at) }}</span>
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="drawerOpen = false" />
        </div>

        <!-- Narrative -->
        <v-alert type="info" variant="tonal" density="compact" class="mb-3 text-body-2">
          {{ evidence.narrative }}
        </v-alert>

        <!-- Segments list -->
        <div class="text-caption font-weight-medium mb-2">Presence segments in window</div>
        <div v-if="evidence.segments.length === 0" class="text-caption text-medium-emphasis mb-2">No segments in window.</div>
        <div v-for="seg in evidence.segments.slice(0, 20)" :key="seg.segment_id" class="d-flex align-center ga-2 py-1 text-caption">
          <v-chip size="x-small" :color="seg.is_inferred ? 'warning' : 'success'" variant="tonal">
            {{ seg.room_name || 'Room ' + seg.room_id }}
          </v-chip>
          <span class="text-medium-emphasis">{{ formatDuration(seg.dwell_seconds) }}</span>
        </div>
      </div>
    </v-navigation-drawer>

    <v-snackbar v-model="snack" :color="snackColor" timeout="4000">{{ snackText }}</v-snackbar>
  </div>
</template>

<script>
import { ref, computed } from "vue";
import { cts } from "@/services/cts.js";
import { useNotify } from "@/composables/useNotify.js";

const PALETTE = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7", "#DDA0DD", "#F7DC6F", "#BB8FCE", "#85C1E9"];

export default {
  name: "SignalExplorerView",

  setup() {
    const { snack, snackText, snackColor, notify } = useNotify();
    const signals = ref([]);
    const loading = ref(false);
    const error = ref("");
    const filters = ref({ kind: [], severity: [], timeRange: "7d" });
    const drawerOpen = ref(false);
    const evidence = ref(null);
    const evidenceLoading = ref(false);

    const headers = [
      { title: "Kind", key: "signal_type", width: 160 },
      { title: "Severity", key: "severity", width: 100 },
      { title: "Person", key: "person_id", width: 120 },
      { title: "Room", key: "room_name", width: 120 },
      { title: "Fired at", key: "fired_at", width: 140 },
      { title: "", key: "actions", width: 80 },
    ];

    const kindOptions = [
      "pacing", "bathroom_dwell_anomaly", "sundowning_index", "nighttime_movement",
      "stillness_anomaly", "absence", "inferred_dwell_exceeded", "presumed_location_unknown", "identity_disagreement",
    ].map((k) => ({ title: k.replace(/_/g, " "), value: k }));

    const timeRangeOptions = [
      { title: "Last 24h", value: "24h" },
      { title: "Last 7 days", value: "7d" },
      { title: "Last 30 days", value: "30d" },
    ];

    const chartWidth = 600;
    const barWidth = computed(() => Math.min(chartWidth / Math.max(Object.keys(aggregates.value.by_kind || {}).length, 1), 100));

    const aggregates = ref({ by_kind: {}, by_room: {} });

    const kindBars = computed(() => {
      const byKind = aggregates.value.by_kind || {};
      return Object.entries(byKind)
        .sort((a, b) => b[1] - a[1])
        .map(([kind, count], i) => ({
          kind,
          count,
          color: PALETTE[i % PALETTE.length],
          height: Math.max((count / Math.max(...Object.values(byKind), 1)) * 90, 4),
        }));
    });

    const topRooms = computed(() => {
      const entries = Object.entries(aggregates.value.by_room || {}).sort((a, b) => b[1] - a[1]).slice(0, 5);
      return Object.fromEntries(entries);
    });

    const maxRoomCount = computed(() => Math.max(...Object.values(aggregates.value.by_room || {}), 1));

    function formatTime(iso) {
      if (!iso) return "";
      return new Date(iso).toISOString().slice(0, 16).replace("T", " ");
    }

    function formatDuration(secs) {
      if (!secs || secs < 0) return "0m";
      const h = Math.floor(secs / 3600);
      const m = Math.floor((secs % 3600) / 60);
      return h > 0 ? `${h}h ${m}m` : `${m}m`;
    }

    async function loadSignals() {
      loading.value = true;
      error.value = "";
      try {
        const data = await cts.getSignalExplorer({
          kind: filters.value.kind || [],
          severity: filters.value.severity || [],
          limit: 200,
        });
        signals.value = data.rows || [];
        aggregates.value = data.aggregates || { by_kind: {}, by_room: {} };
      } catch (e) {
        error.value = e.message || "Failed to load signals";
        notify.error(error.value);
      } finally {
        loading.value = false;
      }
    }

    async function openEvidence(_row, col) {
      const item = col?.item || _row;
      if (!item?.id) return;
      drawerOpen.value = true;
      evidenceLoading.value = true;
      evidence.value = null;
      try {
        evidence.value = await cts.getSignalEvidence(item.id);
      } catch (e) {
        notify.error(e.message || "Failed to load evidence");
      } finally {
        evidenceLoading.value = false;
      }
    }

    function onTimeRange() { loadSignals(); }

    loadSignals();

    return {
      signals, loading, error, filters, headers, kindOptions, timeRangeOptions,
      drawerOpen, evidence, evidenceLoading, aggregates, kindBars, topRooms,
      maxRoomCount, chartWidth, barWidth, formatTime, formatDuration,
      fetch: loadSignals, openEvidence, onTimeRange,
      snack, snackText, snackColor,
    };
  },
};
</script>

<style scoped>
.cc-drawer-right { position: fixed !important; top: 0 !important; bottom: 0 !important; height: auto !important; }
.cc-drawer-right :deep(.v-navigation-drawer__content) { flex: 1 1 0; min-height: 0; padding-top: 64px; }
</style>
