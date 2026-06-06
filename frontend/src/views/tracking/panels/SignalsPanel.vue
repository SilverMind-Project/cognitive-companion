<template>
  <div>
    <TrackingPanelHeader
      title="Signals"
      description="Explore generated tracking signals, severity, provenance, and supporting evidence."
    >
      <template #actions>
        <v-btn variant="tonal" prepend-icon="mdi-refresh" size="small" :loading="loading" @click="loadSignals">
          Refresh
        </v-btn>
      </template>
    </TrackingPanelHeader>

    <v-alert v-if="error" type="error" variant="tonal" density="compact" class="mb-4" closable @click:close="error = ''">
      {{ error }}
    </v-alert>

    <!-- Filter bar -->
    <v-card variant="tonal" class="pa-2 mb-4">
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
            @update:model-value="loadSignals"
          />
        </v-col>
        <v-col cols="6" sm="3" md="2">
          <v-select
            v-model="filters.severity"
            :items="['info', 'warning', 'emergency']"
            label="Severity"
            variant="outlined"
            density="compact"
            multiple
            clearable
            hide-details
            @update:model-value="loadSignals"
          />
        </v-col>
      </v-row>
    </v-card>

    <!-- Signal counts by kind: CcBarChart (D2: replaces hand-rolled SVG bar chart) -->
    <v-row class="mb-4">
      <v-col cols="12" md="8">
        <CcSectionCard title="Signal counts by kind">
          <CcBarChart
            :categories="kindBars.map((b) => b.kind.replace(/_/g, ' '))"
            :series="[{ name: 'Count', data: kindBars.map((b) => b.count) }]"
            :loading="loading"
            height="200"
            @select="onKindSelect"
          />
        </CcSectionCard>
      </v-col>
      <v-col cols="12" md="4">
        <CcSectionCard title="Top rooms">
          <div v-for="(count, room) in topRooms" :key="room" class="d-flex align-center ga-2 mb-1">
            <span class="text-caption" style="min-width: 80px">{{ room }}</span>
            <v-progress-linear :model-value="(count / maxRoomCount) * 100" height="6" rounded color="primary" />
            <span class="text-caption text-medium-emphasis">{{ count }}</span>
          </div>
          <div v-if="Object.keys(topRooms).length === 0 && !loading" class="text-caption text-medium-emphasis">
            No room data.
          </div>
        </CcSectionCard>
      </v-col>
    </v-row>

    <!-- Signal table with provenance -->
    <v-card class="glass-card">
      <v-data-table
        :headers="headers"
        :items="signals"
        :loading="loading"
        item-value="id"
        items-per-page-text="Signals per page"
        hover
        @click:row="openEvidence"
      >
        <template #item.signal_type="{ item }">
          <v-chip size="x-small" variant="tonal">{{ (item.signal_type || "").replace(/_/g, " ") }}</v-chip>
        </template>
        <template #item.severity="{ item }">
          <v-chip
            size="x-small"
            :color="item.severity === 'emergency' ? 'error' : item.severity === 'warning' ? 'warning' : 'info'"
            variant="tonal"
          >{{ item.severity }}</v-chip>
        </template>
        <template #item.source="{ item }">
          <CcProvenanceBadge
            :source="item.source || 'observation'"
            :quality="item.quality ?? null"
          />
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
      <div class="h-100 d-flex flex-column">
        <div class="d-flex align-center px-4 py-3">
          <span class="text-subtitle-1 font-weight-semibold">Evidence</span>
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="drawerOpen = false" />
        </div>
        <v-divider />
        <div class="flex-grow-1 overflow-y-auto" style="min-height: 0">
          <v-card-text>
            <div v-if="evidenceLoading" class="text-center py-4">
              <v-progress-circular indeterminate />
            </div>
            <template v-else-if="evidence">
              <div class="d-flex align-center ga-2 mb-3">
                <v-chip
                  size="small"
                  variant="tonal"
                  :color="evidence.signal?.severity === 'emergency' ? 'error' : 'warning'"
                >
                  {{ (evidence.signal?.signal_type || "").replace(/_/g, " ") }}
                </v-chip>
                <span class="text-caption">{{ formatTime(evidence.signal?.fired_at) }}</span>
              </div>
              <v-alert type="info" variant="tonal" density="compact" class="mb-3 text-body-2">
                {{ evidence.narrative }}
              </v-alert>
              <div class="text-caption font-weight-medium mb-2">Presence segments in window</div>
              <div
                v-for="seg in (evidence.segments || []).slice(0, 20)"
                :key="seg.segment_id"
                class="d-flex align-center ga-2 py-1 text-caption"
              >
                <v-chip
                  size="x-small"
                  :color="seg.is_inferred ? 'warning' : 'success'"
                  variant="tonal"
                >{{ seg.room_name || "Room " + seg.room_id }}</v-chip>
                <span class="text-medium-emphasis">{{ formatDuration(seg.dwell_seconds) }}</span>
              </div>
            </template>
          </v-card-text>
        </div>
      </div>
    </v-navigation-drawer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { cts } from "@/services/cts.js";
import { useNotify } from "@/composables/useNotify.js";
import { formatDateTimeShort } from "@/services/timezone.js";
import CcBarChart from "@/components/charts/CcBarChart.vue";
import CcSectionCard from "@/components/dashboard/CcSectionCard.vue";
import CcProvenanceBadge from "@/components/dashboard/CcProvenanceBadge.vue";
import TrackingPanelHeader from "@/components/tracking/TrackingPanelHeader.vue";

const { notify } = useNotify();

const signals = ref([]);
const loading = ref(false);
const error = ref("");
const filters = ref({ kind: [], severity: [] });
const drawerOpen = ref(false);
const evidence = ref(null);
const evidenceLoading = ref(false);
const aggregates = ref({ by_kind: {}, by_room: {} });

const headers = [
  { title: "Kind",      key: "signal_type", width: 160 },
  { title: "Severity",  key: "severity",    width: 100 },
  { title: "Person",    key: "person_id",   width: 120 },
  { title: "Room",      key: "room_name",   width: 120 },
  { title: "Source",    key: "source",      width: 140 },
  { title: "Fired at",  key: "fired_at",    width: 140 },
  { title: "",          key: "actions",     width: 80  },
];

const kindOptions = [
  "pacing", "bathroom_dwell_anomaly", "sundowning_index", "nighttime_movement",
  "stillness_anomaly", "absence", "inferred_dwell_exceeded", "presumed_location_unknown", "identity_disagreement",
].map((k) => ({ title: k.replace(/_/g, " "), value: k }));

const kindBars = computed(() => {
  const byKind = aggregates.value.by_kind || {};
  return Object.entries(byKind)
    .sort((a, b) => b[1] - a[1])
    .map(([kind, count]) => ({ kind, count: typeof count === "number" ? count : count.count ?? 0 }));
});

const topRooms = computed(() => {
  const entries = Object.entries(aggregates.value.by_room || {}).sort((a, b) => b[1] - a[1]).slice(0, 5);
  return Object.fromEntries(entries);
});

const maxRoomCount = computed(() => Math.max(...Object.values(aggregates.value.by_room || {}), 1));

function formatTime(iso) {
  return formatDateTimeShort(iso || "");
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

function onKindSelect(category) {
  const normalized = category.replace(/ /g, "_");
  if (!filters.value.kind.includes(normalized)) {
    filters.value.kind = [...filters.value.kind, normalized];
    loadSignals();
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

onMounted(loadSignals);
</script>
