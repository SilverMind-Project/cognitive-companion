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
      </div>
      <v-btn
        v-if="mode === 'live'"
        class="ml-2"
        :icon="paused ? 'mdi-play' : 'mdi-pause'"
        variant="text"
        @click="paused = !paused"
      />
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
                  stroke="#ff9800"
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
                  stroke="#ff9800"
                  stroke-width="2"
                  :style="{ cursor: handle.cursor }"
                  @mousedown.stop="onCropHandleDown(handle.corner, $event)"
                />
              </svg>
              <div v-if="!cropImgRect" class="d-flex align-center justify-center pa-8">
                <span class="text-body-2 text-medium-emphasis">Loading image...</span>
              </div>
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

            <!-- Image picker area -->
            <div
              class="scale-picker-container mb-2"
              :class="scalePoints.length < 2 ? 'cursor-crosshair' : ''"
              @click="onScaleImageClick"
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
                :value="room.id"
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
                :disabled="editPolygon.length > 0 && editPolygon.length < 3"
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
            <span class="coverage-legend-swatch" style="border-color:#2196f3;background:rgba(33,150,243,0.18)" />
            Calibrated
          </span>
          <span class="d-flex align-center ga-1">
            <span class="coverage-legend-swatch" style="border-color:#9e9e9e;background:rgba(200,200,200,0.1);border-style:dotted" />
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
                  fill="rgba(33,150,243,0.18)"
                  stroke="#2196f3"
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

    <!-- ── Live view ─────────────────────────────────────────────────────── -->
    <template v-else>
      <v-row>
        <!-- Floor plan SVG -->
        <v-col cols="12" :md="activePersons.length > 0 ? 9 : 12">
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
                v-if="uncalibratedWarning"
                color="warning"
                size="small"
                variant="tonal"
                prepend-icon="mdi-crosshairs-off"
                class="mr-2"
                @click="router.push({ name: 'CTSCalibration' })"
              >
                {{ uncalibratedDetCount }} unmapped detections (calibrate cameras to show)
              </v-chip>
              <v-chip
                :color="paused ? 'warning' : 'success'"
                size="small"
                variant="tonal"
              >
                <v-icon start size="14">{{ paused ? 'mdi-pause' : 'mdi-broadcast' }}</v-icon>
                {{ paused ? 'Paused' : 'Live' }}
              </v-chip>
            </v-card-title>
            <v-divider />
            <v-card-text class="pa-2">
              <div ref="canvasContainer" class="floor-plan-canvas">
                <svg
                  ref="svgEl"
                  :viewBox="`0 0 ${canvasW} ${canvasH}`"
                  preserveAspectRatio="xMidYMid meet"
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

                  <!-- Identity trails and dots -->
                  <g v-for="(trail, gtId) in identityTrails" :key="gtId">
                    <polyline
                      v-if="trail.points.length > 1"
                      :points="trail.points.map(p => `${p.x},${p.y}`).join(' ')"
                      :stroke="trail.color"
                      stroke-width="2.5"
                      fill="none"
                      :opacity="trail.calibrated ? 0.55 : 0.3"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      :stroke-dasharray="trail.calibrated ? 'none' : '8 4'"
                    />
                    <g v-if="trail.current">
                      <!-- Outer ring: solid = calibrated, dashed = estimated -->
                      <circle
                        :cx="trail.current.x"
                        :cy="trail.current.y"
                        r="12"
                        :fill="trail.color"
                        fill-opacity="0.18"
                        :stroke="trail.color"
                        stroke-width="1.5"
                        :stroke-dasharray="trail.calibrated ? 'none' : '5 3'"
                      />
                      <!-- Inner dot -->
                      <circle
                        :cx="trail.current.x"
                        :cy="trail.current.y"
                        r="6"
                        :fill="trail.color"
                        stroke="#fff"
                        stroke-width="2"
                      />
                    </g>
                    <text
                      v-if="trail.current"
                      :x="trail.current.x + 14"
                      :y="trail.current.y - 10"
                      :fill="trail.color"
                      font-size="13"
                      font-weight="bold"
                      class="identity-label"
                    >
                      {{ trail.displayName }}
                    </text>
                    <text
                      v-if="trail.current && !trail.calibrated"
                      :x="trail.current.x + 14"
                      :y="trail.current.y + 4"
                      fill="#999"
                      font-size="10"
                      class="identity-label"
                    >
                      est.
                    </text>
                  </g>

                  <!-- Empty state -->
                  <text
                    v-if="Object.keys(identityTrails).length === 0"
                    x="50%"
                    y="50%"
                    text-anchor="middle"
                    fill="#888"
                    font-size="16"
                  >
                    No active tracks. Waiting for live data…
                  </text>
                </svg>
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
        <v-col v-if="activePersons.length > 0" cols="12" md="3">
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
            </v-list>
          </v-card>

          <!-- Calibration status per camera -->
          <v-card class="glass-card mt-3">
            <v-card-title class="text-subtitle-2">Camera Status</v-card-title>
            <v-divider />
            <v-list density="compact" class="pa-1">
              <v-list-item
                v-for="cam in activeCameras"
                :key="cam.id"
                class="rounded-lg"
              >
                <template #prepend>
                  <v-icon
                    :color="cam.calibrated ? 'success' : 'warning'"
                    size="16"
                  >
                    {{ cam.calibrated ? 'mdi-crosshairs-gps' : 'mdi-crosshairs-off' }}
                  </v-icon>
                </template>
                <v-list-item-title class="text-caption">{{ cam.id }}</v-list-item-title>
                <v-list-item-subtitle class="text-caption text-medium-emphasis">
                  {{ cam.detections }} det. · {{ cam.calibrated ? 'calibrated' : 'no homography' }}
                </v-list-item-subtitle>
              </v-list-item>
              <v-list-item v-if="activeCameras.length === 0" class="text-medium-emphasis text-caption">
                No cameras reporting
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
import { projectDetectionToCanvas, trailKeyFor, roomForCanvasPoint } from "@/composables/useFloorPlanProjection";
import { useCtsWebSocket } from "@/composables/useCtsWebSocket";
import { useNotify } from "@/composables/useNotify";
import { household } from "@/services/household";
import { cts } from "@/services/cts";
import PolygonOnSnapshot from "@/components/cts/PolygonOnSnapshot.vue";

const { snack, snackText, snackColor, notify } = useNotify();
const router = useRouter();

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
const paused = ref(false);
const identityTrails = shallowRef({});
const uncalibratedDetCount = ref(0);
let _uncalibratedWindow = [];
// cameraFrameState tracks the most recent frame per camera for status display
const cameraFrameState = shallowRef({});
const MAX_TRAIL_POINTS = 80;
const TRAIL_MAX_AGE_MS = 30_000;
const CAMERA_STALE_MS = 10_000;

// ── Mode ──────────────────────────────────────────────────────────────────
const mode = ref("live");

// ── Coverage tab state ────────────────────────────────────────────────────
const coverageLoading = ref(false);
const coverageCameras = ref([]);
const coverageImgRef = ref(null);
const coverageImgReady = ref(false);
const coverageImgW = ref(0);
const coverageImgH = ref(0);

// ── WS ───────────────────────────────────────────────────────────────────
function onWsMessage(msg) {
  if (msg?.type === "cts_live_frame") onLiveFrame(msg);
}
useCtsWebSocket(onWsMessage);

// ── Computed ──────────────────────────────────────────────────────────────
const activePersons = computed(() => {
  const now = Date.now();
  return Object.entries(identityTrails.value)
    .filter(([, t]) => now - (t.lastSeen ?? 0) < TRAIL_MAX_AGE_MS)
    .map(([gtId, t]) => ({
      gtId,
      displayName: t.displayName,
      color: t.color,
      calibrated: t.calibrated,
      confidence: t.confidence ?? 0,
      lastSeen: t.lastSeen,
      roomName: t.roomName ?? null,
    }))
    .sort((a, b) => b.lastSeen - a.lastSeen);
});

const activeCameras = computed(() => {
  const now = Date.now();
  return Object.entries(cameraFrameState.value)
    .filter(([, s]) => now - s.lastSeen < CAMERA_STALE_MS)
    .map(([id, s]) => ({ id, calibrated: s.calibrated, detections: s.detections }))
    .sort((a, b) => a.id.localeCompare(b.id));
});

const uncalibratedWarning = computed(() =>
  uncalibratedDetCount.value > 0
);

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
  const r = scaleImgEl.value.getBoundingClientRect();
  const nw = uploadWidth.value || scaleImgEl.value.naturalWidth;
  const nh = uploadHeight.value || scaleImgEl.value.naturalHeight;
  // Populate upload fields from saved data when no file was selected.
  if (!uploadWidth.value && nw) uploadWidth.value = nw;
  if (!uploadHeight.value && nh) uploadHeight.value = nh;
  if (!uploadMpp.value && fpMpp.value) uploadMpp.value = fpMpp.value;
  if (!nw || !nh) {
    scaleImgRect.value = { width: r.width, height: r.height, offsetX: 0, offsetY: 0 };
    return;
  }
  // Compute the actual image content rect within the element accounting for
  // object-fit: contain letterboxing. Normalised scale-point coordinates and
  // the SVG overlay must use content-relative values so they align with what
  // the user actually sees.
  const imgAspect = nw / nh;
  const elAspect = r.width / r.height;
  let cw, ch, ox, oy;
  if (imgAspect > elAspect) {
    // image wider than element → letterbox top/bottom
    cw = r.width;
    ch = r.width / imgAspect;
    ox = 0;
    oy = (r.height - ch) / 2;
  } else {
    // image taller than element → letterbox left/right
    ch = r.height;
    cw = r.height * imgAspect;
    ox = (r.width - cw) / 2;
    oy = 0;
  }
  scaleImgRect.value = { width: cw, height: ch, offsetX: ox, offsetY: oy };

  // Keep content rect current when the container resizes.
  if (!_resizeObserver) {
    _resizeObserver = new ResizeObserver(() => onScaleImageLoad());
    _resizeObserver.observe(scaleImgEl.value);
  }
}

function onScaleImageClick(e) {
  if (scalePoints.value.length >= 2 || !scaleImgEl.value) return;
  if (!scaleImgRect.value) return;
  const cr = scaleImgRect.value;
  const r = scaleImgEl.value.getBoundingClientRect();
  // Map click to content-relative normalised coordinates so points
  // align with the visible image regardless of object-fit letterboxing.
  const x = (e.clientX - r.left - cr.offsetX) / cr.width;
  const y = (e.clientY - r.top - cr.offsetY) / cr.height;
  if (x < 0 || x > 1 || y < 0 || y > 1) return;
  scalePoints.value = [...scalePoints.value, [parseFloat(x.toFixed(4)), parseFloat(y.toFixed(4))]];
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
  const r = img.getBoundingClientRect();
  const nw = img.naturalWidth;
  const nh = img.naturalHeight;
  if (!nw || !nh) return;
  const naturalRatio = nw / nh;
  const elRatio = r.width / r.height;
  let cw, ch, offX, offY;
  if (naturalRatio > elRatio) {
    cw = r.width; ch = r.width / naturalRatio;
    offX = 0; offY = (r.height - ch) / 2;
  } else {
    ch = r.height; cw = r.height * naturalRatio;
    offX = (r.width - cw) / 2; offY = 0;
  }
  cropImgRect.value = { width: cw, height: ch, offsetX: offX, offsetY: offY };
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
  if (!cropImgRef.value || !cropImgRect.value) return null;
  const r = cropImgRef.value.getBoundingClientRect();
  const cr = cropImgRect.value;
  const nx = (e.clientX - r.left - cr.offsetX) / cr.width;
  const ny = (e.clientY - r.top - cr.offsetY) / cr.height;
  if (nx < 0 || nx > 1 || ny < 0 || ny > 1) return null;
  return { x: nx, y: ny };
}

/** Start drawing a new crop rectangle from scratch. */
function onCropMouseDown(e) {
  if (!cropActive.value) return;
  const pt = cropEventToNorm(e);
  if (!pt) return;
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

// ── Live frame handler ────────────────────────────────────────────────────
function onLiveFrame(frame) {
  if (paused.value) return;

  const detections = frame.detections || [];
  const now = Date.now();
  const fp = {
    width: fpWidth.value,
    height: fpHeight.value,
    mpp: fpMpp.value,
    canvasW: canvasW.value,
    canvasH: canvasH.value,
  };
  const floorPlanReady = fp.width && fp.height && fp.mpp;

  const trails = { ...identityTrails.value };

  // Expire stale trails.
  for (const id of Object.keys(trails)) {
    if (now - (trails[id].lastSeen ?? 0) > TRAIL_MAX_AGE_MS) {
      delete trails[id];
    }
  }

  let cameraCalibrated = false;
  let cameraDetCount = 0;
  let frameUncalibrated = 0;

  for (const det of detections) {
    const key = trailKeyFor(det);
    if (!key) continue;

    cameraDetCount++;

    const calibrated = det.floor_calibrated ?? false;
    if (calibrated) cameraCalibrated = true;

    // Project to canvas. Drop uncalibrated detections entirely.
    const projected = projectDetectionToCanvas(det, fp);
    if (!projected) {
      if (floorPlanReady && !calibrated) frameUncalibrated++;
      continue;
    }

    const gtId = det.global_track_id;
    const displayName = det.display_name || det.identity_id || (gtId || "").slice(0, 8);
    const idForColor = det.identity_id || gtId || key;

    // Room lookup from projected canvas point.
    const roomName = roomForCanvasPoint(projected.x, projected.y, fp.canvasW, fp.canvasH, rooms.value);

    let trail = trails[key];
    if (!trail) {
      trail = {
        points: [],
        current: null,
        color: identityColor(idForColor),
        displayName,
        lastSeen: now,
        calibrated,
        confidence: det.identity_confidence ?? 0,
        roomName,
        _identityId: det.identity_id || null,
        _gtId: gtId || null,
      };
      trails[key] = trail;

      // If this is a new id: trail, merge any existing gt: trail for the same GT.
      if (key.startsWith("id:") && gtId) {
        const gtKey = `gt:${gtId}`;
        const gtTrail = trails[gtKey];
        if (gtTrail) {
          trail.points = [...gtTrail.points];
          if (!trail.displayName || trail.displayName === gtId.slice(0, 8)) {
            trail.displayName = gtTrail.displayName;
          }
          delete trails[gtKey];
        }
      }
    }

    trail.lastSeen = now;
    trail.displayName = displayName;
    trail.calibrated = calibrated;
    trail.confidence = det.identity_confidence ?? trail.confidence;
    trail.roomName = roomName;
    trail.points.push({ x: projected.x, y: projected.y, ts: now });
    if (trail.points.length > MAX_TRAIL_POINTS) trail.points = trail.points.slice(-MAX_TRAIL_POINTS);
    trail.current = { x: projected.x, y: projected.y };
  }

  // Reconcile: if the same frame produced both a gt: and an id: trail for the
  // same person (gt detection processed before id detection), merge now.
  for (const key of Object.keys(trails)) {
    if (!key.startsWith("gt:")) continue;
    const gtId = key.slice(3);
    for (const otherKey of Object.keys(trails)) {
      if (!otherKey.startsWith("id:")) continue;
      if (trails[otherKey]._gtId === gtId) {
        trails[otherKey].points = [...trails[key].points, ...trails[otherKey].points]
          .sort((a, b) => a.ts - b.ts)
          .slice(-MAX_TRAIL_POINTS);
        if (trails[key].lastSeen > trails[otherKey].lastSeen) {
          trails[otherKey].lastSeen = trails[key].lastSeen;
        }
        delete trails[key];
        break;
      }
    }
  }

  // Sliding window for uncalibrated count (10-second lookback).
  if (frameUncalibrated > 0) {
    _uncalibratedWindow.push({ count: frameUncalibrated, ts: now });
  }
  _uncalibratedWindow = _uncalibratedWindow.filter((e) => now - e.ts <= 10_000);
  uncalibratedDetCount.value = _uncalibratedWindow.reduce((s, e) => s + e.count, 0);

  identityTrails.value = trails;

  // Update per-camera status.
  if (frame.camera_id) {
    cameraFrameState.value = {
      ...cameraFrameState.value,
      [frame.camera_id]: {
        lastSeen: now,
        calibrated: cameraCalibrated,
        detections: cameraDetCount,
      },
    };
  }
}

onMounted(() => {
  loadFloorPlan();
  loadRooms();
  // WS lifecycle is handled inside useCtsWebSocket (connects on call, disconnects on unmount).
});

onBeforeUnmount(() => {
  if (_uploadBlobUrl) { URL.revokeObjectURL(_uploadBlobUrl); _uploadBlobUrl = null; }
  if (_resizeObserver) { _resizeObserver.disconnect(); _resizeObserver = null; }
});
</script>

<style scoped>
.floor-plan-canvas {
  background: var(--cc-surface-2);
  border: 1px solid var(--cc-divider-strong);
  border-radius: 8px;
  overflow: hidden;
  min-height: 480px;
}

.floor-plan-svg {
  width: 100%;
  height: 100%;
  min-height: 480px;
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

.scale-picker-container {
  position: relative;
  display: inline-block;
  width: 100%;
  user-select: none;
  border: 1px solid var(--cc-divider-strong, rgba(0,0,0,0.12));
  border-radius: 6px;
  overflow: hidden;
}

.scale-picker-img {
  display: block;
  width: 100%;
  max-height: min(500px, 65vh);
  object-fit: contain;
}

.scale-picker-empty {
  height: 200px;
  background: var(--cc-surface-2, rgba(0,0,0,0.03));
}

.scale-picker-overlay {
  position: absolute;
  top: 0;
  left: 0;
  pointer-events: none;
}

.crop-container {
  position: relative;
  display: inline-block;
  width: 100%;
  user-select: none;
  border: 1px solid var(--cc-divider-strong, rgba(0,0,0,0.12));
  border-radius: 6px;
  overflow: hidden;
}

.crop-img {
  display: block;
  width: 100%;
  max-height: min(400px, 55vh);
  object-fit: contain;
}

.crop-svg-overlay {
  position: absolute;
  pointer-events: none;
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
