<template>
  <div>
    <!-- Header -->
    <div class="d-flex align-center mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Homography Calibration</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Teach the system where each camera sees on the floor plan.
        </div>
      </div>
      <v-spacer />
      <v-select
        v-model="selectedCameraId"
        :items="cameras"
        item-title="name"
        item-value="id"
        label="Camera"
        variant="outlined"
        density="compact"
        hide-details
        style="max-width: 260px"
        @update:model-value="onCameraChange"
      />
    </div>

    <PrerequisitesBanner
      :floor-plan-ready="floorPlanReady"
      :scale-ready="scaleReady"
      :fp-mpp="fpMpp"
      :selected-camera-id="selectedCameraId"
      :existing-calibration="existingCalibration"
    />

    <!-- No camera selected -->
    <v-alert v-if="!selectedCameraId" type="info" variant="tonal" class="mt-2">
      Select a camera from the dropdown to begin calibration.
    </v-alert>

    <!-- Drift detected banner -->
    <v-alert
      v-if="selectedCamera && selectedCamera.needs_recalibration"
      type="warning"
      variant="tonal"
      class="mb-4"
      icon="mdi-camera-off"
    >
      <div class="d-flex align-center justify-space-between flex-wrap ga-2">
        <div>
          <strong>Camera drift detected.</strong>
          This camera has likely been moved or bumped since its last calibration.
          <span v-if="selectedCamera.drift_reason" class="text-caption ml-1 text-medium-emphasis">
            ({{ selectedCamera.drift_reason }})
          </span>
          Localization for this camera is unreliable until it is recalibrated.
        </div>
        <v-btn
          color="warning"
          variant="tonal"
          prepend-icon="mdi-auto-fix"
          size="small"
          :loading="autoCalibrating"
          @click="runAutoCalibrate"
        >
          Re-run Auto-Calibration
        </v-btn>
      </div>
    </v-alert>

    <!-- Main calibration area -->
    <template v-if="selectedCameraId">
      <!-- Mode toggle when floor plan is available -->
      <div class="d-flex align-center mb-4 ga-3 flex-wrap">
        <CcSegmentedToggle
          v-if="floorPlanReady && scaleReady"
          v-model="inputMode"
          :options="INPUT_MODE_OPTIONS"
          size="default"
        />

        <v-spacer />

        <!-- Auto-calibrate button -->
        <v-btn
          color="secondary"
          variant="tonal"
          prepend-icon="mdi-auto-fix"
          :loading="autoCalibrating"
          size="small"
          @click="runAutoCalibrate"
        >
          Auto-calibrate
        </v-btn>

        <!-- Seed Floor Region button -->
        <v-btn
          v-if="existingCalibration"
          color="secondary"
          variant="tonal"
          prepend-icon="mdi-shape-polygon-plus"
          size="small"
          @click="loadDefaultFloorRegion"
        >
          Seed Floor Region
        </v-btn>

        <span v-if="floorPlanReady && scaleReady" class="text-caption text-medium-emphasis">
          {{
            inputMode === "pick"
              ? "Click a point on the camera image, then click the same spot on the floor plan."
              : "Click the camera image, then type the floor coordinates manually."
          }}
        </span>
      </div>

      <v-row>
        <!-- Left: camera snapshot -->
        <v-col cols="12" :md="pickModeActive ? 6 : 7">
          <CameraCalibrationPane
            ref="cameraPaneRef"
            v-model:points="points"
            v-model:pending-pixel="pendingPixel"
            v-model:floor-region-draft="floorRegionDraft"
            v-model:floor-region-drag-idx="floorRegionDragIdx"
            v-model:img-content-rect="imgContentRect"
            :snapshot-url="snapshotUrl"
            :snapshot-loading="snapshotLoading"
            :auto-suggested-points="autoSuggestedPoints"
            :input-mode="inputMode"
            :floor-plan-ready="floorPlanReady"
            :scale-ready="scaleReady"
            :point-color="pointColor"
            :point-in-quadrant="pointInQuadrant"
            :display-src="displaySrc"
            :nearest-auto-suggestion="nearestAutoSuggestion"
            :consume-auto-suggestion="consumeAutoSuggestion"
            @refresh="loadSnapshot"
          />
        </v-col>

        <!-- Right: floor plan picker OR manual entry -->
        <v-col cols="12" :md="pickModeActive ? 6 : 5">
          <FloorPlanPickerPane
            v-if="pickModeActive"
            ref="floorPlanPaneRef"
            v-model:points="points"
            v-model:pending-pixel="pendingPixel"
            v-model:fp-img-rect="fpImgRect"
            :floor-plan-url="floorPlanUrl"
            :fp-width="fpWidth"
            :fp-height="fpHeight"
            :fp-mpp="fpMpp"
            :preview-coverage-polygon="previewCoveragePolygon"
            :preview-status="previewStatus"
            :point-color="pointColor"
            :consume-auto-suggestion="consumeAutoSuggestion"
          />
          <CoordinateSystemExplainer v-else />

          <PointCorrespondencesList
            v-model:points="points"
            :pick-mode-active="pickModeActive"
            :calibrating="calibrating"
            @remove="removePoint"
            @clear="clearPoints"
            @calibrate="runCalibration"
          />

          <CalibrationResultCard v-if="result" :result="result" />
          <v-card v-else-if="existingCalibration && !autoResult">
            <v-card-text class="d-flex align-center">
              <v-icon color="success" class="mr-2">mdi-check-circle</v-icon>
              <span class="text-body-2">
                This camera is already calibrated. Run again to update.
              </span>
            </v-card-text>
          </v-card>

          <FloorRegionCard
            v-if="floorRegionDraft"
            :floor-region-draft="floorRegionDraft"
            :saving="floorRegionSaving"
            @discard="discardFloorRegion"
            @save="saveFloorRegion('manual')"
          />

          <AutoCalibrateResultCard
            v-if="autoResult"
            :auto-result="autoResult"
            @dismiss="dismissAutoResult"
            @refine="populateFromAutoResult"
          />
        </v-col>
      </v-row>

      <CalibrationTipsPanel />
    </template>

    <!-- Calibration Health Panel -->
    <v-card class="glass-card mt-6" :border="true">
      <v-card-title class="d-flex align-center">
        <v-icon start icon="mdi-heart-pulse" class="mr-2" />
        Calibration Health
      </v-card-title>
      <v-card-text>
        <CalibrationHealthPanel @test-projection="onTestProjection" />
      </v-card-text>
    </v-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from "vue";
import { useNotify } from "@/composables/useNotify.js";
import { useBlurMode, useDisplaySrc } from "@/composables/useBlurMode.js";
import { useCalibrationCamera } from "@/composables/useCalibrationCamera.js";
import { useFloorPlan } from "@/composables/useFloorPlan.js";
import { useCalibrationPoints } from "@/composables/useCalibrationPoints.js";
import { useAutoCalibration } from "@/composables/useAutoCalibration.js";
import { useFloorRegion } from "@/composables/useFloorRegion.js";
import { useCalibrationPreview } from "@/composables/useCalibrationPreview.js";
import CalibrationHealthPanel from "@/components/cts/CalibrationHealthPanel.vue";
import CcSegmentedToggle from "@/components/common/CcSegmentedToggle.vue";
import PrerequisitesBanner from "@/components/cts/calibration/PrerequisitesBanner.vue";
import CameraCalibrationPane from "@/components/cts/calibration/CameraCalibrationPane.vue";
import FloorPlanPickerPane from "@/components/cts/calibration/FloorPlanPickerPane.vue";
import CoordinateSystemExplainer from "@/components/cts/calibration/CoordinateSystemExplainer.vue";
import PointCorrespondencesList from "@/components/cts/calibration/PointCorrespondencesList.vue";
import CalibrationResultCard from "@/components/cts/calibration/CalibrationResultCard.vue";
import FloorRegionCard from "@/components/cts/calibration/FloorRegionCard.vue";
import AutoCalibrateResultCard from "@/components/cts/calibration/AutoCalibrateResultCard.vue";
import CalibrationTipsPanel from "@/components/cts/calibration/CalibrationTipsPanel.vue";

const { notify } = useNotify();
const { blurMode } = useBlurMode();
const { displaySrc } = useDisplaySrc(blurMode);

const {
  cameras,
  selectedCameraId,
  selectedCamera,
  snapshotUrl,
  snapshotLoading,
  existingCalibration,
  loadCameras,
  loadSnapshot,
  loadExistingCalibration,
} = useCalibrationCamera(notify);

const { floorPlanUrl, fpWidth, fpHeight, fpMpp, floorPlanReady, scaleReady, loadFloorPlan } =
  useFloorPlan();

// ── Cross-pane state (both camera + floor-plan panes read/write these) ────
const imgContentRect = ref(null);
const fpImgRect = ref(null);
const result = ref(null);

// ── Click-to-pick state ───────────────────────────────────────────────────
// pendingPixel: camera click waiting for a matching floor plan click
const pendingPixel = ref(null);
const inputMode = ref("pick");
const INPUT_MODE_OPTIONS = [
  { value: "pick", label: "Click-to-Pick", icon: "mdi-cursor-pointer" },
  { value: "manual", label: "Manual Entry", icon: "mdi-pencil" },
];
const pickModeActive = computed(
  () => inputMode.value === "pick" && floorPlanReady.value && scaleReady.value,
);

const {
  floorRegionDraft,
  floorRegionDragIdx,
  floorRegionSaving,
  saveFloorRegion,
  discardFloorRegion,
  loadDefaultFloorRegion,
} = useFloorRegion(notify, selectedCameraId);

const {
  latestMinioKey,
  autoCalibrating,
  autoResult,
  autoSuggestedPoints,
  nearestAutoSuggestion,
  consumeAutoSuggestion,
  runAutoCalibrate,
  populateFromAutoResult,
  dismissAutoResult,
} = useAutoCalibration(
  notify,
  selectedCameraId,
  imgContentRect,
  inputMode,
  pendingPixel,
  floorRegionDraft,
  result,
);

const { points, calibrating, pointInQuadrant, removePoint, clearPoints, runCalibration } =
  useCalibrationPoints(
    notify,
    selectedCameraId,
    imgContentRect,
    pendingPixel,
    autoSuggestedPoints,
    existingCalibration,
    result,
  );

const { previewStatus, previewCoveragePolygon, pointColor, disposePreviewTimer } =
  useCalibrationPreview(points, imgContentRect, fpImgRect, fpWidth, fpHeight, fpMpp, result);

const cameraPaneRef = ref(null);
const floorPlanPaneRef = ref(null);

async function onCameraChange() {
  points.value = [];
  result.value = null;
  autoResult.value = null;
  autoSuggestedPoints.value = [];
  pendingPixel.value = null;
  snapshotUrl.value = null;
  imgContentRect.value = null;
  existingCalibration.value = false;
  latestMinioKey.value = null;
  floorRegionDraft.value = null;
  await Promise.all([loadSnapshot(), loadExistingCalibration()]);
}

// M2: handle test-projection from CalibrationHealthPanel
async function onTestProjection(cameraId) {
  selectedCameraId.value = cameraId;
  // Bypasses the v-select's @update:model-value, so drive the same reset+reload
  // onCameraChange does -- otherwise the dropdown shows the new camera while the
  // snapshot/calibration panes keep showing the previously selected one.
  await onCameraChange();
  // Scroll to the calibration area for visual inspection.
  window.scrollTo({ top: 0, behavior: "smooth" });
}

onMounted(() => {
  loadCameras();
  loadFloorPlan();
});

onBeforeUnmount(() => {
  if (snapshotUrl.value) URL.revokeObjectURL(snapshotUrl.value);
  cameraPaneRef.value?.stopCameraDrag();
  cameraPaneRef.value?.stopFloorRegionDrag();
  floorPlanPaneRef.value?.stopFloorDrag();
  disposePreviewTimer();
});
</script>
