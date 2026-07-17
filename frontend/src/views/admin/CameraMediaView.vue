<template>
  <div>
    <div class="mb-6">
      <div class="d-flex align-center flex-wrap ga-3">
        <div>
          <h2 class="text-h4 font-weight-bold tracking-tight">Camera Media</h2>
          <div class="text-body-2 text-medium-emphasis mt-1">
            Live buffer depth, image eligibility, and retained media across both camera pathways.
          </div>
        </div>
        <v-spacer />
        <v-switch
          v-model="aggregators.state.autoRefresh"
          label="Auto-refresh"
          density="compact"
          hide-details
        />
        <v-chip
          v-if="aggregators.state.autoRefresh"
          size="small"
          color="primary"
          variant="tonal"
          prepend-icon="mdi-timer-outline"
        >
          {{ AGGREGATOR_REFRESH_SECONDS }}s
        </v-chip>
        <v-btn
          variant="tonal"
          prepend-icon="mdi-refresh"
          :loading="aggregators.state.loading"
          @click="aggregators.actions.fetch"
        >
          Refresh
        </v-btn>
      </div>

      <div class="d-flex align-center flex-wrap ga-3 mt-4">
        <CcSegmentedToggle
          :model-value="aggregators.state.filters.origin"
          :options="originOptions"
          @update:model-value="setOrigin"
        />
        <v-text-field
          :model-value="aggregators.state.filters.query"
          placeholder="Search cameras"
          aria-label="Search cameras"
          prepend-inner-icon="mdi-magnify"
          variant="outlined"
          density="compact"
          clearable
          hide-details
          class="filter-control"
          @update:model-value="setQuery"
        />
        <v-select
          :model-value="aggregators.state.filters.roomName"
          :items="aggregators.state.roomNames"
          placeholder="All rooms"
          aria-label="Filter by room"
          prepend-inner-icon="mdi-floor-plan"
          variant="outlined"
          density="compact"
          clearable
          hide-details
          class="filter-control"
          @update:model-value="setRoom"
        />
      </div>
    </div>

    <v-alert
      v-if="aggregators.state.error"
      type="error"
      variant="tonal"
      density="compact"
      class="mb-4"
    >
      {{ aggregators.state.error }}
    </v-alert>

    <v-row class="mb-4">
      <v-col cols="12" sm="6" lg="3">
        <CcMetricTile label="Cameras" :value="aggregators.state.total" />
      </v-col>
      <v-col cols="12" sm="6" lg="3">
        <CcMetricTile label="Buffered frames" :value="kpis.buffered" />
      </v-col>
      <v-col cols="12" sm="6" lg="3">
        <CcMetricTile label="Image-eligible" :value="kpis.eligible" />
      </v-col>
      <v-col cols="12" sm="6" lg="3">
        <CcMetricTile label="Dropped" :value="kpis.dropped" />
      </v-col>
    </v-row>

    <v-card class="glass-card mb-6">
      <v-card-title class="d-flex align-center">
        <div>
          <div class="text-subtitle-1 font-weight-bold">Buffer pressure</div>
          <div class="text-caption text-medium-emphasis">
            Bar color moves from healthy to constrained as the image drop ratio rises.
          </div>
        </div>
      </v-card-title>
      <v-card-text>
        <CcQueueDepthChart
          :cameras="chartCameras"
          :theme="chartTheme"
          :loading="aggregators.state.loading"
          @select="openCameraById"
        />
      </v-card-text>
    </v-card>

    <v-card class="glass-card">
      <v-data-table-server
        :headers="headers"
        :items="aggregators.state.items"
        :items-length="aggregators.state.total"
        :items-per-page="aggregators.state.itemsPerPage"
        :page="aggregators.state.page"
        :loading="aggregators.state.loading"
        item-value="camera_id"
        hover
        @click:row="openCameraFromRow"
        @update:options="aggregators.actions.onPageOptions"
      >
        <template #item.camera="{ item }">
          <div class="py-2">
            <div class="d-flex align-center ga-2">
              <span class="font-weight-medium">{{ cameraName(item) }}</span>
              <v-chip size="x-small" variant="tonal" :color="originColor(item.origin)">
                {{ originLabel(item.origin) }}
              </v-chip>
            </div>
            <div class="text-caption text-medium-emphasis cc-code mt-1">
              {{ shortCameraId(item.camera_id) }}
            </div>
          </div>
        </template>
        <template #item.room_name="{ item }">
          {{ item.room_name || "Unassigned" }}
        </template>
        <template #item.buffer_depth="{ item }">
          <span class="font-weight-medium">{{ item.buffer_depth }}</span>
          <span class="text-medium-emphasis">
            / {{ item.buffer_capacity == null ? "unbounded" : item.buffer_capacity }}
          </span>
        </template>
        <template #item.pending_flush="{ item }">
          {{ item.pending_flush == null ? "n/a" : item.pending_flush }}
        </template>
        <template #item.cooldown_remaining_seconds="{ item }">
          {{ formatSeconds(item.cooldown_remaining_seconds) }}
        </template>
        <template #item.rate_per_second="{ item }">
          {{ formatRate(item.rate_per_second) }}
        </template>
        <template #item.last_event_at="{ item }">
          {{ item.last_event_at ? formatDateTimeShort(item.last_event_at) : "No events" }}
        </template>
        <template #no-data>
          <div class="pa-8 text-center">
            <v-icon size="40" color="medium-emphasis" class="mb-2">
              mdi-camera-off-outline
            </v-icon>
            <div class="text-body-1 text-medium-emphasis">
              No cameras match these filters.
            </div>
          </div>
        </template>
      </v-data-table-server>
    </v-card>

    <v-navigation-drawer
      v-model="drawerOpen"
      location="right"
      width="640"
      temporary
      class="cc-drawer-right"
    >
      <CameraMediaDrawer
        v-if="selectedCamera"
        :camera="selectedCamera"
        :history="selectedCameraHistory"
        @close="drawerOpen = false"
      />
    </v-navigation-drawer>

  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import CcQueueDepthChart from "@/components/charts/CcQueueDepthChart.vue";
import CcSegmentedToggle from "@/components/common/CcSegmentedToggle.vue";
import CcMetricTile from "@/components/dashboard/CcMetricTile.vue";
import CameraMediaDrawer from "@/components/media/CameraMediaDrawer.vue";
import {
  AGGREGATOR_REFRESH_SECONDS,
  useAggregatorState,
} from "@/composables/useAggregatorState.js";
import { useChartTheme } from "@/composables/useChartTheme.js";
import { useNotify } from "@/composables/useNotify.js";
import { formatDateTimeShort } from "@/services/timezone.js";

const aggregators = useAggregatorState();
const { chartTheme } = useChartTheme();
const { notify } = useNotify();

const drawerOpen = ref(false);
const selectedCameraId = ref(null);

const originOptions = [
  { value: null, label: "All" },
  { value: "recamera", label: "reCamera" },
  { value: "cts", label: "CTS" },
];

const headers = [
  { title: "Camera", key: "camera", sortable: false },
  { title: "Room", key: "room_name", sortable: false },
  { title: "Buffer depth", key: "buffer_depth", sortable: false },
  { title: "Pending flush", key: "pending_flush", sortable: false },
  { title: "Cooldown", key: "cooldown_remaining_seconds", sortable: false },
  { title: "Rate/sec", key: "rate_per_second", sortable: false },
  { title: "Eligible", key: "images_eligible_total", sortable: false },
  { title: "Dropped", key: "images_dropped_total", sortable: false },
  { title: "Last event", key: "last_event_at", sortable: false },
];

const kpis = computed(() => aggregators.state.items.reduce(
  (totals, item) => ({
    buffered: totals.buffered + item.buffer_depth,
    eligible: totals.eligible + item.images_eligible_total,
    dropped: totals.dropped + item.images_dropped_total,
  }),
  { buffered: 0, eligible: 0, dropped: 0 }
));

const chartCameras = computed(() => aggregators.state.items.map((item) => ({
  ...item,
  label: `${originLabel(item.origin)} - ${cameraName(item)}`,
})));

const selectedCamera = computed(() =>
  aggregators.state.items.find((item) => item.camera_id === selectedCameraId.value) ?? null
);

const selectedCameraHistory = computed(
  () => aggregators.state.history.get(selectedCameraId.value) ?? []
);

function setOrigin(value) {
  return aggregators.actions.setFilter("origin", value);
}

function setQuery(value) {
  return aggregators.actions.setFilter("query", value || "");
}

function setRoom(value) {
  return aggregators.actions.setFilter("roomName", value);
}

function cameraName(camera) {
  return camera.display_name || camera.camera_id;
}

function shortCameraId(cameraId) {
  return cameraId.length > 18 ? `${cameraId.slice(0, 15)}...` : cameraId;
}

function originLabel(origin) {
  return origin === "recamera" ? "reCamera" : "CTS";
}

function originColor(origin) {
  return origin === "recamera" ? "primary" : "info";
}

function formatSeconds(value) {
  return value == null ? "n/a" : `${Number(value).toFixed(1)}s`;
}

function formatRate(value) {
  return value == null ? "n/a" : `${Number(value).toFixed(2)}/s`;
}

function openCameraFromRow(_event, { item }) {
  openCamera(item);
}

function openCameraById(cameraId) {
  const camera = aggregators.state.items.find((item) => item.camera_id === cameraId);
  if (camera) openCamera(camera);
}

function openCamera(camera) {
  selectedCameraId.value = camera.camera_id;
  drawerOpen.value = true;
}

watch(
  () => aggregators.state.error,
  (error) => {
    if (error) notify.error(error);
  }
);

watch(
  () => aggregators.state.items,
  (items) => {
    if (selectedCameraId.value && !items.some((item) => item.camera_id === selectedCameraId.value)) {
      drawerOpen.value = false;
      selectedCameraId.value = null;
    }
  }
);

onMounted(aggregators.actions.fetch);

defineExpose({
  aggregators,
  drawerOpen,
  selectedCamera,
  openCamera,
  setOrigin,
});
</script>

<style scoped>
.filter-control {
  max-width: 240px;
}

</style>
