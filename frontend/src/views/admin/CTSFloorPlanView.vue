<template>
  <div>
    <!-- Header -->
    <div class="d-flex align-center mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Floor Plan</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Upload a floor plan image and draw room polygons. Active people appear as dots in real time.
        </div>
      </div>
      <v-spacer />
      <div class="d-flex ga-2">
        <v-btn
          size="small"
          :variant="mode === 'live' ? 'flat' : 'outlined'"
          :color="mode === 'live' ? 'primary' : undefined"
          @click="mode = 'live'"
        >
          Live
        </v-btn>
        <v-btn
          size="small"
          :variant="mode === 'edit' ? 'flat' : 'outlined'"
          :color="mode === 'edit' ? 'primary' : undefined"
          @click="mode = 'edit'"
        >
          Edit Rooms
        </v-btn>
        <v-btn
          size="small"
          :variant="mode === 'upload' ? 'flat' : 'outlined'"
          :color="mode === 'upload' ? 'primary' : undefined"
          @click="mode = 'upload'"
        >
          Floor Plan
        </v-btn>
        <v-btn
          size="small"
          :variant="mode === 'coverage' ? 'flat' : 'outlined'"
          :color="mode === 'coverage' ? 'primary' : undefined"
          @click="mode = 'coverage'"
        >
          Coverage
        </v-btn>
        <v-btn
          size="small"
          :variant="mode === 'doors' ? 'flat' : 'outlined'"
          :color="mode === 'doors' ? 'primary' : undefined"
          @click="mode = 'doors'"
        >
          Door Zones
        </v-btn>
      </div>
    </div>

    <!-- ── Upload panel ───────────────────────────────────────────────────── -->
    <template v-if="mode === 'upload'">
      <v-card class="glass-card mb-4">
        <v-card-title>Upload Floor Plan Image</v-card-title>
        <v-divider />
        <v-card-text>
          <v-alert type="info" variant="tonal" density="compact" class="mb-4 text-body-2">
            Upload a top-down floor plan of the home (JPEG or PNG, up to 10 MB).
            Image dimensions are detected automatically. Setting the real-world scale lets
            the system convert pixel positions to metres for person tracking and camera calibration.
          </v-alert>

          <!-- File input -->
          <v-row dense class="mb-2">
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
            <v-col v-if="uploadWidth && uploadHeight" cols="12" md="4" class="d-flex align-center">
              <v-chip size="small" variant="tonal" color="success" prepend-icon="mdi-check">
                {{ uploadWidth }} × {{ uploadHeight }} px detected
              </v-chip>
            </v-col>
          </v-row>

          <!-- Crop section — visual draw-to-crop bounding box -->
          <template v-if="uploadFile && uploadWidth && uploadHeight">
            <v-divider class="my-4" />
            <div class="d-flex align-center mb-2">
              <div class="text-subtitle-2">Crop margins</div>
              <v-spacer />
              <v-btn
                v-if="!cropActive"
                variant="text"
                size="small"
                prepend-icon="mdi-crop"
                @click="startCropMode"
              >
                Trim margins
              </v-btn>
              <template v-else>
                <v-btn variant="text" size="small" @click="resetCrop">Reset</v-btn>
                <v-btn
                  color="primary"
                  variant="tonal"
                  size="small"
                  class="ml-2"
                  prepend-icon="mdi-check"
                  @click="applyCrop"
                >
                  Apply crop
                </v-btn>
              </template>
            </div>

            <!-- Draw-to-crop overlay (SVG-based, follows scale picker pattern) -->
            <div
              v-if="cropActive && scalePickerImageUrl"
              ref="cropOuterRef"
              class="crop-outer"
              @wheel.prevent="cropZoom.actions.onWheel"
            >
              <div class="crop-zoom-content" :style="cropZoom.state.transformStyle">
                <div
                  class="crop-container"
                  @mousedown="onCropMouseDown"
                >
                  <img
                    ref="cropImgRef"
                    :src="scalePickerImageUrl"
                    class="crop-img"
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
                    <!-- Dimmed backdrop: full image minus crop area -->
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
                      x="0" y="0"
                      :width="cropImgRect.width" :height="cropImgRect.height"
                      fill="rgba(0,0,0,0.4)"
                      mask="url(#crop-mask)"
                    />
                    <!-- Crop rectangle border -->
                    <rect
                      :x="cropRect.x * cropImgRect.width"
                      :y="cropRect.y * cropImgRect.height"
                      :width="cropRect.w * cropImgRect.width"
                      :height="cropRect.h * cropImgRect.height"
                      fill="none"
                      :stroke="_tokWarning"
                      stroke-width="2.5"
                      stroke-dasharray="8 4"
                    />
                    <!-- Corner drag handles -->
                    <rect
                      v-for="handle in cropHandles"
                      :key="handle.corner"
                      class="crop-handle"
                      :x="handle.x * cropImgRect.width - 5"
                      :y="handle.y * cropImgRect.height - 5"
                      width="10" height="10"
                      fill="white"
                      :stroke="_tokWarning"
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
            <div v-if="cropActive" class="text-caption text-medium-emphasis mt-1">
              Drag corners to adjust, or click &amp; drag on empty area to redraw.
              Cropped: {{ Math.round(uploadWidth * cropRect.w) }} × {{ Math.round(uploadHeight * cropRect.h) }} px
            </div>
          </template>

          <!-- Scale section -->
          <div class="text-subtitle-2 mb-3 mt-4">Real-world scale</div>

          <v-btn-toggle
            v-model="scaleMethod"
            mandatory
            density="compact"
            variant="outlined"
            class="mb-4"
          >
            <v-btn value="pickpoints" size="small">
              <v-icon start size="15">mdi-cursor-pointer</v-icon>Click on image
            </v-btn>
            <v-btn value="realwidth" size="small">
              <v-icon start size="15">mdi-ruler</v-icon>Enter total width
            </v-btn>
          </v-btn-toggle>

          <!-- Method A: click two points -->
          <template v-if="scaleMethod === 'pickpoints'">
            <div class="text-caption text-medium-emphasis mb-2">
              Click any two points whose real-world distance you can measure with a tape
              (e.g. opposite corners of a room, two sides of a doorway).
            </div>

            <!-- Image picker area with zoom -->
            <div
              ref="scaleOuterRef"
              class="scale-picker-outer mb-2"
              @wheel.prevent="scaleZoom.actions.onWheel"
            >
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
                    class="scale-picker-img"
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

                  <!-- SVG overlay -->
                  <svg
                    v-if="scalePickerImageUrl && scaleImgRect"
                    class="scale-picker-overlay"
                    :viewBox="`0 0 ${scaleImgRect.width} ${scaleImgRect.height}`"
                    :style="`left:${scaleImgRect.offsetX}px;top:${scaleImgRect.offsetY}px;width:${scaleImgRect.width}px;height:${scaleImgRect.height}px`"
                  >
                    <!-- Connecting line -->
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
                    <!-- Midpoint label -->
                    <text
                      v-if="scalePoints.length === 2"
                      :x="(scalePoints[0][0] + scalePoints[1][0]) / 2 * scaleImgRect.width"
                      :y="(scalePoints[0][1] + scalePoints[1][1]) / 2 * scaleImgRect.height - 8"
                      fill="var(--cc-brand)"
                      font-size="11"
                      font-weight="600"
                      text-anchor="middle"
                    >{{ scalePixelDistance.toFixed(0) }} px</text>
                    <!-- Point dots -->
                    <g v-for="(pt, i) in scalePoints" :key="i">
                      <circle
                        :cx="pt[0] * scaleImgRect.width"
                        :cy="pt[1] * scaleImgRect.height"
                        r="8"
                        fill="none"
                        stroke="var(--cc-brand)"
                        stroke-width="2.5"
                      />
                      <circle
                        :cx="pt[0] * scaleImgRect.width"
                        :cy="pt[1] * scaleImgRect.height"
                        r="3"
                        fill="var(--cc-brand)"
                      />
                      <text
                        :x="pt[0] * scaleImgRect.width + 12"
                        :y="pt[1] * scaleImgRect.height - 6"
                        fill="var(--cc-brand)"
                        font-size="12"
                        font-weight="bold"
                      >{{ ['A', 'B'][i] }}</text>
                    </g>
                    <!-- Instruction when no points yet -->
                    <text
                      v-if="scalePoints.length === 0"
                      x="50%"
                      y="50%"
                      text-anchor="middle"
                      dominant-baseline="middle"
                      fill="var(--cc-brand)"
                      font-size="13"
                      opacity="0.6"
                    >Click to place point A</text>
                    <text
                      v-else-if="scalePoints.length === 1"
                      :x="scalePoints[0][0] * scaleImgRect.width + 20"
                      :y="scalePoints[0][1] * scaleImgRect.height + 16"
                      fill="var(--cc-brand)"
                      font-size="12"
                      opacity="0.8"
                    >Click to place point B</text>
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

            <!-- Controls below image -->
            <div class="d-flex align-center mb-3">
              <v-btn
                size="small"
                variant="tonal"
                :disabled="scalePoints.length === 0"
                prepend-icon="mdi-close"
                @click="scalePoints = []"
              >
                Clear points
              </v-btn>
              <v-spacer />
              <span v-if="scalePoints.length === 2" class="text-caption text-medium-emphasis">
                {{ scalePixelDistance.toFixed(0) }} image pixels between A and B
              </span>
            </div>

            <v-row dense v-if="scalePoints.length === 2">
              <v-col cols="12" md="5">
                <v-text-field
                  v-model.number="scaleMeasuredM"
                  label="Real distance between A and B (metres)"
                  variant="outlined"
                  density="compact"
                  type="number"
                  step="0.01"
                  :hint="scaleComputedMpp ? `→ ${scaleComputedMpp} m/px` : 'Measure A→B with a tape measure on the actual floor'"
                  persistent-hint
                  @update:model-value="onScaleMeasuredChange"
                />
              </v-col>
            </v-row>
            <div v-else class="text-caption text-medium-emphasis mb-3">
              Place both points first, then enter the measured distance.
            </div>
          </template>

          <!-- Method B: enter total width -->
          <template v-else>
            <div class="text-caption text-medium-emphasis mb-2">
              How wide is the area this floor plan represents in real life?
            </div>
            <v-row dense>
              <v-col cols="12" md="5">
                <v-text-field
                  v-model.number="uploadRealWidth"
                  label="Total real-world width (metres)"
                  variant="outlined"
                  density="compact"
                  type="number"
                  step="0.1"
                  :hint="uploadRealWidth && uploadWidth
                    ? `→ ${(uploadRealWidth / uploadWidth).toFixed(5)} m/px`
                    : 'e.g. 12.5 for a 12.5 m wide house'"
                  persistent-hint
                  @update:model-value="onRealWidthChange"
                />
              </v-col>
            </v-row>
          </template>

          <!-- Result row: final mpp + dimensions -->
          <v-divider class="my-4" />
          <v-row dense>
            <v-col cols="12" md="4">
              <v-text-field
                v-model.number="uploadMpp"
                label="Scale (m/px)"
                variant="outlined"
                density="compact"
                type="number"
                step="0.00001"
                hint="Metres per pixel — auto-filled above, or type directly"
                persistent-hint
              />
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field
                v-model.number="uploadWidth"
                label="Width (px)"
                variant="outlined"
                density="compact"
                type="number"
                hide-details
              />
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field
                v-model.number="uploadHeight"
                label="Height (px)"
                variant="outlined"
                density="compact"
                type="number"
                hide-details
              />
            </v-col>
          </v-row>
          <div v-if="uploadMpp && uploadWidth && uploadHeight" class="text-caption text-medium-emphasis mt-1">
            This floor plan covers {{ (uploadWidth * uploadMpp).toFixed(1) }} × {{ (uploadHeight * uploadMpp).toFixed(1) }} metres.
          </div>
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn
            color="primary"
            variant="flat"
            :loading="uploading"
            :disabled="!uploadFile && !uploadWidth && !uploadHeight && !uploadMpp"
            prepend-icon="mdi-upload"
            @click="uploadFloorPlan"
          >
            Save
          </v-btn>
        </v-card-actions>
      </v-card>

      <!-- Current floor plan preview -->
      <v-card v-if="floorPlanUrl" class="glass-card">
        <v-card-title>Current Floor Plan</v-card-title>
        <v-divider />
        <v-card-text>
          <img :src="floorPlanUrl" class="floor-plan-preview" alt="Floor plan" />
          <div class="text-caption text-medium-emphasis mt-2">
            <template v-if="fpWidth && fpHeight">{{ fpWidth }} × {{ fpHeight }} px</template>
            <template v-if="fpMpp">
              · {{ fpMpp }} m/px
              · covers {{ (fpWidth * fpMpp).toFixed(1) }} × {{ (fpHeight * fpMpp).toFixed(1) }} m
            </template>
          </div>
        </v-card-text>
      </v-card>
    </template>

    <!-- ── Edit rooms panel ───────────────────────────────────────────────── -->
    <template v-else-if="mode === 'edit'">
      <v-alert type="info" variant="tonal" density="compact" class="mb-4 text-body-2">
        Select a room, then draw its polygon on the floor plan below. Right-click a vertex to
        delete it. Drag vertices to adjust. Click "Save polygon" to persist.
      </v-alert>

      <v-row>
        <v-col cols="12" md="3">
          <v-card class="glass-card">
            <v-card-title class="text-subtitle-2">Rooms</v-card-title>
            <v-divider />
            <v-list density="compact" nav>
              <v-list-item
                v-for="room in rooms"
                :key="room.id"
                :title="room.name"
                :subtitle="room.floor_polygon ? `${room.floor_polygon.length} pts` : 'No polygon'"
                :active="editingRoom?.id === room.id"
                rounded="lg"
                @click="selectRoom(room)"
              >
                <template #append>
                  <v-icon v-if="room.floor_polygon" color="success" size="small">mdi-check-circle</v-icon>
                </template>
              </v-list-item>
              <v-list-item v-if="rooms.length === 0" class="text-medium-emphasis text-body-2">
                No rooms configured. Add rooms in the Rooms view.
              </v-list-item>
            </v-list>
          </v-card>
        </v-col>

        <v-col cols="12" md="9">
          <v-card class="glass-card">
            <v-card-title class="d-flex align-center">
              <span>{{ editingRoom ? editingRoom.name : 'Select a room' }}</span>
              <v-spacer />
              <v-btn
                v-if="editingRoom && editPolygon.length > 0"
                size="small"
                variant="text"
                color="error"
                class="mr-2"
                @click="editPolygon = []"
              >
                Clear
              </v-btn>
              <v-btn
                v-if="editingRoom"
                color="primary"
                variant="flat"
                size="small"
                :loading="savingRoom"
                :disabled="(editPolygon.length > 0 && editPolygon.length < 3) || (editPolygon.length === 0 && !editingRoom?.floor_polygon)"
                @click="saveRoomPolygon"
              >
                {{ editPolygon.length === 0 && editingRoom?.floor_polygon ? 'Delete polygon' : 'Save polygon' }}
              </v-btn>
            </v-card-title>
            <v-card-text class="pa-0">
              <PolygonOnSnapshot
                :image-url="floorPlanUrl"
                :model-value="editPolygon"
                :min-points="3"
                :readonly="!editingRoom"
                @update:model-value="editPolygon = $event"
              />
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>
    </template>

    <!-- ── Coverage panel ──────────────────────────────────────────────────── -->
    <template v-else-if="mode === 'coverage'">
      <v-card class="glass-card">
        <v-card-title class="d-flex align-center">
          Camera Coverage
          <v-spacer />
          <v-btn
            variant="tonal"
            size="small"
            prepend-icon="mdi-refresh"
            :loading="coverageLoading"
            @click="loadCoverage"
            class="mr-2"
          >
            Refresh
          </v-btn>
        </v-card-title>
        <v-divider />

        <div class="d-flex align-center flex-wrap ga-4 px-4 py-2 text-caption text-medium-emphasis">
          <span class="d-flex align-center ga-1">
            <span class="coverage-legend-swatch" :style="{ borderColor: _tokBrand, background: _tokBrandSoft }" />
            Calibrated
          </span>
          <span class="d-flex align-center ga-1">
            <span class="coverage-legend-swatch" :style="{ borderColor: _tokText3, background: 'rgba(128,128,128,0.1)', borderStyle: 'dotted' }" />
            Not calibrated
          </span>
        </div>
        <v-divider />

        <v-card-text class="pa-0">
          <div class="coverage-canvas-wrap">
            <img
              v-if="floorPlanUrl"
              :src="floorPlanUrl"
              class="coverage-fp-img"
              ref="coverageImgRef"
              @load="onCoverageImgLoad"
              alt="Floor plan"
              draggable="false"
            />

            <svg
              v-if="coverageImgReady && floorPlanUrl"
              class="coverage-svg-overlay"
              :viewBox="`0 0 ${coverageImgW} ${coverageImgH}`"
              xmlns="http://www.w3.org/2000/svg"
            >
              <g v-for="cam in coverageCameras" :key="cam.camera_id">
                <polygon
                  v-if="cam.visibility_polygon"
                  :points="toCoverageSvgPoints(cam.visibility_polygon)"
                  :fill="_tokBrandSoft"
                  :stroke="_tokBrand"
                  stroke-width="2"
                />
                <text
                  v-if="cam.visibility_polygon"
                  :x="coverageCentroid(cam.visibility_polygon)[0]"
                  :y="coverageCentroid(cam.visibility_polygon)[1]"
                  text-anchor="middle"
                  dominant-baseline="middle"
                  font-size="12"
                  font-family="system-ui, sans-serif"
                  fill="white"
                  paint-order="stroke"
                  stroke="rgba(0,0,0,0.7)"
                  stroke-width="3"
                  style="pointer-events:none"
                >{{ cam.camera_name }}</text>
              </g>
            </svg>

            <div v-if="!floorPlanUrl" class="coverage-empty d-flex flex-column align-center justify-center">
              <v-icon size="48" color="medium-emphasis">mdi-floor-plan</v-icon>
              <div class="text-body-2 text-medium-emphasis mt-2">
                Upload a floor plan first.
              </div>
              <v-btn variant="tonal" size="small" class="mt-3" @click="mode = 'upload'">
                Go to Floor Plan
              </v-btn>
            </div>
          </div>

          <div v-if="uncalibratedCoverage.length > 0" class="px-4 py-3">
            <v-alert type="warning" density="compact" variant="tonal">
              <strong>{{ uncalibratedCoverage.length }} camera(s) not shown</strong>
              &mdash;
              <span v-if="uncalibratedCoverage.some(c => c.has_homography)">
                visibility polygon could not be computed.
                Check that the floor plan scale (m/pixel) is correct in
                <router-link :to="{ name: 'cts-floor-plan' }" class="text-primary">Floor Plan settings</router-link>.
              </span>
              <span v-else>
                no homography calibration yet.
                <v-btn
                  variant="text"
                  size="x-small"
                  class="ml-1"
                  :to="{ name: 'CTSCalibration' }"
                >
                  Calibrate &rarr;
                </v-btn>
              </span>
            </v-alert>
          </div>
        </v-card-text>
      </v-card>
    </template>

    <!-- ── Door Zones panel ─────────────────────────────────────────────────── -->
    <template v-else-if="mode === 'doors'">
      <v-card class="glass-card">
        <v-card-title class="d-flex align-center">
          Door Zones
          <v-spacer />
          <v-btn
            variant="tonal"
            size="small"
            prepend-icon="mdi-plus"
            :disabled="!rooms.length"
            @click="showDoorZoneDialog = true"
          >
            Add Zone
          </v-btn>
        </v-card-title>
        <v-divider />
        <v-card-text>
          <p class="text-body-2 text-medium-emphasis mb-4">
            Door zones track when a person enters or leaves a room with no camera.
            If a room has no camera, use a door zone to detect entry and exit events.
          </p>

          <div v-if="doorZonesLoading" class="text-caption">Loading...</div>
          <div v-else-if="!doorZones.length" class="text-body-2 text-medium-emphasis">
            No door zones configured. Add one to track entry/exit for camera-blind rooms.
          </div>
          <div v-else class="d-flex flex-wrap ga-3">
            <v-card
              v-for="zone in doorZones"
              :key="zone.id"
              class="glass-card"
              width="300"
              :border="true"
            >
              <v-card-item>
                <template #title>{{ zone.name }}</template>
                <template #subtitle>
                  {{ zone.kind === 'door' ? 'Door' : 'Threshold' }}
                </template>
              </v-card-item>
              <v-card-text class="text-caption">
                <div>Inside: room {{ zone.inside_room_id }}</div>
                <div>Outside: room {{ zone.outside_room_id }}</div>
                <div>{{ zone.polygon?.length || 0 }} polygon vertices</div>
              </v-card-text>
              <v-card-actions>
                <v-spacer />
                <v-btn
                  icon="mdi-delete"
                  variant="text"
                  size="small"
                  color="error"
                  @click="deleteDoorZone(zone.id)"
                />
              </v-card-actions>
            </v-card>
          </div>
        </v-card-text>
      </v-card>

      <!-- Add Door Zone Dialog -->
      <v-dialog v-model="showDoorZoneDialog" max-width="500">
        <v-card>
          <v-card-title>Add Door Zone</v-card-title>
          <v-card-text>
            <v-text-field
              v-model="newDoorZone.name"
              label="Name"
              variant="outlined"
              density="compact"
              class="mb-3"
            />
            <v-select
              v-model="newDoorZone.kind"
              :items="['door', 'threshold']"
              label="Type"
              variant="outlined"
              density="compact"
              class="mb-3"
            />
            <v-select
              v-model="newDoorZone.inside_room_id"
              :items="rooms"
              item-title="name"
              item-value="id"
              label="Inside Room"
              variant="outlined"
              density="compact"
              class="mb-3"
            />
            <v-select
              v-model="newDoorZone.outside_room_id"
              :items="rooms"
              item-title="name"
              item-value="id"
              label="Outside Room"
              variant="outlined"
              density="compact"
              class="mb-3"
            />
            <p class="text-caption text-medium-emphasis">
              Direction vector: [{{ newDoorZone.direction_vec.join(', ') }}]
            </p>
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn variant="text" @click="showDoorZoneDialog = false">Cancel</v-btn>
            <v-btn
              variant="tonal"
              color="primary"
              :disabled="!newDoorZone.name || !newDoorZone.inside_room_id || !newDoorZone.outside_room_id"
              :loading="doorZoneCreating"
              @click="createDoorZone"
            >
              Create
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
    </template>

    <!-- ── Live view ─────────────────────────────────────────────────────── -->
    <template v-else>
      <v-row>
        <!-- Floor plan SVG -->
        <v-col cols="12" md="9">
          <v-card class="glass-card">
            <v-card-title class="d-flex align-center">
              <span>Live Floor Plan</span>
              <v-spacer />
              <v-chip
                v-if="!floorPlanUrl"
                color="warning"
                size="small"
                variant="tonal"
                prepend-icon="mdi-alert-outline"
                class="mr-2"
              >
                No floor plan
              </v-chip>
              <v-chip
                v-if="uncalibratedPhCount > 0"
                color="warning"
                size="small"
                variant="tonal"
                prepend-icon="mdi-crosshairs-off"
                class="mr-2"
                @click="router.push({ name: 'CTSCalibration' })"
              >
                {{ uncalibratedPhCount }} person(s) off-plan
              </v-chip>
              <v-chip
                :color="worldStatusColor"
                size="small"
                variant="tonal"
              >
                <v-icon start size="14">{{ worldStatusIcon }}</v-icon>
                {{ worldStatusLabel }}
              </v-chip>
            </v-card-title>
            <v-divider />
            <v-card-text class="pa-2">
              <!-- Floor plan canvas with pan/zoom. The outer div clips the zoomed
                   content; the inner zoom-content div receives the CSS transform. -->
              <div
                ref="liveCanvasRef"
                class="floor-plan-canvas"
                :style="{ aspectRatio: `${canvasW}/${canvasH}`, maxHeight: '65vh' }"
                @wheel.prevent="liveZoom.actions.onWheel"
              >
                <div
                  class="floor-plan-zoom-content"
                  :style="liveZoom.state.transformStyle"
                  @mousedown="onLiveZoomMouseDown"
                >
                  <svg
                    :viewBox="`0 0 ${canvasW} ${canvasH}`"
                    class="floor-plan-svg"
                  >
                    <!-- Background floor plan image -->
                    <image
                      v-if="floorPlanUrl"
                      :href="floorPlanUrl"
                      :width="canvasW"
                      :height="canvasH"
                      opacity="0.45"
                    />

                    <!-- Room polygons -->
                    <g v-for="room in rooms" :key="room.id">
                      <polygon
                        v-if="room.floor_polygon && room.floor_polygon.length >= 3"
                        :points="room.floor_polygon.map(([x, y]) => `${x * canvasW},${y * canvasH}`).join(' ')"
                        class="room-poly"
                      />
                      <text
                        v-if="room.floor_polygon && room.floor_polygon.length >= 3"
                        :x="centroidX(room.floor_polygon) * canvasW"
                        :y="centroidY(room.floor_polygon) * canvasH"
                        class="room-label"
                      >
                        {{ room.name }}
                      </text>
                    </g>

                    <!-- N4: PH-driven markers — positions are interpolated by the
                         smoothedMarkers watcher for jitter-free 5 Hz updates -->
                    <PHMarker
                      v-for="m in smoothedMarkers"
                      :key="m.ph.ph_id || m.ph.identity_id"
                      :ph="m.ph"
                      :x="m.x"
                      :y="m.y"
                      :color="m.color"
                      @click="onPhClick"
                    />

                    <!-- Empty state -->
                    <text
                      v-if="worldPhMarkers.length === 0"
                      x="50%"
                      y="50%"
                      text-anchor="middle"
                      fill="#888"
                      :font-size="Math.round(canvasH * 0.025)"
                    >
                      No active tracks. Waiting for live data…
                    </text>
                  </svg>
                </div>

                <CcZoomControls
                  :zoom="liveZoom.state.zoom"
                  :pan-x="liveZoom.state.panX"
                  :pan-y="liveZoom.state.panY"
                  :max-zoom="5"
                  :min-zoom="0.3"
                  @zoom-in="liveZoom.actions.zoomIn(liveCanvasRef)"
                  @zoom-out="liveZoom.actions.zoomOut(liveCanvasRef)"
                  @reset="liveZoom.actions.reset()"
                />
              </div>

              <!-- Legend -->
              <div class="d-flex align-center ga-4 px-2 pt-2">
                <div class="d-flex align-center ga-1 text-caption text-medium-emphasis">
                  <svg width="28" height="14">
                    <line x1="0" y1="7" x2="28" y2="7" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
                    <circle cx="14" cy="7" r="5" fill="currentColor" stroke="#fff" stroke-width="1.5" />
                  </svg>
                  Floor-mapped
                </div>
                <div class="d-flex align-center ga-1 text-caption text-medium-emphasis">
                  <svg width="28" height="14">
                    <line x1="0" y1="7" x2="28" y2="7" stroke="currentColor" stroke-width="2" stroke-dasharray="5 3" stroke-linecap="round" />
                    <circle cx="14" cy="7" r="5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-dasharray="4 2" />
                  </svg>
                  Estimated (no homography)
                </div>
              </div>
            </v-card-text>
          </v-card>
        </v-col>

        <!-- Active persons sidebar -->
        <v-col cols="12" md="3">
          <v-card class="glass-card">
            <v-card-title class="text-subtitle-2 d-flex align-center">
              <v-icon start size="16" color="success">mdi-account-multiple</v-icon>
              Active Persons
              <v-chip class="ml-2" size="x-small" color="primary">{{ activePersons.length }}</v-chip>
            </v-card-title>
            <v-divider />
            <v-list density="compact" class="pa-1">
              <v-list-item
                v-for="person in activePersons"
                :key="person.gtId"
                class="person-card rounded-lg mb-1"
                :style="`border-left: 3px solid ${person.color}`"
              >
                <template #prepend>
                  <div
                    class="person-dot mr-3"
                    :style="`background: ${person.color}`"
                  />
                </template>
                <v-list-item-title class="text-body-2 font-weight-medium">
                  {{ person.displayName }}
                </v-list-item-title>
                <v-list-item-subtitle class="text-caption">
                  <span v-if="person.roomName">{{ person.roomName }}</span>
                  <span v-else class="text-medium-emphasis">Room unknown</span>
                  <template v-if="person.confidence > 0">
                    &nbsp;·&nbsp;{{ Math.round(person.confidence * 100) }}%
                  </template>
                </v-list-item-subtitle>
                <template #append>
                  <div class="d-flex flex-column align-end ga-1">
                    <v-chip
                      :color="person.calibrated ? 'success' : 'warning'"
                      size="x-small"
                      variant="tonal"
                    >
                      {{ person.calibrated ? 'mapped' : 'est.' }}
                    </v-chip>
                    <span class="text-caption text-medium-emphasis">
                      {{ formatAge(person.lastSeen) }}
                    </span>
                  </div>
                </template>
              </v-list-item>
              <v-list-item v-if="activePersons.length === 0" class="text-medium-emphasis text-caption">
                No active identified people
              </v-list-item>
            </v-list>
          </v-card>

          <!-- N4: Inferred presence badges -->
          <v-card v-if="worldInferredRooms.length > 0" class="glass-card mt-3">
            <v-card-title class="text-subtitle-2">Inferred Presence</v-card-title>
            <v-divider />
            <v-card-text class="pa-2">
              <InferredPresenceBadge
                v-for="ir in worldInferredRooms"
                :key="ir.room_id"
                :room-name="ir.room_name"
                :person-name="ir.person_id || ''"
                :since="ir.since"
                @dismiss="() => {}"
              />
            </v-card-text>
          </v-card>

          <!-- Snapshot status -->
          <v-card class="glass-card mt-3">
            <v-card-title class="text-subtitle-2">Snapshot Status</v-card-title>
            <v-divider />
            <v-list density="compact" class="pa-1">
              <v-list-item class="rounded-lg">
                <template #prepend>
                  <v-icon :color="worldStatusColor" size="16">{{ worldStatusIcon }}</v-icon>
                </template>
                <v-list-item-title class="text-caption">{{ worldStatusLabel }}</v-list-item-title>
                <v-list-item-subtitle class="text-caption text-medium-emphasis">
                  {{ worldLastUpdate ? `Updated ${formatAge(worldLastUpdate)}` : 'Waiting for snapshot' }}
                </v-list-item-subtitle>
              </v-list-item>
              <v-list-item class="rounded-lg">
                <template #prepend>
                  <v-icon color="primary" size="16">mdi-account-group</v-icon>
                </template>
                <v-list-item-title class="text-caption">{{ worldPhs.length }} active PH(s)</v-list-item-title>
                <v-list-item-subtitle class="text-caption text-medium-emphasis">
                  {{ worldPhMarkers.length }} on plan · {{ uncalibratedPhCount }} off-plan
                </v-list-item-subtitle>
              </v-list-item>
              <v-list-item class="rounded-lg">
                <template #prepend>
                  <v-icon color="primary" size="16">mdi-door-open</v-icon>
                </template>
                <v-list-item-title class="text-caption">{{ worldInferredRooms.length }} inferred-only room(s)</v-list-item-title>
                <v-list-item-subtitle class="text-caption text-medium-emphasis">
                  {{ worldWsStatusLabel }}
                </v-list-item-subtitle>
              </v-list-item>
            </v-list>
          </v-card>
        </v-col>
      </v-row>
    </template>

    <v-snackbar v-model="snack" :color="snackColor" timeout="3500">{{ snackText }}</v-snackbar>
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, ref, shallowRef, computed, watch } from "vue";
import { useRouter } from "vue-router";
import { identityColor } from "@/composables/useIdentityColor";
import { roomForCanvasPoint } from "@/composables/useFloorPlanProjection";
import { ccToken } from "@/composables/useChartTheme.js";
import { useCanvasZoom } from "@/composables/useCanvasZoom.js";
import { useWorldSnapshot } from "@/composables/useWorldSnapshot";
import { useNotify } from "@/composables/useNotify";
import { household } from "@/services/household";
import { cts } from "@/services/cts";
import CcZoomControls from "@/components/common/CcZoomControls.vue";
import PolygonOnSnapshot from "@/components/cts/PolygonOnSnapshot.vue";
import PHMarker from "@/components/cts/floor/PHMarker.vue";
import InferredPresenceBadge from "@/components/cts/floor/InferredPresenceBadge.vue";

const { snack, snackText, snackColor, notify } = useNotify();
const router = useRouter();

// ── Design-token colors for bespoke spatial renderers (D3) ────────────────
// SVG attributes cannot use CSS custom properties directly; compute them here
// so every stroke/fill reads from the --cc-* token vocabulary instead of
// hardcoded hex values.
const _tokWarning = computed(() => ccToken("--cc-warning"));
const _tokBrand = computed(() => ccToken("--cc-brand"));
const _tokBrandSoft = computed(() => ccToken("--cc-brand-soft"));
const _tokText3 = computed(() => ccToken("--cc-text-3"));

// ── Floor plan state ───────────────────────────────────────────────────────
const floorPlanUrl = ref(null);
const fpWidth = ref(null);
const fpHeight = ref(null);
const fpMpp = ref(null);

// ── Upload state ───────────────────────────────────────────────────────────
const uploading = ref(false);
const uploadFile = ref(null);
const uploadWidth = ref(null);
const uploadHeight = ref(null);
const uploadMpp = ref(null);
// Scale method state
const scaleMethod = ref("pickpoints");
const uploadRealWidth = ref(null);
// Method C: click-on-image scale picker
const scalePoints = ref([]);      // up to 2 normalized [x, y] points
const scaleMeasuredM = ref(null); // real-world distance in metres
const scaleImgEl = ref(null);
const scaleImgRect = ref(null);
let _uploadBlobUrl = null;        // blob URL lifecycle managed manually
let _originalFile = null;         // pre-crop File object, kept for reset
let _resizeObserver = null;       // keeps scaleImgRect current on resize

// ── Zoom for scale picker and crop ─────────────────────────────────────────
const scaleOuterRef = ref(null);
const scaleZoom = useCanvasZoom();
const cropOuterRef = ref(null);
const cropZoom = useCanvasZoom();

// ── Zoom for the live floor plan SVG ───────────────────────────────────────
const liveCanvasRef = ref(null);
const liveZoom = useCanvasZoom({ maxZoom: 5, minZoom: 0.3 });

// Crop state — visual draw-to-crop bounding box on the image.
// cropRect is normalised [0,1] relative to the image content area.
const cropActive = ref(false);
const cropRect = ref({ x: 0.05, y: 0.05, w: 0.90, h: 0.90 });
// cropDrag: { type: 'draw'|'nw'|'ne'|'se'|'sw'|'move', startX, startY, startRect }
const cropDrag = ref(null);
const cropImgRef = ref(null);          // ref for the crop preview <img>
const cropImgRect = ref(null);         // { width, height, offsetX, offsetY } like scaleImgRect

// ── Rooms state ────────────────────────────────────────────────────────────
const rooms = ref([]);
const editingRoom = ref(null);
const editPolygon = ref([]);
const savingRoom = ref(false);

// ── Live view state ────────────────────────────────────────────────────────
const canvasW = ref(1200);
const canvasH = ref(800);

// ── Mode ──────────────────────────────────────────────────────────────────
const mode = ref("live");

// ── Door Zones tab state ───────────────────────────────────────────────────
const doorZones = ref([]);
const doorZonesLoading = ref(false);
const doorZoneCreating = ref(false);
const showDoorZoneDialog = ref(false);
const newDoorZone = ref({
  name: "",
  kind: "door",
  inside_room_id: null,
  outside_room_id: null,
  direction_vec: [1.0, 0.0],
  polygon: [[0.4, 0.45], [0.6, 0.45], [0.6, 0.55], [0.4, 0.55]],
});

async function loadDoorZones() {
  doorZonesLoading.value = true;
  try {
    doorZones.value = await cts.getTransitZones();
  } catch (e) {
    // silently fail; user sees empty state
  } finally {
    doorZonesLoading.value = false;
  }
}

async function createDoorZone() {
  doorZoneCreating.value = true;
  try {
    await cts.createTransitZone({
      name: newDoorZone.value.name,
      kind: newDoorZone.value.kind,
      polygon: newDoorZone.value.polygon,
      inside_room_id: newDoorZone.value.inside_room_id,
      outside_room_id: newDoorZone.value.outside_room_id,
      direction_vec: newDoorZone.value.direction_vec,
    });
    showDoorZoneDialog.value = false;
    newDoorZone.value = {
      name: "",
      kind: "door",
      inside_room_id: null,
      outside_room_id: null,
      direction_vec: [1.0, 0.0],
      polygon: [[0.4, 0.45], [0.6, 0.45], [0.6, 0.55], [0.4, 0.55]],
    };
    await loadDoorZones();
  } catch (e) {
    // error shown by notify
  } finally {
    doorZoneCreating.value = false;
  }
}

async function deleteDoorZone(id) {
  try {
    await cts.deleteTransitZone(id);
    doorZones.value = doorZones.value.filter((z) => z.id !== id);
  } catch (e) {
    // silently fail
  }
}

// Watch mode to lazy-load door zones (watch is imported at the top of <script setup>)
watch(mode, (m) => {
  if (m === "doors") loadDoorZones();
});

// ── Coverage tab state ────────────────────────────────────────────────────
const coverageLoading = ref(false);
const coverageCameras = ref([]);
const coverageImgRef = ref(null);
const coverageImgReady = ref(false);
const coverageImgW = ref(0);
const coverageImgH = ref(0);

// N4: world snapshot (PH-driven floor plan markers)
// WS lifecycle is managed inside useWorldSnapshot.
const {
  phs: worldPhs,
  inferredRooms: worldInferredRooms,
  lastUpdate: worldLastUpdate,
  isStale: worldIsStale,
  wsStatus: worldWsStatus,
} = useWorldSnapshot();

// Compute floor positions for world snapshot PHs
const worldPhMarkers = computed(() => {
  const fp = {
    width: fpWidth.value,
    height: fpHeight.value,
    mpp: fpMpp.value,
    canvasW: canvasW.value,
    canvasH: canvasH.value,
  };
  const floorPlanReady = fp.width && fp.height && fp.mpp;
  if (!floorPlanReady) return [];
  return worldPhs.value
    .filter((ph) => !ph.uncalibrated)
    .map((ph) => {
      const [fx, fy] = ph.floor_xy_m || [0, 0];
      const x = (fx / (fp.width * fp.mpp)) * fp.canvasW;
      const y = (fy / (fp.height * fp.mpp)) * fp.canvasH;
      if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
      return {
        ph,
        x,
        y,
        color: ph.identity_color || identityColor(ph.identity_id || ph.ph_id),
        roomName: ph.room_name || roomForCanvasPoint(x, y, fp.canvasW, fp.canvasH, rooms.value),
      };
    })
    .filter(Boolean);
});

// Uncalibrated PH count for warning chip
const uncalibratedPhCount = computed(() =>
  worldPhs.value.filter((ph) => ph.uncalibrated).length
);

// ── Live floor plan interaction ────────────────────────────────────────────
function onLiveZoomMouseDown(e) {
  liveZoom.actions.startPan(e);
}

function onPhClick(ph) {
  // Suppress navigation if the mousedown was actually a pan drag.
  if (liveZoom.state.didPan) { liveZoom.state.didPan = false; return; }
  router.push({ name: "CTSPeople", query: { ph_id: ph.ph_id || "" } });
}

// ── Smooth marker interpolation ───────────────────────────────────────────
// The backend pushes cts_world_snapshot at ≤5 Hz (200 ms debounce). Without
// interpolation each update causes an instantaneous position jump. A cubic
// ease-out lerp over LERP_MS makes movement look continuous.
//
// Implementation notes:
//   - LERP_MS < update interval so the tween finishes before the next arrives.
//   - On each new snapshot the rAF is cancelled; the in-flight position becomes
//     the new start point, so rapid updates never cause a jump to old coords.
//   - New PHs have no prior position: they snap directly to their first location.
//   - The loop stops itself once t ≥ 1, so idle scenes waste no rAF budget.

const LERP_MS = 160; // ms — safely below the 200 ms backend debounce

// ph_id → { x0, y0, x1, y1 } (start and target in SVG user units)
const _interpState = new Map();
const smoothedMarkers = shallowRef([]);
let _rafId = null;
let _animStart = 0;
let _animTargets = /** @type {typeof worldPhMarkers.value | null} */ (null);

function _cubicEaseOut(t) { return 1 - (1 - t) ** 3; }

function _lerp(now) {
  const t = Math.min(1, (now - _animStart) / LERP_MS);
  const e = _cubicEaseOut(t);

  smoothedMarkers.value = (_animTargets ?? []).map((m) => {
    const id = m.ph.ph_id ?? m.ph.identity_id;
    const s = _interpState.get(id);
    if (!s || (s.x0 === s.x1 && s.y0 === s.y1)) return m;
    const x = s.x0 + (s.x1 - s.x0) * e;
    const y = s.y0 + (s.y1 - s.y0) * e;
    if (t >= 1) _interpState.set(id, { x0: x, y0: y, x1: x, y1: y });
    return { ...m, x, y };
  });

  if (t < 1) {
    _rafId = requestAnimationFrame(_lerp);
  } else {
    _rafId = null;
    _animTargets = null;
  }
}

watch(worldPhMarkers, (newMarkers) => {
  if (_rafId !== null) {
    cancelAnimationFrame(_rafId);
    _rafId = null;
  }

  // Capture current in-flight positions as the new start so we never jump.
  for (const m of newMarkers) {
    const id = m.ph.ph_id ?? m.ph.identity_id;
    const prev = _interpState.get(id);
    // If no previous: snap (x0 === x1 — no lerp needed, _lerp returns m directly).
    _interpState.set(id, {
      x0: prev ? smoothedMarkers.value.find(s => (s.ph.ph_id ?? s.ph.identity_id) === id)?.x ?? m.x : m.x,
      y0: prev ? smoothedMarkers.value.find(s => (s.ph.ph_id ?? s.ph.identity_id) === id)?.y ?? m.y : m.y,
      x1: m.x,
      y1: m.y,
    });
  }

  // Remove state for PHs that have left the scene.
  const activeIds = new Set(newMarkers.map(m => m.ph.ph_id ?? m.ph.identity_id));
  for (const id of _interpState.keys()) {
    if (!activeIds.has(id)) _interpState.delete(id);
  }

  _animTargets = newMarkers;
  _animStart = performance.now();
  _rafId = requestAnimationFrame(_lerp);
}, { immediate: true });

// ── Computed ──────────────────────────────────────────────────────────────
const worldMarkerByPhId = computed(() => {
  const byId = new Map();
  for (const marker of worldPhMarkers.value) {
    if (marker.ph?.ph_id) byId.set(marker.ph.ph_id, marker);
  }
  return byId;
});

const activePersons = computed(() => {
  return worldPhs.value
    .filter((ph) => ph.identity_id && ph.last_observed_at)
    .map((ph) => ({
      gtId: ph.ph_id,
      displayName: ph.identity_display_name || ph.identity_id || "UNKNOWN",
      color: ph.identity_color || "#888888",
      calibrated: !ph.uncalibrated,
      confidence: ph.posterior_top_prob ?? 0,
      lastSeen: new Date(ph.last_observed_at).getTime(),
      roomName: ph.room_name || worldMarkerByPhId.value.get(ph.ph_id)?.roomName || null,
    }))
    .sort((a, b) => b.lastSeen - a.lastSeen);
});

const worldStatusLabel = computed(() => {
  if (worldWsStatus.value === "connecting") return "Connecting";
  if (worldWsStatus.value === "error" || worldWsStatus.value === "closed") return "Disconnected";
  return worldIsStale.value ? "Stale" : "Live";
});

const worldStatusColor = computed(() => {
  if (worldWsStatus.value === "error" || worldWsStatus.value === "closed") return "error";
  if (worldWsStatus.value === "connecting" || worldIsStale.value) return "warning";
  return "success";
});

const worldStatusIcon = computed(() => {
  if (worldWsStatus.value === "error" || worldWsStatus.value === "closed") return "mdi-wifi-off";
  if (worldWsStatus.value === "connecting") return "mdi-wifi-strength-1";
  return worldIsStale.value ? "mdi-clock-alert-outline" : "mdi-broadcast";
});

const worldWsStatusLabel = computed(() => {
  switch (worldWsStatus.value) {
    case "open":
      return "WebSocket connected";
    case "connecting":
      return "WebSocket connecting";
    case "error":
      return "WebSocket error";
    case "closed":
      return "WebSocket reconnecting";
    default:
      return "WebSocket disconnected";
  }
});

const uncalibratedCoverage = computed(() =>
  coverageCameras.value.filter((c) => !c.visibility_polygon)
);

// ── Coverage tab functions ─────────────────────────────────────────────────
function onCoverageImgLoad() {
  if (!coverageImgRef.value) return;
  coverageImgW.value = coverageImgRef.value.naturalWidth;
  coverageImgH.value = coverageImgRef.value.naturalHeight;
  coverageImgReady.value = true;
}

async function loadCoverage() {
  coverageLoading.value = true;
  try {
    const data = await cts.getVisibilityPolygons();
    coverageCameras.value = data.cameras || [];
  } catch (e) {
    notify(e.message, "error");
  } finally {
    coverageLoading.value = false;
  }
}

function toCoverageSvgPoints(polygon) {
  if (!coverageImgW.value || !coverageImgH.value) return "";
  return polygon
    .map(([x, y]) => `${(x * coverageImgW.value).toFixed(1)},${(y * coverageImgH.value).toFixed(1)}`)
    .join(" ");
}

function coverageCentroid(polygon) {
  if (!polygon || !polygon.length) return [0, 0];
  const sumX = polygon.reduce((s, [x]) => s + x, 0);
  const sumY = polygon.reduce((s, [, y]) => s + y, 0);
  return [
    (sumX / polygon.length) * coverageImgW.value,
    (sumY / polygon.length) * coverageImgH.value,
  ];
}

watch(
  () => mode.value,
  (newMode) => {
    if (newMode === "coverage" && coverageCameras.value.length === 0) {
      loadCoverage();
    }
  }
);

// ── Helpers ───────────────────────────────────────────────────────────────
function centroidX(polygon) {
  return polygon.reduce((s, [x]) => s + x, 0) / polygon.length;
}
function centroidY(polygon) {
  return polygon.reduce((s, [, y]) => s + y, 0) / polygon.length;
}

function formatAge(ts) {
  if (!ts) return "";
  const s = Math.round((Date.now() - ts) / 1000);
  if (s < 5) return "now";
  if (s < 60) return `${s}s ago`;
  return `${Math.round(s / 60)}m ago`;
}

// ── Load ─────────────────────────────────────────────────────────────────
async function loadFloorPlan() {
  try {
    const data = await household.getFloorPlan();
    floorPlanUrl.value = data.floor_plan_url;
    fpWidth.value = data.floor_plan_width;
    fpHeight.value = data.floor_plan_height;
    fpMpp.value = data.floor_meters_per_pixel;
    if (data.floor_plan_width && data.floor_plan_height) {
      canvasW.value = data.floor_plan_width;
      canvasH.value = data.floor_plan_height;
    }
  } catch {
    // Not configured yet — not an error.
  }
}

async function loadRooms() {
  try {
    rooms.value = await household.getRooms();
  } catch (e) {
    notify(e.message, "error");
  }
}

// ── Scale picker computed ─────────────────────────────────────────────────
// URL shown in the Method C image picker: prefer the newly selected file,
// fall back to the already-saved floor plan.
const scalePickerImageUrl = computed(() => _uploadBlobUrl || floorPlanUrl.value);

// Pixel distance between the two scale points, measured in original image pixels.
const scalePixelDistance = computed(() => {
  if (scalePoints.value.length < 2) return 0;
  const w = uploadWidth.value || fpWidth.value || (scaleImgEl.value?.naturalWidth ?? 0);
  const h = uploadHeight.value || fpHeight.value || (scaleImgEl.value?.naturalHeight ?? 0);
  if (!w || !h) return 0;
  const [p1, p2] = scalePoints.value;
  const dx = (p2[0] - p1[0]) * w;
  const dy = (p2[1] - p1[1]) * h;
  return Math.sqrt(dx * dx + dy * dy);
});

// Computed mpp from Method C.
const scaleComputedMpp = computed(() => {
  if (!scaleMeasuredM.value || scalePixelDistance.value < 1) return null;
  return (scaleMeasuredM.value / scalePixelDistance.value).toFixed(6);
});

// ── Upload helpers ────────────────────────────────────────────────────────
function onFileSelected(fileOrArray) {
  const file = Array.isArray(fileOrArray) ? fileOrArray[0] : fileOrArray;
  // Revoke previous blob URL.
  if (_uploadBlobUrl) { URL.revokeObjectURL(_uploadBlobUrl); _uploadBlobUrl = null; }
  // Reset state for the new image.
  scalePoints.value = [];
  scaleMeasuredM.value = null;
  scaleImgRect.value = null;
  cropActive.value = false;
  cropRect.value = { x: 0.05, y: 0.05, w: 0.90, h: 0.90 };
  if (!file) return;

  _originalFile = file;
  _uploadBlobUrl = URL.createObjectURL(file);
  // Read natural dimensions without a visible img element.
  const probe = new Image();
  probe.onload = () => {
    uploadWidth.value = probe.naturalWidth;
    uploadHeight.value = probe.naturalHeight;
    // Recompute mpp if real width was already set.
    if (uploadRealWidth.value && probe.naturalWidth) {
      uploadMpp.value = parseFloat((uploadRealWidth.value / probe.naturalWidth).toFixed(6));
    }
  };
  probe.src = _uploadBlobUrl;
}

function onScaleImageLoad() {
  if (!scaleImgEl.value) return;
  // Use offset* (pre-transform layout) so zoom/pan don't distort the overlay.
  const elW = scaleImgEl.value.offsetWidth;
  const elH = scaleImgEl.value.offsetHeight;
  const elLeft = scaleImgEl.value.offsetLeft;
  const elTop = scaleImgEl.value.offsetTop;
  const nw = uploadWidth.value || scaleImgEl.value.naturalWidth;
  const nh = uploadHeight.value || scaleImgEl.value.naturalHeight;
  // Populate upload fields from saved data when no file was selected.
  if (!uploadWidth.value && nw) uploadWidth.value = nw;
  if (!uploadHeight.value && nh) uploadHeight.value = nh;
  if (!uploadMpp.value && fpMpp.value) uploadMpp.value = fpMpp.value;
  if (!nw || !nh || !elW || !elH) {
    scaleImgRect.value = { width: elW, height: elH, offsetX: elLeft, offsetY: elTop };
    return;
  }
  // Compute the actual image content rect within the element accounting for
  // object-fit: contain letterboxing. Normalised scale-point coordinates and
  // the SVG overlay must use content-relative values so they align with what
  // the user actually sees.
  const imgAspect = nw / nh;
  const elAspect = elW / elH;
  let cw, ch, ox, oy;
  if (imgAspect > elAspect) {
    // image wider than element → letterbox top/bottom
    cw = elW;
    ch = elW / imgAspect;
    ox = 0;
    oy = (elH - ch) / 2;
  } else {
    // image taller than element → letterbox left/right
    ch = elH;
    cw = elH * imgAspect;
    ox = (elW - cw) / 2;
    oy = 0;
  }
  scaleImgRect.value = { width: cw, height: ch, offsetX: elLeft + ox, offsetY: elTop + oy };

  // Keep content rect current when the container resizes.
  if (!_resizeObserver) {
    _resizeObserver = new ResizeObserver(() => onScaleImageLoad());
    _resizeObserver.observe(scaleImgEl.value);
  }
}

function onScaleImageClick(e) {
  if (scalePoints.value.length >= 2 || !scaleImgEl.value) return;
  // Ignore when the user was panning (drag exceeded threshold).
  if (scaleZoom.state.didPan) { scaleZoom.state.didPan = false; return; }
  if (!scaleImgRect.value || !scaleOuterRef.value) return;
  const cr = scaleImgRect.value;
  const outerRect = scaleOuterRef.value.getBoundingClientRect();
  // Map through zoom/pan to get coordinates in the pre-transform space.
  const local = scaleZoom.containerToLocal(
    e.clientX - outerRect.left,
    e.clientY - outerRect.top,
  );
  // Then normalise to [0,1] within the image content area.
  const x = (local.x - cr.offsetX) / cr.width;
  const y = (local.y - cr.offsetY) / cr.height;
  if (x < 0 || x > 1 || y < 0 || y > 1) return;
  scalePoints.value = [...scalePoints.value, [parseFloat(x.toFixed(4)), parseFloat(y.toFixed(4))]];
}

/** Start a potential pan on mousedown of the scale picker inner area. */
function onScalePickerMouseDown(e) {
  scaleZoom.actions.startPan(e);
}

function onScaleMeasuredChange() {
  if (scaleComputedMpp.value) {
    uploadMpp.value = parseFloat(scaleComputedMpp.value);
  }
}

function onRealWidthChange() {
  if (uploadRealWidth.value && uploadWidth.value) {
    uploadMpp.value = parseFloat((uploadRealWidth.value / uploadWidth.value).toFixed(6));
  }
}



// ── Crop ──────────────────────────────────────────────────────────────────

/** Corner handle positions (normalised) for the crop rectangle. */
const cropHandles = computed(() => {
  const r = cropRect.value;
  return [
    { corner: 'nw', x: r.x,       y: r.y,       cursor: 'nwse-resize' },
    { corner: 'ne', x: r.x + r.w, y: r.y,       cursor: 'nesw-resize' },
    { corner: 'se', x: r.x + r.w, y: r.y + r.h, cursor: 'nwse-resize' },
    { corner: 'sw', x: r.x,       y: r.y + r.h, cursor: 'nesw-resize' },
  ];
});

function onCropImgLoad() {
  if (!cropImgRef.value) return;
  const img = cropImgRef.value;
  // Use offset* (pre-transform layout) so zoom doesn't distort the overlay.
  const elW = img.offsetWidth;
  const elH = img.offsetHeight;
  const elLeft = img.offsetLeft;
  const elTop = img.offsetTop;
  const nw = img.naturalWidth;
  const nh = img.naturalHeight;
  if (!nw || !nh || !elW || !elH) return;
  const naturalRatio = nw / nh;
  const elRatio = elW / elH;
  let cw, ch, offX, offY;
  if (naturalRatio > elRatio) {
    cw = elW; ch = elW / naturalRatio;
    offX = 0; offY = (elH - ch) / 2;
  } else {
    ch = elH; cw = elH * naturalRatio;
    offX = (elW - cw) / 2; offY = 0;
  }
  cropImgRect.value = { width: cw, height: ch, offsetX: elLeft + offX, offsetY: elTop + offY };
}

function startCropMode() {
  cropRect.value = { x: 0.05, y: 0.05, w: 0.90, h: 0.90 };
  cropActive.value = true;
}

function resetCrop() {
  cropRect.value = { x: 0.05, y: 0.05, w: 0.90, h: 0.90 };
}

/** Convert a mouse event on the crop container to normalised [0,1] coords. */
function cropEventToNorm(e) {
  if (!cropImgRef.value || !cropImgRect.value || !cropOuterRef.value) return null;
  const cr = cropImgRect.value;
  const outerRect = cropOuterRef.value.getBoundingClientRect();
  // Map through zoom to get coordinates in the pre-transform space.
  const local = cropZoom.containerToLocal(
    e.clientX - outerRect.left,
    e.clientY - outerRect.top,
  );
  const nx = (local.x - cr.offsetX) / cr.width;
  const ny = (local.y - cr.offsetY) / cr.height;
  if (nx < 0 || nx > 1 || ny < 0 || ny > 1) return null;
  return { x: nx, y: ny };
}

/** Start drawing a new crop rectangle from scratch, or pan when outside the image. */
function onCropMouseDown(e) {
  if (!cropActive.value) return;
  const pt = cropEventToNorm(e);
  if (!pt) {
    // Click is in the letterbox area outside the image — pan instead of draw.
    cropZoom.actions.startPan(e);
    return;
  }
  cropDrag.value = { type: 'draw', startX: pt.x, startY: pt.y, startRect: { ...cropRect.value } };
  window.addEventListener('mousemove', onCropMouseMove);
  window.addEventListener('mouseup', onCropMouseUp);
  e.preventDefault();
}

/** Start dragging a corner handle. */
function onCropHandleDown(corner, e) {
  const pt = cropEventToNorm(e);
  if (!pt) return;
  cropDrag.value = { type: corner, startX: pt.x, startY: pt.y, startRect: { ...cropRect.value } };
  window.addEventListener('mousemove', onCropMouseMove);
  window.addEventListener('mouseup', onCropMouseUp);
}

function onCropMouseMove(e) {
  if (!cropDrag.value || !cropImgRef.value || !cropImgRect.value) return;
  const pt = cropEventToNorm(e);
  if (!pt) return;
  const d = cropDrag.value;
  const dx = pt.x - d.startX;
  const dy = pt.y - d.startY;
  const sr = d.startRect;

  let nx = sr.x, ny = sr.y, nw = sr.w, nh = sr.h;

  if (d.type === 'draw') {
    // Drag to define a new rectangle.
    nx = Math.min(d.startX, pt.x);
    ny = Math.min(d.startY, pt.y);
    nw = Math.abs(pt.x - d.startX);
    nh = Math.abs(pt.y - d.startY);
  } else if (d.type === 'move') {
    nx = Math.max(0, Math.min(1 - sr.w, sr.x + dx));
    ny = Math.max(0, Math.min(1 - sr.h, sr.y + dy));
  } else {
    // Corner resize — adjust whichever edges the corner controls.
    if (d.type.includes('n')) { ny = Math.min(sr.y + sr.h - 0.01, sr.y + dy); nh = sr.y + sr.h - ny; }
    if (d.type.includes('s')) { nh = Math.max(0.01, sr.h + dy); }
    if (d.type.includes('w')) { nx = Math.min(sr.x + sr.w - 0.01, sr.x + dx); nw = sr.x + sr.w - nx; }
    if (d.type.includes('e')) { nw = Math.max(0.01, sr.w + dx); }
    // Clamp to image bounds.
    nx = Math.max(0, nx); ny = Math.max(0, ny);
    nw = Math.min(1 - nx, nw); nh = Math.min(1 - ny, nh);
  }

  // Enforce minimum size.
  const minPx = 10;
  const pw = uploadWidth.value || 1448;
  const ph = uploadHeight.value || 1086;
  if (nw * pw < minPx) nw = minPx / pw;
  if (nh * ph < minPx) nh = minPx / ph;

  cropRect.value = { x: nx, y: ny, w: nw, h: nh };
}

function onCropMouseUp() {
  cropDrag.value = null;
  window.removeEventListener('mousemove', onCropMouseMove);
  window.removeEventListener('mouseup', onCropMouseUp);
}

async function applyCrop() {
  if (!_originalFile || !uploadWidth.value || !uploadHeight.value) return;

  const r = cropRect.value;
  const x = Math.round(uploadWidth.value * r.x);
  const y = Math.round(uploadHeight.value * r.y);
  const w = Math.round(uploadWidth.value * r.w);
  const h = Math.round(uploadHeight.value * r.h);
  if (w < 10 || h < 10) return;

  // Canvas-crop the image.
  const img = await new Promise((resolve, reject) => {
    const el = new Image();
    el.onload = () => resolve(el);
    el.onerror = reject;
    el.src = _uploadBlobUrl;
  });

  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(img, x, y, w, h, 0, 0, w, h);

  const croppedBlob = await new Promise((resolve) =>
    canvas.toBlob(resolve, _originalFile.type, 0.95)
  );

  const croppedFile = new File([croppedBlob], _originalFile.name, { type: _originalFile.type });
  uploadFile.value = croppedFile;
  if (_uploadBlobUrl) URL.revokeObjectURL(_uploadBlobUrl);
  _uploadBlobUrl = URL.createObjectURL(croppedBlob);
  uploadWidth.value = w;
  uploadHeight.value = h;

  cropActive.value = false;
  cropImgRect.value = null;
  scalePoints.value = [];
  scaleMeasuredM.value = null;
  scaleImgRect.value = null;
}

// ── Upload ────────────────────────────────────────────────────────────────
async function uploadFloorPlan() {
  uploading.value = true;
  try {
    const fd = new FormData();
    if (uploadFile.value) fd.append("file", uploadFile.value[0] ?? uploadFile.value);
    if (uploadWidth.value) fd.append("floor_plan_width", String(uploadWidth.value));
    if (uploadHeight.value) fd.append("floor_plan_height", String(uploadHeight.value));
    if (uploadMpp.value) fd.append("floor_meters_per_pixel", String(uploadMpp.value));
    const data = await household.postFloorPlan(fd);
    floorPlanUrl.value = data.floor_plan_url;
    fpWidth.value = data.floor_plan_width;
    fpHeight.value = data.floor_plan_height;
    fpMpp.value = data.floor_meters_per_pixel;
    if (data.floor_plan_width && data.floor_plan_height) {
      canvasW.value = data.floor_plan_width;
      canvasH.value = data.floor_plan_height;
    }
    notify("Floor plan saved");
    uploadFile.value = null;
  } catch (e) {
    notify(e.message, "error");
  } finally {
    uploading.value = false;
  }
}

// ── Edit rooms ────────────────────────────────────────────────────────────
function selectRoom(room) {
  editingRoom.value = room;
  editPolygon.value = room.floor_polygon ? JSON.parse(JSON.stringify(room.floor_polygon)) : [];
}

async function saveRoomPolygon() {
  if (!editingRoom.value) return;
  // Allow 0 points (delete polygon) or 3+ points (valid polygon), not 1-2.
  if (editPolygon.value.length > 0 && editPolygon.value.length < 3) return;
  savingRoom.value = true;
  const isDelete = editPolygon.value.length === 0;
  try {
    const updated = await household.putRoom(editingRoom.value.id, {
      ...editingRoom.value,
      floor_polygon: isDelete ? null : editPolygon.value,
    });
    const idx = rooms.value.findIndex((r) => r.id === updated.id);
    if (idx >= 0) rooms.value[idx] = updated;
    editingRoom.value = updated;
    notify(isDelete ? "Room polygon removed" : "Room polygon saved");
  } catch (e) {
    notify(e.message, "error");
  } finally {
    savingRoom.value = false;
  }
}

onMounted(() => {
  loadFloorPlan();
  loadRooms();
  // WS lifecycle is handled inside useWorldSnapshot.
});

onBeforeUnmount(() => {
  if (_uploadBlobUrl) { URL.revokeObjectURL(_uploadBlobUrl); _uploadBlobUrl = null; }
  if (_resizeObserver) { _resizeObserver.disconnect(); _resizeObserver = null; }
  if (_rafId !== null) { cancelAnimationFrame(_rafId); _rafId = null; }
});
</script>

<style scoped>
.floor-plan-canvas {
  position: relative;     /* anchor for CcZoomControls (absolute, bottom-right) */
  overflow: hidden;       /* clip the zoomed/panned content */
  background: var(--cc-surface-2);
  border: 1px solid var(--cc-divider-strong);
  border-radius: 8px;
  /* aspect-ratio is set via :style from canvasW/canvasH; max-height keeps
     very tall floor plans from pushing content off screen. */
  min-height: 300px;
}

/* Receives the useCanvasZoom CSS transform. fill parent fully so the
   transform scales from the correct origin. */
.floor-plan-zoom-content {
  width: 100%;
  height: 100%;
  transform-origin: 0 0;
  will-change: transform;
}

.floor-plan-svg {
  display: block;
  width: 100%;
  height: 100%;
}

.floor-plan-preview {
  display: block;
  max-width: 100%;
  max-height: 400px;
  border-radius: 4px;
  object-fit: contain;
}

.room-poly {
  fill: rgba(99, 102, 241, 0.12);
  stroke: var(--cc-brand);
  stroke-width: 1.5;
  stroke-dasharray: 6 4;
}

.room-label {
  fill: var(--cc-brand);
  font-size: 11px;
  font-weight: 600;
  text-anchor: middle;
  dominant-baseline: central;
  pointer-events: none;
}

.identity-label {
  pointer-events: none;
}

.person-card {
  background: var(--cc-surface-2);
  padding: 6px 8px !important;
}

.person-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
  border: 2px solid white;
}

/* ── Scale picker zoom ─────────────────────────────────────────────── */
.scale-picker-outer {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--cc-divider-strong, rgba(0,0,0,0.12));
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
  background: var(--cc-surface-2, rgba(0,0,0,0.03));
}

.scale-picker-overlay {
  position: absolute;
  pointer-events: none;
}

/* ── Crop zoom ─────────────────────────────────────────────────────── */
.crop-outer {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--cc-divider-strong, rgba(0,0,0,0.12));
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

/* Zoom controls rendered by CcZoomControls using global .cc-zoom-controls */

.cursor-crosshair {
  cursor: crosshair;
}
/* Corner handles receive pointer events so they're draggable. */
.crop-svg-overlay .crop-handle {
  pointer-events: auto;
}

.coverage-canvas-wrap {
  position: relative;
  overflow: hidden;
  background: var(--cc-surface-2);
  min-height: 300px;
}

.coverage-fp-img {
  display: block;
  width: 100%;
  height: auto;
}

.coverage-svg-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.coverage-empty {
  min-height: 300px;
}

.coverage-legend-swatch {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid;
  border-radius: 3px;
  vertical-align: middle;
}
</style>
