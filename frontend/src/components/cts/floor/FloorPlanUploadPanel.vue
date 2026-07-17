<template>
  <div>
    <v-card class="glass-card upload-floor-plan-card mb-4">
      <v-card-title class="floor-plan-card-title d-flex align-center">
        <v-icon start size="18" color="primary">mdi-floor-plan</v-icon>
        Upload Floor Plan Image
      </v-card-title>
      <v-divider />
      <v-card-text class="pa-4">
        <div class="upload-intro d-flex align-start ga-3 mb-4">
          <v-icon size="20" color="primary">mdi-information-outline</v-icon>
          <div>
            <div class="text-body-2 font-weight-medium">Prepare the map for tracking</div>
            <div class="text-caption text-medium-emphasis mt-1">
              Choose a top-down JPEG or PNG up to 10 MB, optionally trim its margins, then set the
              real-world scale used by tracking and camera calibration.
            </div>
          </div>
        </div>

        <!-- Step 1: image selection and optional crop -->
        <section class="upload-step">
          <div class="upload-step-header d-flex align-start ga-3">
            <span class="upload-step-number">1</span>
            <div class="flex-grow-1">
              <div class="text-subtitle-2 font-weight-semibold">Choose the image</div>
              <div class="text-caption text-medium-emphasis">
                Dimensions are detected automatically. Existing values remain editable below.
              </div>
            </div>
          </div>

          <v-row dense class="upload-file-row mt-3">
            <v-col cols="12" md="8">
              <v-file-input
                v-model="uploadFile"
                label="Floor plan image"
                accept="image/jpeg,image/png"
                variant="outlined"
                prepend-icon="mdi-image-outline"
                density="compact"
                hide-details
                @update:model-value="onFileSelected"
              />
            </v-col>
            <v-col cols="12" md="4" class="upload-file-actions d-flex align-center justify-end flex-wrap ga-2">
              <v-chip
                v-if="uploadWidth && uploadHeight"
                size="small"
                variant="tonal"
                color="success"
                prepend-icon="mdi-check"
              >
                {{ uploadWidth }} × {{ uploadHeight }} px
              </v-chip>
              <v-btn
                v-if="uploadFile && uploadWidth && uploadHeight && !cropActive"
                variant="tonal"
                size="small"
                prepend-icon="mdi-crop"
                @click="startCropMode"
              >
                Trim margins
              </v-btn>
            </v-col>
          </v-row>

          <!-- Crop section: actions stay attached to the workspace. -->
          <div v-if="cropActive && scalePickerImageUrl" class="upload-crop-workspace mt-3">
            <div class="d-flex align-center flex-wrap ga-2 px-3 py-2">
              <div>
                <div class="text-body-2 font-weight-medium">Trim image margins</div>
                <div class="text-caption text-medium-emphasis">
                  Drag corners or draw a new crop area.
                </div>
              </div>
              <v-spacer />
              <v-btn variant="text" size="small" @click="resetCrop">Reset</v-btn>
              <v-btn color="primary" variant="tonal" size="small" prepend-icon="mdi-check" @click="applyCrop">
                Apply crop
              </v-btn>
            </div>
            <v-divider />
            <div ref="cropOuterRef" class="crop-outer" @wheel.prevent="cropZoom.actions.onWheel">
              <div class="crop-zoom-content" :style="cropZoom.state.transformStyle">
                <div class="crop-container" @mousedown="onCropMouseDown">
                  <img
                    ref="cropImgRef"
                    :src="scalePickerImageUrl"
                    class="crop-img marauders-no-paint"
                    draggable="false"
                    alt="Crop preview"
                    @load="onCropImgLoad"
                  />
                  <svg
                    v-if="cropImgRect"
                    class="crop-svg-overlay"
                    :viewBox="`0 0 ${cropImgRect.width} ${cropImgRect.height}`"
                    :style="`left:${cropImgRect.offsetX}px;top:${cropImgRect.offsetY}px;width:${cropImgRect.width}px;height:${cropImgRect.height}px`"
                  >
                    <defs>
                      <mask id="crop-mask">
                        <rect x="0" y="0" :width="cropImgRect.width" :height="cropImgRect.height" fill="white" />
                        <rect
                          :x="cropRect.x * cropImgRect.width"
                          :y="cropRect.y * cropImgRect.height"
                          :width="cropRect.w * cropImgRect.width"
                          :height="cropRect.h * cropImgRect.height"
                          fill="black"
                        />
                      </mask>
                    </defs>
                    <rect
                      x="0"
                      y="0"
                      :width="cropImgRect.width"
                      :height="cropImgRect.height"
                      fill="rgba(0,0,0,0.4)"
                      mask="url(#crop-mask)"
                    />
                    <rect
                      :x="cropRect.x * cropImgRect.width"
                      :y="cropRect.y * cropImgRect.height"
                      :width="cropRect.w * cropImgRect.width"
                      :height="cropRect.h * cropImgRect.height"
                      fill="none"
                      :stroke="tokWarning"
                      stroke-width="2.5"
                      stroke-dasharray="8 4"
                    />
                    <rect
                      v-for="handle in cropHandles"
                      :key="handle.corner"
                      class="crop-handle"
                      :x="handle.x * cropImgRect.width - 5"
                      :y="handle.y * cropImgRect.height - 5"
                      width="10"
                      height="10"
                      fill="white"
                      :stroke="tokWarning"
                      stroke-width="2"
                      :style="{ cursor: handle.cursor }"
                      @mousedown.stop="onCropHandleDown(handle.corner, $event)"
                    />
                  </svg>
                  <div v-if="!cropImgRect" class="d-flex align-center justify-center pa-8">
                    <span class="text-body-2 text-medium-emphasis">Loading image...</span>
                  </div>
                </div>
              </div>

              <CcZoomControls
                :zoom="cropZoom.state.zoom"
                :pan-x="cropZoom.state.panX"
                :pan-y="cropZoom.state.panY"
                @zoom-in="cropZoom.actions.zoomIn(cropOuterRef)"
                @zoom-out="cropZoom.actions.zoomOut(cropOuterRef)"
                @reset="cropZoom.actions.reset()"
              />
            </div>
            <div class="text-caption text-medium-emphasis px-3 py-2">
              Selection: {{ Math.round(uploadWidth * cropRect.w) }} ×
              {{ Math.round(uploadHeight * cropRect.h) }} px
            </div>
          </div>
        </section>

        <!-- Step 2: scale calibration -->
        <section class="upload-step">
          <div class="upload-step-header d-flex align-start flex-wrap ga-3">
            <span class="upload-step-number">2</span>
            <div class="flex-grow-1">
              <div class="text-subtitle-2 font-weight-semibold">Set the real-world scale</div>
              <div class="text-caption text-medium-emphasis">
                Measure two known points for best accuracy, or enter the map's total width.
              </div>
            </div>
            <CcSegmentedToggle v-model="scaleMethod" :options="SCALE_METHOD_OPTIONS" class="upload-scale-method" />
          </div>

          <!-- Method A: click two points -->
          <template v-if="scaleMethod === 'pickpoints'">
            <div class="text-caption text-medium-emphasis mt-3 mb-2">
              Click two points whose real distance you can measure, such as opposite room corners
              or the sides of a doorway.
            </div>

            <div ref="scaleOuterRef" class="scale-picker-outer" @wheel.prevent="scaleZoom.actions.onWheel">
              <div class="scale-picker-zoom-content" :style="scaleZoom.state.transformStyle">
                <div
                  class="scale-picker-inner"
                  :class="scalePoints.length < 2 ? 'cursor-crosshair' : ''"
                  @click="onScaleImageClick"
                  @mousedown="onScalePickerMouseDown"
                >
                  <img
                    v-if="scalePickerImageUrl"
                    ref="scaleImgEl"
                    :src="scalePickerImageUrl"
                    class="scale-picker-img marauders-no-paint"
                    draggable="false"
                    alt="Floor plan"
                    @load="onScaleImageLoad"
                  />
                  <div v-else class="scale-picker-empty d-flex align-center justify-center">
                    <v-icon size="32" color="medium-emphasis">mdi-image-outline</v-icon>
                    <span class="text-body-2 text-medium-emphasis ml-2">
                      Upload a floor plan image first
                    </span>
                  </div>

                  <svg
                    v-if="scalePickerImageUrl && scaleImgRect"
                    class="scale-picker-overlay"
                    :viewBox="`0 0 ${scaleImgRect.width} ${scaleImgRect.height}`"
                    :style="`left:${scaleImgRect.offsetX}px;top:${scaleImgRect.offsetY}px;width:${scaleImgRect.width}px;height:${scaleImgRect.height}px`"
                  >
                    <line
                      v-if="scalePoints.length === 2"
                      :x1="scalePoints[0][0] * scaleImgRect.width"
                      :y1="scalePoints[0][1] * scaleImgRect.height"
                      :x2="scalePoints[1][0] * scaleImgRect.width"
                      :y2="scalePoints[1][1] * scaleImgRect.height"
                      stroke="var(--cc-brand)"
                      stroke-width="2"
                      stroke-dasharray="6 4"
                    />
                    <text
                      v-if="scalePoints.length === 2"
                      :x="((scalePoints[0][0] + scalePoints[1][0]) / 2) * scaleImgRect.width"
                      :y="((scalePoints[0][1] + scalePoints[1][1]) / 2) * scaleImgRect.height - 8"
                      fill="var(--cc-brand)"
                      font-size="11"
                      font-weight="600"
                      text-anchor="middle"
                    >
                      {{ scalePixelDistance.toFixed(0) }} px
                    </text>
                    <g v-for="(pt, i) in scalePoints" :key="i">
                      <circle
                        :cx="pt[0] * scaleImgRect.width"
                        :cy="pt[1] * scaleImgRect.height"
                        r="8"
                        fill="none"
                        stroke="var(--cc-brand)"
                        stroke-width="2.5"
                      />
                      <circle :cx="pt[0] * scaleImgRect.width" :cy="pt[1] * scaleImgRect.height" r="3" fill="var(--cc-brand)" />
                      <text
                        :x="pt[0] * scaleImgRect.width + 12"
                        :y="pt[1] * scaleImgRect.height - 6"
                        fill="var(--cc-brand)"
                        font-size="12"
                        font-weight="bold"
                      >
                        {{ ["A", "B"][i] }}
                      </text>
                    </g>
                    <text
                      v-if="scalePoints.length === 0"
                      x="50%"
                      y="50%"
                      text-anchor="middle"
                      dominant-baseline="middle"
                      fill="var(--cc-brand)"
                      font-size="13"
                      opacity="0.6"
                    >
                      Click to place point A
                    </text>
                    <text
                      v-else-if="scalePoints.length === 1"
                      :x="scalePoints[0][0] * scaleImgRect.width + 20"
                      :y="scalePoints[0][1] * scaleImgRect.height + 16"
                      fill="var(--cc-brand)"
                      font-size="12"
                      opacity="0.8"
                    >
                      Click to place point B
                    </text>
                  </svg>
                </div>
              </div>

              <CcZoomControls
                :zoom="scaleZoom.state.zoom"
                :pan-x="scaleZoom.state.panX"
                :pan-y="scaleZoom.state.panY"
                @zoom-in="scaleZoom.actions.zoomIn(scaleOuterRef)"
                @zoom-out="scaleZoom.actions.zoomOut(scaleOuterRef)"
                @reset="scaleZoom.actions.reset()"
              />
            </div>

            <div class="upload-scale-controls d-flex align-center flex-wrap ga-2 mt-3">
              <div class="text-caption text-medium-emphasis">
                <template v-if="scalePoints.length === 2"> {{ scalePixelDistance.toFixed(0) }} pixels selected </template>
                <template v-else> {{ scalePoints.length }}/2 points placed </template>
              </div>
              <v-spacer />
              <v-btn
                size="small"
                variant="text"
                :disabled="scalePoints.length === 0"
                prepend-icon="mdi-close"
                @click="scalePoints = []"
              >
                Clear points
              </v-btn>
            </div>

            <v-row dense class="mt-1">
              <v-col cols="12" md="7">
                <v-text-field
                  v-model.number="scaleMeasuredM"
                  label="Measured distance between A and B (metres)"
                  variant="outlined"
                  density="compact"
                  type="number"
                  step="0.01"
                  :disabled="scalePoints.length < 2"
                  :hint="
                    scaleComputedMpp ? `Calculated scale: ${scaleComputedMpp} m/px` : 'Place both points, then enter the measured distance'
                  "
                  persistent-hint
                  @update:model-value="onScaleMeasuredChange"
                />
              </v-col>
              <v-col cols="12" md="5" class="d-flex align-start">
                <div class="upload-calculation-summary cc-inset-section px-3 py-2">
                  <div class="text-caption text-medium-emphasis">Calculated scale</div>
                  <div class="text-body-2 font-weight-medium mt-1">
                    {{ scaleComputedMpp ? `${scaleComputedMpp} m/px` : "Waiting for measurement" }}
                  </div>
                </div>
              </v-col>
            </v-row>
          </template>

          <!-- Method B: enter total width -->
          <template v-else>
            <v-row dense class="mt-3">
              <v-col cols="12" md="7">
                <v-text-field
                  v-model.number="uploadRealWidth"
                  label="Total real-world width (metres)"
                  variant="outlined"
                  density="compact"
                  type="number"
                  step="0.1"
                  :hint="
                    uploadRealWidth && uploadWidth
                      ? `Calculated scale: ${(uploadRealWidth / uploadWidth).toFixed(5)} m/px`
                      : 'For example, enter 12.5 for a 12.5 metre wide home'
                  "
                  persistent-hint
                  @update:model-value="onRealWidthChange"
                />
              </v-col>
              <v-col cols="12" md="5">
                <div class="upload-calculation-summary cc-inset-section px-3 py-2">
                  <div class="text-caption text-medium-emphasis">Image width</div>
                  <div class="text-body-2 font-weight-medium mt-1">
                    {{ uploadWidth ? `${uploadWidth} px` : "Select an image first" }}
                  </div>
                </div>
              </v-col>
            </v-row>
          </template>
        </section>

        <!-- Step 3: review editable values -->
        <section class="upload-step">
          <div class="upload-step-header d-flex align-start ga-3">
            <span class="upload-step-number">3</span>
            <div>
              <div class="text-subtitle-2 font-weight-semibold">Review map details</div>
              <div class="text-caption text-medium-emphasis">
                Confirm the calculated scale and detected image dimensions before saving.
              </div>
            </div>
          </div>

          <v-row dense class="mt-3">
            <v-col cols="12" md="4">
              <v-text-field
                v-model.number="uploadMpp"
                label="Scale (m/px)"
                variant="outlined"
                density="compact"
                type="number"
                step="0.00001"
                hint="Metres represented by one image pixel"
                persistent-hint
              />
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field v-model.number="uploadWidth" label="Width (px)" variant="outlined" density="compact" type="number" hide-details />
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field v-model.number="uploadHeight" label="Height (px)" variant="outlined" density="compact" type="number" hide-details />
            </v-col>
          </v-row>
        </section>
      </v-card-text>
      <v-divider />
      <v-card-actions class="upload-save-actions px-4 py-3">
        <div class="upload-save-summary">
          <div class="text-body-2 font-weight-medium">
            {{ uploadFile ? "New image ready to save" : "Update floor plan settings" }}
          </div>
          <div class="text-caption text-medium-emphasis">
            <template v-if="uploadMpp && uploadWidth && uploadHeight">
              {{ uploadWidth }} × {{ uploadHeight }} px ·
              {{ (uploadWidth * uploadMpp).toFixed(1) }} × {{ (uploadHeight * uploadMpp).toFixed(1) }} metres
            </template>
            <template v-else> Image dimensions and scale are required for accurate mapping. </template>
          </div>
        </div>
        <v-spacer />
        <v-btn
          color="primary"
          variant="flat"
          min-width="150"
          :loading="uploading"
          :disabled="!uploadFile && !uploadWidth && !uploadHeight && !uploadMpp"
          prepend-icon="mdi-content-save"
          @click="uploadFloorPlan"
        >
          Save floor plan
        </v-btn>
      </v-card-actions>
    </v-card>

    <!-- Current floor plan preview -->
    <v-card v-if="floorPlanUrl" class="glass-card floor-plan-visual-card">
      <v-card-title class="floor-plan-card-title">Current Floor Plan</v-card-title>
      <v-divider />
      <v-card-text class="pa-3">
        <img :src="floorPlanUrl" class="floor-plan-preview marauders-no-paint" alt="Floor plan" />
        <div class="text-caption text-medium-emphasis mt-2">
          <template v-if="fpWidth && fpHeight">{{ fpWidth }} × {{ fpHeight }} px</template>
          <template v-if="fpMpp">
            · {{ fpMpp }} m/px · covers {{ (fpWidth * fpMpp).toFixed(1) }} × {{ (fpHeight * fpMpp).toFixed(1) }} m
          </template>
        </div>
      </v-card-text>
    </v-card>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount } from "vue";
import { useNotify } from "@/composables/useNotify";
import { ccToken } from "@/composables/useChartTheme.js";
import { useFloorPlanUpload } from "@/composables/useFloorPlanUpload.js";
import CcZoomControls from "@/components/common/CcZoomControls.vue";
import CcSegmentedToggle from "@/components/common/CcSegmentedToggle.vue";

const props = defineProps({
  floorPlanUrl: { type: String, default: null },
  fpWidth: { type: Number, default: null },
  fpHeight: { type: Number, default: null },
  fpMpp: { type: Number, default: null },
});
const emit = defineEmits(["saved"]);

const { notify } = useNotify();
const tokWarning = computed(() => ccToken("--cc-warning"));

const floorPlanUrlRef = computed(() => props.floorPlanUrl);
const fpWidthRef = computed(() => props.fpWidth);
const fpHeightRef = computed(() => props.fpHeight);
const fpMppRef = computed(() => props.fpMpp);

const {
  uploading,
  uploadFile,
  uploadWidth,
  uploadHeight,
  uploadMpp,
  scaleMethod,
  SCALE_METHOD_OPTIONS,
  uploadRealWidth,
  scalePoints,
  scaleMeasuredM,
  scaleImgEl,
  scaleImgRect,
  scaleOuterRef,
  scaleZoom,
  cropOuterRef,
  cropZoom,
  cropActive,
  cropRect,
  cropImgRef,
  cropImgRect,
  cropHandles,
  scalePickerImageUrl,
  scalePixelDistance,
  scaleComputedMpp,
  onFileSelected,
  onScaleImageLoad,
  onScaleImageClick,
  onScalePickerMouseDown,
  onScaleMeasuredChange,
  onRealWidthChange,
  onCropImgLoad,
  startCropMode,
  resetCrop,
  onCropMouseDown,
  onCropHandleDown,
  applyCrop,
  uploadFloorPlan,
  dispose,
} = useFloorPlanUpload(notify, floorPlanUrlRef, fpWidthRef, fpHeightRef, fpMppRef, (data) =>
  emit("saved", data),
);

onBeforeUnmount(dispose);
</script>

<style scoped>
.upload-floor-plan-card {
  overflow: hidden;
}

.upload-intro {
  padding: 12px 14px;
  background: var(--cc-brand-softer);
  border: 1px solid var(--cc-divider);
  border-radius: var(--cc-radius-md);
}

.upload-step {
  padding: 16px;
  background: var(--cc-surface-2);
  border: 1px solid var(--cc-divider);
  border-radius: var(--cc-radius-md);
}

.upload-step + .upload-step {
  margin-top: 14px;
}

.upload-step-number {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  flex: 0 0 26px;
  color: var(--cc-brand);
  font-size: 0.75rem;
  font-weight: 700;
  background: var(--cc-brand-soft);
  border: 1px solid var(--cc-divider-strong);
  border-radius: var(--cc-radius-pill);
}

.upload-file-actions {
  min-height: 40px;
}

.upload-crop-workspace {
  overflow: hidden;
  background: var(--cc-bg-elevated);
  border: 1px solid var(--cc-divider-strong);
  border-radius: var(--cc-radius-md);
}

.upload-crop-workspace .crop-outer {
  border: 0;
  border-radius: 0;
}

.upload-scale-method {
  flex-shrink: 0;
}

.upload-scale-controls {
  min-height: 32px;
}

.upload-calculation-summary {
  width: 100%;
  min-height: 64px;
}

.upload-save-actions {
  min-height: 68px;
  flex-wrap: wrap;
  gap: 12px;
  background: var(--cc-surface-2);
}

.upload-save-summary {
  min-width: 220px;
}

/* ── Scale picker zoom ─────────────────────────────────────────────── */
.scale-picker-outer {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--cc-divider-strong, rgba(0, 0, 0, 0.12));
  border-radius: 6px;
  background: var(--cc-surface-2);
  min-height: 240px;
  max-height: min(560px, 70vh);
}

.scale-picker-zoom-content {
  display: inline-block;
  position: relative;
  will-change: transform;
}

.scale-picker-inner {
  position: relative;
  display: inline-block;
  user-select: none;
}

.scale-picker-img {
  display: block;
  width: 100%;
  max-height: min(560px, 70vh);
  object-fit: contain;
}

.scale-picker-empty {
  height: 240px;
  background: var(--cc-surface-2, rgba(0, 0, 0, 0.03));
}

.scale-picker-overlay {
  position: absolute;
  pointer-events: none;
}

/* ── Crop zoom ─────────────────────────────────────────────────────── */
.crop-outer {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--cc-divider-strong, rgba(0, 0, 0, 0.12));
  border-radius: 6px;
  background: var(--cc-surface-2);
  min-height: 240px;
  max-height: min(480px, 60vh);
}

.crop-zoom-content {
  display: inline-block;
  position: relative;
  will-change: transform;
}

.crop-container {
  position: relative;
  display: inline-block;
  user-select: none;
}

.crop-img {
  display: block;
  width: 100%;
  max-height: min(480px, 60vh);
  object-fit: contain;
}

.crop-svg-overlay {
  position: absolute;
  pointer-events: none;
}

.cursor-crosshair {
  cursor: crosshair;
}
/* Corner handles receive pointer events so they're draggable. */
.crop-svg-overlay .crop-handle {
  pointer-events: auto;
}

@media (max-width: 959px) {
  .upload-file-actions {
    justify-content: flex-start !important;
  }

  .upload-scale-method {
    width: 100%;
  }

  .upload-scale-method :deep(.v-btn) {
    flex: 1 1 0;
  }

  .upload-save-actions .v-spacer {
    display: none;
  }

  .upload-save-summary {
    width: 100%;
  }

  .upload-save-actions :deep(.v-btn) {
    width: 100%;
  }
}
</style>
