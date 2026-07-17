<template>
  <div>
    <FloorPlanModeNav v-model="mode" :embedded="embedded" />

    <FloorPlanUploadPanel
      v-if="mode === 'upload'"
      :floor-plan-url="floorPlanUrl"
      :fp-width="fpWidth"
      :fp-height="fpHeight"
      :fp-mpp="fpMpp"
      @saved="applyUploadedFloorPlan"
    />

    <EditRoomsPanel
      v-else-if="mode === 'edit'"
      v-model:edit-polygon="editPolygon"
      :rooms="rooms"
      :floor-plan-url="floorPlanUrl"
      :editing-room="editingRoom"
      :saving-room="savingRoom"
      @select-room="selectRoom"
      @save-polygon="saveRoomPolygon"
    />

    <CoverageCameraMap
      v-else-if="mode === 'coverage'"
      :loading="coverageLoading"
      :floor-plan-url="floorPlanUrl"
      :img-ready="coverageImgReady"
      :img-w="coverageImgW"
      :img-h="coverageImgH"
      :cameras="coverageCameras"
      :uncalibrated="uncalibratedCoverage"
      :marauders-enabled="maraudersState.enabled"
      :to-svg-points="toCoverageSvgPoints"
      :centroid="coverageCentroid"
      :tok-brand="tokBrand"
      :tok-brand-soft="tokBrandSoft"
      :tok-text3="tokText3"
      @refresh="loadCoverage"
      @img-load="onCoverageImgLoad"
      @go-upload="mode = 'upload'"
    />

    <v-card v-else-if="mode === 'doors'" class="glass-card">
      <v-card-title class="floor-plan-card-title d-flex align-center"> Door Zones </v-card-title>
      <v-divider />
      <v-card-text>
        <DoorZoneEditor
          :rooms="rooms"
          :zones="doorZones"
          :loading="doorZonesLoading"
          :floor-plan-url="floorPlanUrl"
          :canvas-w="canvasW"
          :canvas-h="canvasH"
          :fp-mpp="fpMpp"
          @saved="loadDoorZones"
          @deleted="loadDoorZones"
          @set-scale="mode = 'upload'"
        />
      </v-card-text>
    </v-card>

    <HeatmapModePanel
      v-else-if="mode === 'heatmap'"
      v-model:heatmap-person-id="heatmapPersonId"
      v-model:heatmap-date-preset="heatmapDatePreset"
      v-model:heatmap-start-date="heatmapStartDate"
      v-model:heatmap-end-date="heatmapEndDate"
      v-model:heatmap-time-preset="heatmapTimePreset"
      v-model:heatmap-start-time="heatmapStartTime"
      v-model:heatmap-end-time="heatmapEndTime"
      :floor-plan-url="floorPlanUrl"
      :canvas-w="canvasW"
      :canvas-h="canvasH"
      :rooms="rooms"
      :marauders-enabled="maraudersState.enabled"
      :heatmap-zoom="heatmapZoom"
      :mapped-heatmap-bins="mappedHeatmapBins"
      :heatmap-state="heatmapState"
      :heatmap-persons="heatmapPersons"
      :date-presets="DATE_PRESETS"
      :time-presets="TIME_PRESETS"
      :app-tz-label="appTzLabel"
      :heatmap-time-window-label="heatmapTimeWindowLabel"
      :heatmap-range-ready="heatmapRangeReady"
      :heatmap-time-ready="heatmapTimeReady"
      @canvas-mousedown="onHeatmapMouseDown"
      @generate="runHeatmap"
    />

    <v-row v-else class="floor-plan-layout">
      <v-col cols="12" md="9" class="floor-plan-main">
        <LiveFloorCanvas
          :floor-plan-url="floorPlanUrl"
          :canvas-w="canvasW"
          :canvas-h="canvasH"
          :fp-width="fpWidth"
          :fp-height="fpHeight"
          :fp-mpp="fpMpp"
          :rooms="rooms"
          :marauders-state="maraudersState"
          :live-zoom="liveZoom"
          :smoothed-markers="smoothedMarkers"
          :ph-count="worldPhMarkers.length"
          :trail-buffers="trailBuffers"
          :footprint-now="footprintNow"
          :uncalibrated-ph-count="uncalibratedPhCount"
          :world-status-color="worldStatusColor"
          :world-status-icon="worldStatusIcon"
          :world-status-label="worldStatusLabel"
          @ph-click="onPhClick"
          @canvas-mousedown="onLiveZoomMouseDown"
          @go-calibration="router.push({ name: 'cts-calibration' })"
        />
      </v-col>

      <v-col cols="12" md="3" class="floor-plan-sidebar">
        <LiveSidebar
          :active-persons="activePersons"
          :world-inferred-rooms="worldInferredRooms"
          :world-status-color="worldStatusColor"
          :world-status-icon="worldStatusIcon"
          :world-status-label="worldStatusLabel"
          :world-last-update="worldLastUpdate"
          :world-ph-count="worldPhs.length"
          :world-ph-marker-count="worldPhMarkers.length"
          :uncalibrated-ph-count="uncalibratedPhCount"
          :world-ws-status-label="worldWsStatusLabel"
        />
      </v-col>
    </v-row>
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, ref, computed } from "vue";
import { useRouter } from "vue-router";
import { ccToken } from "@/composables/useChartTheme.js";
import { useNotify } from "@/composables/useNotify";
import { useMaraudersMode } from "@/composables/useMaraudersMode.js";
import { useFloorPlanCanvas } from "@/composables/useFloorPlanCanvas.js";
import { useFloorPlanRooms } from "@/composables/useFloorPlanRooms.js";
import { useRoomPolygonEditor } from "@/composables/useRoomPolygonEditor.js";
import { useFloorPlanCoverage } from "@/composables/useFloorPlanCoverage.js";
import { useFloorPlanDoorZones } from "@/composables/useFloorPlanDoorZones.js";
import { useFloorPlanHeatmap } from "@/composables/useFloorPlanHeatmap.js";
import { useLiveWorldMarkers } from "@/composables/useLiveWorldMarkers.js";
import FloorPlanModeNav from "@/components/cts/floor/FloorPlanModeNav.vue";
import FloorPlanUploadPanel from "@/components/cts/floor/FloorPlanUploadPanel.vue";
import EditRoomsPanel from "@/components/cts/floor/EditRoomsPanel.vue";
import CoverageCameraMap from "@/components/cts/floor/CoverageCameraMap.vue";
import HeatmapModePanel from "@/components/cts/floor/HeatmapModePanel.vue";
import LiveFloorCanvas from "@/components/cts/floor/LiveFloorCanvas.vue";
import LiveSidebar from "@/components/cts/floor/LiveSidebar.vue";
import DoorZoneEditor from "@/components/cts/DoorZoneEditor.vue";
import "@/styles/floor-plan-shared.css";

defineProps({
  embedded: { type: Boolean, default: false },
});

const { notify } = useNotify();
const { state: maraudersState } = useMaraudersMode();
const router = useRouter();

// ── Design-token colors for bespoke spatial renderers (D3) ────────────────
const tokBrand = computed(() => ccToken("--cc-brand"));
const tokBrandSoft = computed(() => ccToken("--cc-brand-soft"));
const tokText3 = computed(() => ccToken("--cc-text-3"));

// ── Mode ──────────────────────────────────────────────────────────────────
const mode = ref("live");

// ── Shared floor-plan/rooms state ──────────────────────────────────────────
const { floorPlanUrl, fpWidth, fpHeight, fpMpp, canvasW, canvasH, loadFloorPlan, applyUploadedFloorPlan } =
  useFloorPlanCanvas();
const { rooms, loadRooms, replaceRoom } = useFloorPlanRooms(notify);
const { editingRoom, editPolygon, savingRoom, selectRoom, saveRoomPolygon } = useRoomPolygonEditor(
  notify,
  replaceRoom,
);

// ── Per-mode composables (kept in the orchestrator; see each file's header
//    comment for why -- coverage/door-zones/heatmap all lazy-load on the
//    first watch(mode) transition into that mode, which a v-if-gated panel
//    component would never see) ────────────────────────────────────────────
const {
  coverageLoading,
  coverageCameras,
  coverageImgReady,
  coverageImgW,
  coverageImgH,
  uncalibratedCoverage,
  onCoverageImgLoad,
  loadCoverage,
  toCoverageSvgPoints,
  coverageCentroid,
} = useFloorPlanCoverage(mode, notify);

const { doorZones, doorZonesLoading, loadDoorZones } = useFloorPlanDoorZones(mode, notify);

const {
  heatmapZoom,
  heatmapPersonId,
  heatmapPersons,
  heatmapState,
  appTzLabel,
  DATE_PRESETS,
  heatmapDatePreset,
  heatmapStartDate,
  heatmapEndDate,
  TIME_PRESETS,
  heatmapTimePreset,
  heatmapStartTime,
  heatmapEndTime,
  heatmapRangeReady,
  heatmapTimeReady,
  heatmapTimeWindowLabel,
  mappedHeatmapBins,
  runHeatmap,
  onHeatmapMouseDown,
} = useFloorPlanHeatmap(mode, fpWidth, fpHeight, fpMpp, canvasW, canvasH);

const {
  liveZoom,
  worldPhs,
  worldInferredRooms,
  worldLastUpdate,
  worldWsStatusLabel,
  trailBuffers,
  worldPhMarkers,
  uncalibratedPhCount,
  smoothedMarkers,
  footprintNow,
  activePersons,
  worldStatusLabel,
  worldStatusColor,
  worldStatusIcon,
  onLiveZoomMouseDown,
  onPhClick,
  dispose: disposeLiveMarkers,
} = useLiveWorldMarkers(fpWidth, fpHeight, fpMpp, canvasW, canvasH, rooms, router, maraudersState);

onMounted(() => {
  loadFloorPlan();
  loadRooms();
  // WS lifecycle is handled inside useWorldSnapshot (via useLiveWorldMarkers).
});

onBeforeUnmount(() => {
  disposeLiveMarkers();
});
</script>
