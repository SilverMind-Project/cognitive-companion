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

    <!-- Prerequisites banner -->
    <v-card class="glass-card mb-5">
      <v-card-text class="py-3">
        <div class="text-caption text-medium-emphasis mb-2 font-weight-medium">SETUP PREREQUISITES</div>
        <div class="d-flex flex-wrap ga-3 align-center">
          <span>Floor plan image</span>
          <div class="prereq-item" :class="floorPlanReady ? 'prereq-ok' : 'prereq-warn'">
            <v-icon size="16" :color="floorPlanReady ? 'success' : 'warning'">
              {{ floorPlanReady ? 'mdi-check-circle' : 'mdi-alert-circle-outline' }}
            </v-icon>
          </div>
          <div class="prereq-item" :class="scaleReady ? 'prereq-ok' : 'prereq-warn'">
            <v-icon size="16" :color="scaleReady ? 'success' : 'warning'">
              {{ scaleReady ? 'mdi-check-circle' : 'mdi-alert-circle-outline' }}
            </v-icon>
            <span>Scale set ({{ scaleReady ? `${fpMpp} m/px` : 'missing' }})</span>
          </div>
          <div class="prereq-item" :class="selectedCameraId ? (existingCalibration ? 'prereq-ok' : 'prereq-none') : 'prereq-none'">
            <v-icon size="16" :color="existingCalibration ? 'success' : 'default'">
              {{ existingCalibration ? 'mdi-check-circle' : 'mdi-circle-outline' }}
            </v-icon>
            <span>{{ selectedCameraId ? (existingCalibration ? 'Camera calibrated' : 'Camera not yet calibrated') : 'Select a camera' }}</span>
          </div>
        </div>
        <div v-if="!floorPlanReady || !scaleReady" class="mt-3 text-body-2">
          <v-icon size="14" class="mr-1" color="warning">mdi-information-outline</v-icon>
          Upload a floor plan with its scale in
          <router-link to="/admin/cts/floor-plan" class="text-primary">Floor Plan settings</router-link>
          first. That enables click-to-pick calibration — no manual coordinate entry needed.
        </div>
      </v-card-text>
    </v-card>

    <!-- No camera selected -->
    <v-alert v-if="!selectedCameraId" type="info" variant="tonal" class="mt-2">
      Select a camera from the dropdown to begin calibration.
    </v-alert>

    <!-- Main calibration area -->
    <template v-if="selectedCameraId">
      <!-- Mode toggle when floor plan is available -->
      <div class="d-flex align-center mb-4 ga-3 flex-wrap">
        <v-btn-toggle
          v-if="floorPlanReady && scaleReady"
          v-model="inputMode"
          mandatory
          density="compact"
          variant="outlined"
        >
          <v-btn value="pick" prepend-icon="mdi-cursor-pointer">Click-to-Pick</v-btn>
          <v-btn value="manual" prepend-icon="mdi-pencil">Manual Entry</v-btn>
        </v-btn-toggle>

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

        <span v-if="floorPlanReady && scaleReady" class="text-caption text-medium-emphasis">
          {{ inputMode === 'pick'
            ? 'Click a point on the camera image, then click the same spot on the floor plan.'
            : 'Click the camera image, then type the floor coordinates manually.' }}
        </span>
      </div>

      <v-row>
        <!-- Left: camera snapshot -->
        <v-col cols="12" :md="inputMode === 'pick' && floorPlanReady && scaleReady ? 6 : 7">
          <v-card>
            <v-card-title class="d-flex align-center">
              <span>Camera Frame</span>
              <v-spacer />
              <BlurToggle class="mr-2" />
              <v-btn size="small" variant="tonal" prepend-icon="mdi-camera" @click="loadSnapshot">
                Refresh
              </v-btn>
            </v-card-title>
            <v-card-text class="pa-0 position-relative">
              <div
                class="snapshot-container"
                :class="{ 'cursor-crosshair': !!snapshotUrl }"
                @click="onCameraClick"
              >
                <img
                  v-if="snapshotUrl"
                  ref="imgEl"
                  :src="displaySrc(snapshotUrl)"
                  class="snapshot-img"
                  draggable="false"
                  @load="onImageLoad"
                />
                <div v-else class="d-flex align-center justify-center" style="height: 300px">
                  <v-progress-circular v-if="snapshotLoading" indeterminate />
                  <span v-else class="text-medium-emphasis text-body-2">
                    Click "Refresh" to load a camera frame.
                  </span>
                </div>

                <!-- Point overlay SVG (viewBox = natural camera resolution, positioned over content area) -->
                <svg
                  v-if="snapshotUrl && imgContentRect"
                  class="point-overlay"
                  :viewBox="`0 0 ${imgContentRect.naturalWidth} ${imgContentRect.naturalHeight}`"
                  :style="`width:${imgContentRect.width}px;height:${imgContentRect.height}px;top:${imgContentRect.offsetY}px;left:${imgContentRect.offsetX}px`"
                >
                  <!-- Distribution guide: faint quadrant zones, shown until 4 points are placed -->
                  <g v-if="points.length < 4">
                    <rect
                      x="0" y="0"
                      :width="imgContentRect.naturalWidth / 2"
                      :height="imgContentRect.naturalHeight / 2"
                      fill="none"
                      stroke="rgba(255,255,255,0.18)"
                      stroke-width="2"
                      stroke-dasharray="12 6"
                    />
                    <rect
                      :x="imgContentRect.naturalWidth / 2" y="0"
                      :width="imgContentRect.naturalWidth / 2"
                      :height="imgContentRect.naturalHeight / 2"
                      fill="none"
                      stroke="rgba(255,255,255,0.18)"
                      stroke-width="2"
                      stroke-dasharray="12 6"
                    />
                    <rect
                      x="0" :y="imgContentRect.naturalHeight / 2"
                      :width="imgContentRect.naturalWidth / 2"
                      :height="imgContentRect.naturalHeight / 2"
                      fill="none"
                      stroke="rgba(255,255,255,0.18)"
                      stroke-width="2"
                      stroke-dasharray="12 6"
                    />
                    <rect
                      :x="imgContentRect.naturalWidth / 2"
                      :y="imgContentRect.naturalHeight / 2"
                      :width="imgContentRect.naturalWidth / 2"
                      :height="imgContentRect.naturalHeight / 2"
                      fill="none"
                      stroke="rgba(255,255,255,0.18)"
                      stroke-width="2"
                      stroke-dasharray="12 6"
                    />
                    <text
                      :x="imgContentRect.naturalWidth * 0.25"
                      :y="imgContentRect.naturalHeight * 0.25"
                      text-anchor="middle" dominant-baseline="middle"
                      fill="rgba(255,255,255,0.35)" font-size="36"
                      :opacity="pointInQuadrant(0) ? 0 : 1"
                    >Place point here</text>
                    <text
                      :x="imgContentRect.naturalWidth * 0.75"
                      :y="imgContentRect.naturalHeight * 0.25"
                      text-anchor="middle" dominant-baseline="middle"
                      fill="rgba(255,255,255,0.35)" font-size="36"
                      :opacity="pointInQuadrant(1) ? 0 : 1"
                    >Place point here</text>
                    <text
                      :x="imgContentRect.naturalWidth * 0.25"
                      :y="imgContentRect.naturalHeight * 0.75"
                      text-anchor="middle" dominant-baseline="middle"
                      fill="rgba(255,255,255,0.35)" font-size="36"
                      :opacity="pointInQuadrant(2) ? 0 : 1"
                    >Place point here</text>
                    <text
                      :x="imgContentRect.naturalWidth * 0.75"
                      :y="imgContentRect.naturalHeight * 0.75"
                      text-anchor="middle" dominant-baseline="middle"
                      fill="rgba(255,255,255,0.35)" font-size="36"
                      :opacity="pointInQuadrant(3) ? 0 : 1"
                    >Place point here</text>
                  </g>
                  <!-- Completed points — draggable with residual coloring -->
                  <g
                    v-for="(pt, i) in points"
                    :key="i"
                    style="cursor:grab"
                    @mousedown.stop="startCameraDrag(i, $event)"
                    @click.stop
                  >
                    <circle
                      :cx="pt.pixel[0]"
                      :cy="pt.pixel[1]"
                      r="40"
                      fill="transparent"
                    />
                    <circle
                      :cx="pt.pixel[0]"
                      :cy="pt.pixel[1]"
                      r="30"
                      fill="none"
                      :stroke="pointColor(i)"
                      stroke-width="3"
                    />
                    <circle
                      :cx="pt.pixel[0]"
                      :cy="pt.pixel[1]"
                      r="12"
                      :fill="pointColor(i)"
                    />
                    <text
                      v-bind="haloLg"
                      :x="pt.pixel[0] + 18"
                      :y="pt.pixel[1] - 10"
                      :fill="pointColor(i)"
                      font-size="48"
                      font-weight="500"
                      style="pointer-events:none"
                    >{{ i + 1 }}</text>
                  </g>
                  <!-- Auto-calibration suggestions: camera pixels only, not floor-plan coordinates -->
                  <g
                    v-for="(pt, i) in autoSuggestedPoints"
                    :key="`auto-${i}`"
                    class="auto-suggestion-marker"
                  >
                    <circle
                      :cx="pt.pixel[0]"
                      :cy="pt.pixel[1]"
                      r="24"
                      fill="none"
                      stroke="#38bdf8"
                      stroke-width="3"
                      stroke-dasharray="8 6"
                    />
                    <circle
                      :cx="pt.pixel[0]"
                      :cy="pt.pixel[1]"
                      r="7"
                      fill="#38bdf8"
                      opacity="0.85"
                    />
                  </g>
                  <!-- Pending camera point -->
                  <g v-if="pendingPixel">
                    <circle
                      :cx="pendingPixel[0]"
                      :cy="pendingPixel[1]"
                      r="50"
                      fill="none"
                      stroke="#f59e0b"
                      stroke-width="2.5"
                      stroke-dasharray="4 3"
                    />
                    <circle
                      :cx="pendingPixel[0]"
                      :cy="pendingPixel[1]"
                      r="15"
                      fill="#f59e0b"
                    />
                    <text
                      v-bind="haloLg"
                      :x="pendingPixel[0] + 18"
                      :y="pendingPixel[1] - 10"
                      fill="#f59e0b"
                      font-size="48"
                      font-weight="500"
                    >{{ points.length + 1 }}?</text>
                  </g>
                </svg>
              </div>

              <!-- Camera status bar -->
              <div class="d-flex align-center px-3 py-2 text-caption text-medium-emphasis">
                <template v-if="!snapshotUrl" />
                <template v-else-if="pendingPixel && inputMode === 'pick'">
                  <v-icon size="14" color="warning" class="mr-1">mdi-arrow-right-circle</v-icon>
                  Point {{ points.length + 1 }} placed — now click the same spot on the floor plan →
                </template>
                <template v-else>
                  <v-icon size="14" class="mr-1">mdi-cursor-default-click</v-icon>
                  Click a floor-level spot to place point {{ points.length + 1 }}
                  <template v-if="points.length < 4">
                    ({{ 4 - points.length }} more needed)
                  </template>
                </template>
              </div>
            </v-card-text>
          </v-card>
        </v-col>

        <!-- Right: floor plan picker OR manual entry -->
        <v-col cols="12" :md="inputMode === 'pick' && floorPlanReady && scaleReady ? 6 : 5">

          <!-- ── Click-to-Pick: floor plan image ──────────────────────────── -->
          <template v-if="inputMode === 'pick' && floorPlanReady && scaleReady">
            <v-card class="mb-4">
              <v-card-title class="d-flex align-center">
                <span>Floor Plan</span>
                <v-spacer />
                <v-chip v-if="pendingPixel" color="warning" size="small" variant="tonal">
                  Click to match point {{ points.length + 1 }}
                </v-chip>
              </v-card-title>
              <v-card-text class="pa-0 position-relative">
                <div
                  class="snapshot-container"
                  :class="pendingPixel ? 'cursor-crosshair fp-awaiting' : 'fp-idle'"
                  @click="onFloorPlanClick"
                >
                  <img
                    ref="fpImgEl"
                    :src="floorPlanUrl"
                    class="snapshot-img"
                    draggable="false"
                    alt="Floor plan"
                    @load="onFpImageLoad"
                  />
                  <svg
                    v-if="fpImgRect"
                    class="point-overlay"
                    :viewBox="`0 0 ${fpImgRect.width} ${fpImgRect.height}`"
                    :style="`width:${fpImgRect.width}px;height:${fpImgRect.height}px`"
                  >
                    <!-- Live coverage preview polygon -->
                    <polygon
                      v-if="previewCoveragePolygon"
                      :points="previewCoveragePolygon"
                      fill="rgba(99,102,241,0.12)"
                      :stroke="qualityColor(previewStatus === 'ok' ? 0 : previewStatus === 'warning' ? 0.10 : 0.30)"
                      stroke-width="2"
                      stroke-dasharray="8 4"
                    />
                    <text
                      v-if="previewCoveragePolygon && previewStatus"
                      x="8"
                      y="20"
                      :fill="qualityColor(previewStatus === 'ok' ? 0 : previewStatus === 'warning' ? 0.10 : 0.30)"
                      font-size="13"
                      font-weight="700"
                    >
                      preview · {{ previewStatus }}
                    </text>
                    <!-- Draggable floor plan points with residual coloring -->
                    <g
                      v-for="(pt, i) in points"
                      :key="i"
                      style="cursor:grab"
                      @mousedown.stop="startFloorDrag(i, $event)"
                      @click.stop
                    >
                      <circle
                        :cx="(pt.floor_m[0] / (fpWidth * fpMpp)) * fpImgRect.width"
                        :cy="(pt.floor_m[1] / (fpHeight * fpMpp)) * fpImgRect.height"
                        r="16"
                        fill="transparent"
                      />
                      <circle
                        :cx="(pt.floor_m[0] / (fpWidth * fpMpp)) * fpImgRect.width"
                        :cy="(pt.floor_m[1] / (fpHeight * fpMpp)) * fpImgRect.height"
                        r="8"
                        fill="none"
                        :stroke="pointColor(i)"
                        stroke-width="2.5"
                      />
                      <circle
                        :cx="(pt.floor_m[0] / (fpWidth * fpMpp)) * fpImgRect.width"
                        :cy="(pt.floor_m[1] / (fpHeight * fpMpp)) * fpImgRect.height"
                        r="2.5"
                        :fill="pointColor(i)"
                      />
                      <text
                        v-bind="haloSm"
                        :x="(pt.floor_m[0] / (fpWidth * fpMpp)) * fpImgRect.width + 12"
                        :y="(pt.floor_m[1] / (fpHeight * fpMpp)) * fpImgRect.height - 6"
                        :fill="pointColor(i)"
                        font-size="12"
                        font-weight="700"
                        style="pointer-events:none"
                      >{{ i + 1 }}</text>
                    </g>
                    <!-- Awaiting-click indicator: pulsing crosshair target -->
                    <g v-if="pendingPixel">
                      <line x1="0" :y1="fpImgRect.height / 2" :x2="fpImgRect.width" :y2="fpImgRect.height / 2"
                        stroke="#f59e0b" stroke-width="0.5" stroke-dasharray="6 4" opacity="0.4" />
                      <line :x1="fpImgRect.width / 2" y1="0" :x2="fpImgRect.width / 2" :y2="fpImgRect.height"
                        stroke="#f59e0b" stroke-width="0.5" stroke-dasharray="6 4" opacity="0.4" />
                      <text x="50%" y="50%" text-anchor="middle" dominant-baseline="middle"
                        fill="#f59e0b" font-size="13" font-weight="600" opacity="0.8">
                        Click here to place point {{ points.length + 1 }}
                      </text>
                    </g>
                  </svg>
                </div>
                <div class="d-flex align-center px-3 py-2 text-caption text-medium-emphasis">
                  <v-icon size="13" class="mr-1">mdi-map-marker</v-icon>
                  Points are placed in the floor plan coordinate frame
                  <template v-if="fpMpp">
                    &nbsp;({{ fpMpp }} m/px)
                  </template>
                </div>
              </v-card-text>
            </v-card>
          </template>

          <!-- ── Manual mode: coordinate entry ───────────────────────────── -->
          <template v-else>
            <!-- Coordinate system explainer -->
            <v-card class="mb-4">
              <v-card-title class="text-subtitle-2">
                <v-icon size="16" class="mr-1">mdi-help-circle-outline</v-icon>
                What do X and Y metres mean?
              </v-card-title>
              <v-card-text class="pb-2">
                <!-- SVG diagram -->
                <svg viewBox="0 0 320 218" class="coord-diagram">
                  <!-- Floor plan rectangle -->
                  <rect x="20" y="34" width="280" height="160" rx="4"
                    fill="rgba(99,102,241,0.07)" stroke="var(--cc-brand)" stroke-width="1.5" stroke-dasharray="6 3" />
                  <text x="160" y="12" text-anchor="middle" fill="var(--cc-brand)" font-size="10" font-weight="600">
                    Floor plan image
                  </text>

                  <!-- Origin -->
                  <circle cx="20" cy="34" r="5" fill="var(--cc-brand)" />
                  <text x="26" y="32" fill="var(--cc-brand)" font-size="10" font-weight="700">Origin (0, 0)</text>
                  <text x="26" y="44" fill="var(--cc-text-secondary, #888)" font-size="9">
                    top-left corner
                  </text>

                  <!-- X axis -->
                  <line x1="20" y1="34" x2="280" y2="34" stroke="var(--cc-brand)" stroke-width="1.5"
                    marker-end="url(#arrowX)" />
                  <text x="290" y="38" fill="var(--cc-brand)" font-size="11" font-weight="700">X</text>
                  <text x="145" y="30" text-anchor="middle" fill="var(--cc-brand)" font-size="9">→ increases right</text>

                  <!-- Y axis -->
                  <line x1="20" y1="34" x2="20" y2="179" stroke="var(--cc-brand)" stroke-width="1.5"
                    marker-end="url(#arrowY)" />
                  <text x="6" y="189" fill="var(--cc-brand)" font-size="11" font-weight="700">Y</text>
                  <text x="12" y="106" text-anchor="middle" fill="var(--cc-brand)" font-size="9"
                    transform="rotate(-90 12 106)">↓ increases downward</text>

                  <!-- Example point -->
                  <circle cx="180" cy="134" r="5" fill="#10b981" />
                  <!-- X dashed measurement line -->
                  <line x1="20" y1="134" x2="180" y2="134" stroke="#10b981" stroke-width="1" stroke-dasharray="4 3" />
                  <text x="100" y="129" text-anchor="middle" fill="#10b981" font-size="10">X = 3.2 m</text>
                  <!-- Y dashed measurement line -->
                  <line x1="180" y1="34" x2="180" y2="134" stroke="#10b981" stroke-width="1" stroke-dasharray="4 3" />
                  <text x="215" y="84" text-anchor="middle" fill="#10b981" font-size="10">Y = 2.5 m</text>

                  <!-- Arrow markers -->
                  <defs>
                    <marker id="arrowX" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
                      <path d="M0,0 L6,3 L0,6 Z" fill="var(--cc-brand)" />
                    </marker>
                    <marker id="arrowY" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
                      <path d="M0,0 L6,3 L0,6 Z" fill="var(--cc-brand)" />
                    </marker>
                  </defs>
                </svg>

                <div class="text-body-2 mt-2">
                  <strong>X</strong> and <strong>Y</strong> are straight-line distances measured
                  <em>on the floor</em> — not from the camera, not slanted distances through the air.
                  Measure them as if you were standing on the floor with a tape measure, from the
                  top-left corner of your floor plan image.
                </div>
                <v-alert type="warning" variant="tonal" density="compact" class="mt-3 text-caption">
                  All cameras must use the <strong>same origin</strong>. If camera A calls
                  the front door "X=0, Y=0" and camera B calls it "X=1, Y=0", tracks will not
                  align on the shared floor plan.
                </v-alert>
              </v-card-text>
            </v-card>
          </template>

          <!-- Point list (both modes) -->
          <v-card class="mb-4">
            <v-card-title class="d-flex align-center">
              <span>Point Correspondences</span>
              <v-spacer />
              <v-chip size="x-small" :color="points.length >= 4 ? 'success' : 'default'">
                {{ points.length }}/4{{ points.length > 4 ? '+' : '' }}
              </v-chip>
            </v-card-title>
            <v-card-text class="pb-0">
              <div v-if="points.length === 0" class="text-medium-emphasis text-body-2 py-2">
                No points yet. Click on the camera frame to start.
              </div>
              <div v-for="(pt, i) in points" :key="i" class="point-row mb-2">
                <div class="d-flex align-center mb-1">
                  <v-chip size="x-small" color="primary" class="mr-2 font-weight-bold">{{ i + 1 }}</v-chip>
                  <span class="text-caption text-medium-emphasis">
                    Camera: ({{ pt.pixel[0] }}px, {{ pt.pixel[1] }}px)
                  </span>
                  <v-spacer />
                  <v-btn icon="mdi-close" size="x-small" variant="text" @click="removePoint(i)" />
                </div>
                <!-- Show floor coords as read-only in pick mode, editable in manual mode -->
                <template v-if="inputMode === 'pick' && floorPlanReady && scaleReady">
                  <div class="text-caption ml-1" style="color: var(--cc-brand)">
                    <v-icon size="12" class="mr-1">mdi-map-marker</v-icon>
                    Floor: X = {{ pt.floor_m[0].toFixed(2) }} m, Y = {{ pt.floor_m[1].toFixed(2) }} m
                  </div>
                </template>
                <template v-else>
                  <v-row dense>
                    <v-col cols="6">
                      <v-text-field
                        v-model.number="pt.floor_m[0]"
                        label="X (m from left)"
                        variant="outlined"
                        density="compact"
                        type="number"
                        step="0.1"
                        hide-details
                      />
                    </v-col>
                    <v-col cols="6">
                      <v-text-field
                        v-model.number="pt.floor_m[1]"
                        label="Y (m from top)"
                        variant="outlined"
                        density="compact"
                        type="number"
                        step="0.1"
                        hide-details
                      />
                    </v-col>
                  </v-row>
                </template>
              </div>
            </v-card-text>
            <v-card-actions class="px-4 pb-4 pt-2">
              <v-btn variant="text" :disabled="points.length === 0" size="small" @click="clearPoints">
                Clear All
              </v-btn>
              <v-spacer />
              <v-btn
                color="primary"
                variant="flat"
                :loading="calibrating"
                :disabled="points.length < 4"
                @click="runCalibration"
              >
                Calibrate
              </v-btn>
            </v-card-actions>
          </v-card>

          <!-- Calibration result -->
          <v-card v-if="result">
            <v-card-title class="d-flex align-center">
              <span>Result</span>
              <v-spacer />
              <v-chip
                :color="result.status === 'ok' ? 'success' : result.status === 'warning' ? 'warning' : 'error'"
                size="small"
              >
                {{ result.status.toUpperCase() }}
              </v-chip>
            </v-card-title>
            <v-card-text>
              <div class="text-body-2 mb-1">
                Max reprojection error: <strong>{{ result.max_residual_m.toFixed(3) }} m</strong>
              </div>
              <div class="text-caption text-medium-emphasis mb-3">
                This is how far off the computed transform is at its worst calibration point.
                Under 0.1 m is good; over 0.3 m means the points were poorly placed or measured.
              </div>
              <v-table density="compact">
                <thead>
                  <tr><th>Point</th><th>Error (m)</th><th></th></tr>
                </thead>
                <tbody>
                  <tr v-for="(r, i) in result.residuals_m" :key="i">
                    <td>{{ i + 1 }}</td>
                    <td>{{ r.toFixed(4) }}</td>
                    <td>
                      <v-chip size="x-small" :color="r < 0.05 ? 'success' : r < 0.15 ? 'warning' : 'error'">
                        {{ r < 0.05 ? 'excellent' : r < 0.15 ? 'acceptable' : 'poor' }}
                      </v-chip>
                    </td>
                  </tr>
                </tbody>
              </v-table>
              <v-alert
                v-if="result.visibility_polygon_computed === false"
                type="warning"
                variant="tonal"
                density="compact"
                class="mt-3"
              >
                <div class="text-caption">
                  <strong>Coverage map not updated.</strong>
                  {{ result.visibility_polygon_warning || 'Visibility polygon could not be computed from this homography.' }}
                </div>
              </v-alert>
              <v-alert
                v-else-if="result.visibility_polygon_computed === true"
                type="success"
                variant="tonal"
                density="compact"
                class="mt-3"
              >
                <div class="text-caption">
                  Coverage map updated — visibility polygon computed successfully.
                </div>
              </v-alert>
              <div v-if="result.status !== 'ok'" class="text-caption mt-3 text-medium-emphasis">
                Tip: re-calibrate with more spread-out points and re-measure carefully.
                Points with a "poor" rating are dragging down accuracy — try replacing them.
              </div>
            </v-card-text>
          </v-card>

          <!-- Existing calibration indicator (shown when no new result yet) -->
          <v-card v-else-if="existingCalibration && !autoResult">
            <v-card-text class="d-flex align-center">
              <v-icon color="success" class="mr-2">mdi-check-circle</v-icon>
              <span class="text-body-2">
                This camera is already calibrated. Run again to update.
              </span>
            </v-card-text>
          </v-card>

          <!-- Auto-calibrate result card -->
          <v-card v-if="autoResult" class="mt-3">
            <v-card-title class="d-flex align-center">
              <v-icon start size="18">mdi-auto-fix</v-icon>
              <span>Auto-calibrate Result</span>
              <v-spacer />
              <v-chip
                :color="autoResult.confidence >= 0.6 ? 'success' : autoResult.confidence >= 0.4 ? 'warning' : 'error'"
                size="small"
              >
                {{ Math.round(autoResult.confidence * 100) }}% confidence
              </v-chip>
            </v-card-title>
            <v-card-text>
              <div class="text-body-2 mb-1">
                <strong>{{ autoResult.inlier_count }}</strong> of
                <strong>{{ autoResult.sample_count }}</strong> floor points used &nbsp;·&nbsp;
                FoV: <strong>{{ autoResult.fov_deg }}°</strong>
              </div>
              <v-alert
                v-if="autoResult.warning"
                type="warning"
                variant="tonal"
                density="compact"
                class="mt-2 text-caption"
              >
                {{ autoResult.warning }}
              </v-alert>
              <div class="text-caption text-medium-emphasis mt-2">
                This draft found {{ autoResult.suggested_points?.length || 0 }} candidate
                floor pixels. It has not been saved as calibration. Refine manually by
                anchoring the suggested camera points to the floor plan.
              </div>
            </v-card-text>
            <v-card-actions class="px-4 pb-4 pt-0">
              <v-btn variant="text" size="small" @click="dismissAutoResult">Dismiss</v-btn>
              <v-spacer />
              <v-btn
                color="primary"
                variant="tonal"
                size="small"
                prepend-icon="mdi-pencil"
                @click="populateFromAutoResult"
              >
                Refine manually
              </v-btn>
            </v-card-actions>
          </v-card>
        </v-col>
      </v-row>

      <!-- Tips panel -->
      <v-expansion-panels class="mt-5" variant="accordion">
        <v-expansion-panel>
          <v-expansion-panel-title class="text-body-2 font-weight-medium">
            <v-icon start size="16">mdi-lightbulb-outline</v-icon>
            Tips for accurate calibration
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <v-row>
              <v-col cols="12" md="4">
                <div class="text-subtitle-2 mb-2">Choose good points</div>
                <ul class="text-body-2 tip-list">
                  <li>Pick points on the <strong>floor surface</strong>, not walls or elevated objects</li>
                  <li>Spread points across the full camera view — avoid clustering in one area</li>
                  <li>Use fixed landmarks: doorway corners, tile intersections, rug edges</li>
                  <li>Avoid points that are very close to the camera's edge</li>
                </ul>
              </v-col>
              <v-col cols="12" md="4">
                <div class="text-subtitle-2 mb-2">Measure carefully</div>
                <ul class="text-body-2 tip-list">
                  <li>Use a tape measure on the actual floor — never estimate by eye</li>
                  <li>Measure from the same reference corner for every camera</li>
                  <li>Measure horizontal and vertical distances separately (not diagonal)</li>
                  <li>Double-check: if the floor plan shows a wall at X=5.0 m, stand there and measure from your origin</li>
                </ul>
              </v-col>
              <v-col cols="12" md="4">
                <div class="text-subtitle-2 mb-2">Interpreting errors</div>
                <ul class="text-body-2 tip-list">
                  <li>Under 0.05 m: excellent — person dots will be accurate to ~5 cm</li>
                  <li>0.05–0.15 m: acceptable for most use cases</li>
                  <li>Over 0.3 m: re-calibrate; check measurements and point placement</li>
                  <li>One "poor" point usually means a mis-click or measurement error — replace it</li>
                </ul>
              </v-col>
            </v-row>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>
    </template>

    <v-snackbar v-model="snack" :color="snackColor" timeout="4000">{{ snackText }}</v-snackbar>

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
import { ref, computed, watch, onMounted, onBeforeUnmount } from "vue";
import { cts } from "../../services/cts.js";
import { household } from "../../services/household.js";
import { useNotify } from "../../composables/useNotify.js";
import { useBlurMode, useDisplaySrc } from "../../composables/useBlurMode.js";
import { useCtsWebSocket } from "../../composables/useCtsWebSocket.js";
import { HALO, qualityColor } from "../../composables/useAnnotationStyle.js";
import BlurToggle from "../../components/cts/BlurToggle.vue";
import CalibrationHealthPanel from "../../components/cts/CalibrationHealthPanel.vue";

// haloLg: camera natural-resolution SVG (viewBox ~1920×1080, font-size 48)
//   stroke-width 8 ≈ 17% of 48 — thin enough to not distort letterforms
// haloSm: floor-plan display-pixel SVG (viewBox = displayed size, font-size 12)
//   stroke-width 2 ≈ 17% of 12
const haloLg = HALO.attrs(8);
const haloSm = HALO.attrs(2);

const { snack, snackText, snackColor, notify } = useNotify();
const { blurMode } = useBlurMode();
const { displaySrc } = useDisplaySrc(blurMode);

// ── Camera state ──────────────────────────────────────────────────────────
const cameras = ref([]);
const selectedCameraId = ref(null);
const snapshotUrl = ref(null);
const snapshotLoading = ref(false);
const imgEl = ref(null);
// Letterbox-aware content area of the camera snapshot image.
// naturalWidth/Height: the camera's native resolution.
// width/height: displayed content size (within object-fit:contain element).
// offsetX/offsetY: pillarbox/letterbox offset from element top-left.
const imgContentRect = ref(null);
const existingCalibration = ref(false);

// ── Floor plan state ──────────────────────────────────────────────────────
const floorPlanUrl = ref(null);
const fpWidth = ref(null);
const fpHeight = ref(null);
const fpMpp = ref(null);
const fpImgEl = ref(null);
const fpImgRect = ref(null);

// ── Calibration state ─────────────────────────────────────────────────────
const points = ref([]);
const calibrating = ref(false);
const result = ref(null);

// ── Live preview state ─────────────────────────────────────────────────────
const previewMatrix = ref(null);
const previewResiduals = ref([]);
const previewStatus = ref(null);
let _previewDebounceTimer = null;

// ── Drag state ─────────────────────────────────────────────────────────────
const dragState = ref(null);

// ── Auto-calibration state ────────────────────────────────────────────────
// Track the most recent MinIO key received via WebSocket for the selected camera.
// This key is sent to the auto-calibrate endpoint so the orchestrator can
// download the same frame it just processed.
const latestMinioKey = ref(null);
const autoCalibrating = ref(false);
const autoResult = ref(null);
const autoSuggestedPoints = ref([]);

// ── Click-to-pick state ───────────────────────────────────────────────────
// pendingPixel: camera click waiting for a matching floor plan click
const pendingPixel = ref(null);
const inputMode = ref("pick");

// ── Computed ──────────────────────────────────────────────────────────────
const floorPlanReady = computed(() => !!(floorPlanUrl.value));
const scaleReady = computed(() => !!(fpMpp.value && fpWidth.value && fpHeight.value));

// ── Point color helper ─────────────────────────────────────────────────────
function pointColor(i) {
  const residuals = result.value?.residuals_m ?? previewResiduals.value;
  if (!residuals || residuals.length <= i) return "var(--cc-brand)";
  return qualityColor(residuals[i]);
}

// ── Point-in-quadrant helper ───────────────────────────────────────────────
function pointInQuadrant(q) {
  if (!imgContentRect.value) return false;
  const W = imgContentRect.value.naturalWidth;
  const H = imgContentRect.value.naturalHeight;
  return points.value.some(({ pixel: [px, py] }) => {
    const inRight = px >= W / 2;
    const inBottom = py >= H / 2;
    if (q === 0) return !inRight && !inBottom;
    if (q === 1) return inRight && !inBottom;
    if (q === 2) return !inRight && inBottom;
    if (q === 3) return inRight && inBottom;
    return false;
  });
}

// ── Project point through homography matrix ─────────────────────────────────
function _projectPoint(H, px, py) {
  const hw = H[0][0] * px + H[0][1] * py + H[0][2];
  const hh = H[1][0] * px + H[1][1] * py + H[1][2];
  const hw3 = H[2][0] * px + H[2][1] * py + H[2][2];
  if (Math.abs(hw3) < 1e-9) return null;
  return [hw / hw3, hh / hw3];
}

// ── Preview coverage polygon computed ───────────────────────────────────────
const previewCoveragePolygon = computed(() => {
  if (!previewMatrix.value) return null;
  if (!imgContentRect.value) return null;
  if (!fpImgRect.value) return null;
  if (!fpMpp.value || !fpWidth.value || !fpHeight.value) return null;

  const H = previewMatrix.value;
  const W = imgContentRect.value.naturalWidth;
  const Ht = imgContentRect.value.naturalHeight;
  const n = 20;

  const boundary = [];
  for (let i = 0; i < n; i++) {
    const t = i / n;
    boundary.push([W * t, 0]);
    boundary.push([W, Ht * t]);
    boundary.push([W * (1 - t), Ht]);
    boundary.push([0, Ht * (1 - t)]);
  }

  const floorPts = [];
  for (const [px, py] of boundary) {
    const fm = _projectPoint(H, px, py);
    if (fm === null) return null;
    floorPts.push(fm);
  }

  const totalW_m = fpWidth.value * fpMpp.value;
  const totalH_m = fpHeight.value * fpMpp.value;

  const svgPts = floorPts.map(([fx, fy]) => {
    const x = (fx / totalW_m) * fpImgRect.value.width;
    const y = (fy / totalH_m) * fpImgRect.value.height;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  return svgPts.join(" ");
});

// ── Preview scheduling ─────────────────────────────────────────────────────
function schedulePreview() {
  if (points.value.length < 4) {
    previewMatrix.value = null;
    previewResiduals.value = [];
    previewStatus.value = null;
    return;
  }
  clearTimeout(_previewDebounceTimer);
  _previewDebounceTimer = setTimeout(async () => {
    try {
      const res = await cts.previewHomography(points.value);
      previewMatrix.value = res.matrix;
      previewResiduals.value = res.residuals_m;
      previewStatus.value = res.status;
    } catch {
      previewMatrix.value = null;
    }
  }, 400);
}

watch(points, schedulePreview, { deep: true });

// ── Drag: camera pane ──────────────────────────────────────────────────────
function startCameraDrag(i, e) {
  e.preventDefault();
  e.stopPropagation();
  dragState.value = { pane: "camera", idx: i };
  window.addEventListener("mousemove", onCameraDragMove);
  window.addEventListener("mouseup", stopCameraDrag);
}

function onCameraDragMove(e) {
  if (!dragState.value || dragState.value.pane !== "camera") return;
  if (!imgEl.value || !imgContentRect.value) return;

  const r = imgEl.value.getBoundingClientRect();
  const { offsetX, offsetY, width: cw, height: ch, naturalWidth: nw, naturalHeight: nh } = imgContentRect.value;

  const relX = Math.max(0, Math.min(cw, e.clientX - r.left - offsetX));
  const relY = Math.max(0, Math.min(ch, e.clientY - r.top - offsetY));

  const px = Math.round(relX / cw * nw);
  const py = Math.round(relY / ch * nh);

  const updated = points.value.map((pt, idx) =>
    idx === dragState.value.idx ? { ...pt, pixel: [px, py] } : pt
  );
  points.value = updated;
}

function stopCameraDrag() {
  dragState.value = null;
  window.removeEventListener("mousemove", onCameraDragMove);
  window.removeEventListener("mouseup", stopCameraDrag);
}

// ── Drag: floor plan pane ──────────────────────────────────────────────────
function startFloorDrag(i, e) {
  e.preventDefault();
  e.stopPropagation();
  dragState.value = { pane: "floor", idx: i };
  window.addEventListener("mousemove", onFloorDragMove);
  window.addEventListener("mouseup", stopFloorDrag);
}

function onFloorDragMove(e) {
  if (!dragState.value || dragState.value.pane !== "floor") return;
  if (!fpImgEl.value || !fpImgRect.value) return;

  const r = fpImgEl.value.getBoundingClientRect();
  const xn = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
  const yn = Math.max(0, Math.min(1, (e.clientY - r.top) / r.height));

  const floorX = parseFloat((xn * fpWidth.value * fpMpp.value).toFixed(3));
  const floorY = parseFloat((yn * fpHeight.value * fpMpp.value).toFixed(3));

  const updated = points.value.map((pt, idx) =>
    idx === dragState.value.idx ? { ...pt, floor_m: [floorX, floorY] } : pt
  );
  points.value = updated;
}

function stopFloorDrag() {
  dragState.value = null;
  window.removeEventListener("mousemove", onFloorDragMove);
  window.removeEventListener("mouseup", stopFloorDrag);
}

// ── Load ──────────────────────────────────────────────────────────────────
async function loadCameras() {
  try {
    cameras.value = await cts.getCameras();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function loadFloorPlan() {
  try {
    const data = await household.getFloorPlan();
    floorPlanUrl.value = data.floor_plan_url;
    fpWidth.value = data.floor_plan_width;
    fpHeight.value = data.floor_plan_height;
    fpMpp.value = data.floor_meters_per_pixel;
  } catch {
    // Not configured yet.
  }
}

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
  await Promise.all([loadSnapshot(), loadExistingCalibration()]);
}

async function loadSnapshot() {
  if (!selectedCameraId.value) return;
  snapshotLoading.value = true;
  if (snapshotUrl.value) {
    URL.revokeObjectURL(snapshotUrl.value);
    snapshotUrl.value = null;
  }
  try {
    snapshotUrl.value = await cts.getSnapshot(selectedCameraId.value);
  } catch (e) {
    notify(`Snapshot failed: ${e.message}`, "warning");
  } finally {
    snapshotLoading.value = false;
  }
}

async function loadExistingCalibration() {
  if (!selectedCameraId.value) return;
  try {
    await cts.getHomography(selectedCameraId.value);
    existingCalibration.value = true;
  } catch {
    existingCalibration.value = false;
  }
}

// ── Image load / resize ───────────────────────────────────────────────────
function onImageLoad() {
  if (!imgEl.value) return;
  const r = imgEl.value.getBoundingClientRect();
  const nw = imgEl.value.naturalWidth;
  const nh = imgEl.value.naturalHeight;
  if (!nw || !nh) return;
  const naturalRatio = nw / nh;
  const elRatio = r.width / r.height;
  let contentW, contentH, offX, offY;
  if (naturalRatio > elRatio) {
    // Letterboxed (bars top/bottom).
    contentW = r.width;
    contentH = r.width / naturalRatio;
    offX = 0;
    offY = (r.height - contentH) / 2;
  } else {
    // Pillarboxed (bars left/right).
    contentH = r.height;
    contentW = r.height * naturalRatio;
    offX = (r.width - contentW) / 2;
    offY = 0;
  }
  imgContentRect.value = {
    width: contentW, height: contentH,
    offsetX: offX, offsetY: offY,
    naturalWidth: nw, naturalHeight: nh,
  };
}

function onFpImageLoad() {
  if (!fpImgEl.value) return;
  const r = fpImgEl.value.getBoundingClientRect();
  fpImgRect.value = { width: r.width, height: r.height };
}

// ── Camera click ──────────────────────────────────────────────────────────
function onCameraClick(e) {
  if (!snapshotUrl.value || !imgEl.value || !imgContentRect.value) return;
  const r = imgEl.value.getBoundingClientRect();
  const { offsetX, offsetY, width: cw, height: ch, naturalWidth: nw, naturalHeight: nh } = imgContentRect.value;
  // Click position relative to the image content area (excluding pillar/letterbox bars).
  const relX = e.clientX - r.left - offsetX;
  const relY = e.clientY - r.top - offsetY;
  if (relX < 0 || relX > cw || relY < 0 || relY > ch) return;
  // Convert to raw pixel coords in the camera's natural resolution.
  let px = Math.round(relX / cw * nw);
  let py = Math.round(relY / ch * nh);
  const suggestion = nearestAutoSuggestion(px, py);
  if (suggestion) {
    px = suggestion.pixel[0];
    py = suggestion.pixel[1];
  }

  if (inputMode.value === 'pick' && floorPlanReady.value && scaleReady.value) {
    pendingPixel.value = [px, py];
  } else {
    points.value.push({ pixel: [px, py], floor_m: [0, 0] });
  }
}

// ── Floor plan click (pick mode) ──────────────────────────────────────────
function onFloorPlanClick(e) {
  if (!pendingPixel.value || !fpImgEl.value) return;
  const r = fpImgEl.value.getBoundingClientRect();
  const xn = (e.clientX - r.left) / r.width;
  const yn = (e.clientY - r.top) / r.height;
  if (xn < 0 || xn > 1 || yn < 0 || yn > 1) return;

  const floorX = parseFloat((xn * fpWidth.value * fpMpp.value).toFixed(3));
  const floorY = parseFloat((yn * fpHeight.value * fpMpp.value).toFixed(3));

  points.value.push({
    pixel: pendingPixel.value,
    floor_m: [floorX, floorY],
  });
  consumeAutoSuggestion(pendingPixel.value);
  pendingPixel.value = null;
}

// ── Points ────────────────────────────────────────────────────────────────
function removePoint(i) {
  points.value.splice(i, 1);
  // If we removed a point while one is pending, keep the pending state.
}

function clearPoints() {
  points.value = [];
  pendingPixel.value = null;
  result.value = null;
  autoSuggestedPoints.value = [];
}

// M2: handle test-projection from CalibrationHealthPanel
function onTestProjection(cameraId) {
  selectedCameraId.value = cameraId;
  // Scroll to the calibration area for visual inspection.
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// ── Calibrate ─────────────────────────────────────────────────────────────
async function runCalibration() {
  if (points.value.length < 4) return;
  if (!imgContentRect.value) {
    notify("Load a camera snapshot first", "warning");
    return;
  }
  calibrating.value = true;
  result.value = null;
  try {
    result.value = await cts.postHomography(
      selectedCameraId.value,
      points.value,
      imgContentRect.value.naturalWidth,
      imgContentRect.value.naturalHeight,
    );
    existingCalibration.value = true;
    autoSuggestedPoints.value = [];
    notify("Calibration saved");
  } catch (e) {
    notify(e.message, "error");
  } finally {
    calibrating.value = false;
  }
}

// ── Auto-calibrate ────────────────────────────────────────────────────────

function normalizeSuggestedPoints(rawPoints) {
  return (rawPoints || [])
    .map((pt) => {
      const pixel = pt?.pixel;
      if (!Array.isArray(pixel) || pixel.length < 2) return null;
      const px = Number(pixel[0]);
      const py = Number(pixel[1]);
      if (!Number.isFinite(px) || !Number.isFinite(py)) return null;
      return { pixel: [Math.round(px), Math.round(py)], local_floor_m: pt.local_floor_m || null };
    })
    .filter(Boolean);
}

function nearestAutoSuggestion(px, py) {
  if (!autoSuggestedPoints.value.length) return null;
  let best = null;
  let bestD2 = Infinity;
  for (const suggestion of autoSuggestedPoints.value) {
    const dx = suggestion.pixel[0] - px;
    const dy = suggestion.pixel[1] - py;
    const d2 = dx * dx + dy * dy;
    if (d2 < bestD2) {
      best = suggestion;
      bestD2 = d2;
    }
  }
  return bestD2 <= 36 * 36 ? best : null;
}

function consumeAutoSuggestion(pixel) {
  autoSuggestedPoints.value = autoSuggestedPoints.value.filter((suggestion) => {
    const dx = suggestion.pixel[0] - pixel[0];
    const dy = suggestion.pixel[1] - pixel[1];
    return dx * dx + dy * dy > 36 * 36;
  });
}

async function runAutoCalibrate() {
  if (!selectedCameraId.value) return;
  autoCalibrating.value = true;
  autoResult.value = null;
  result.value = null;
  try {
    // Pass minio_key when available (from live stream); otherwise the BFF
    // fetches a fresh snapshot from the RTSP ingress automatically.
    const body = latestMinioKey.value ? { minio_key: latestMinioKey.value } : {};
    const res = await cts.autoCalibrate(selectedCameraId.value, body);
    autoResult.value = res;
    autoSuggestedPoints.value = [];
    notify("Auto-calibration draft ready — review the suggested camera points below.", "success");
  } catch (e) {
    const msg = e?.response?.data?.detail?.message || e.message || "Auto-calibration failed.";
    notify(msg, "error");
  } finally {
    autoCalibrating.value = false;
  }
}

function populateFromAutoResult() {
  if (!autoResult.value || !imgContentRect.value) return;
  autoSuggestedPoints.value = normalizeSuggestedPoints(autoResult.value.suggested_points);
  inputMode.value = "pick";
  pendingPixel.value = null;
  autoResult.value = null;
  notify(`${autoSuggestedPoints.value.length} suggested camera points shown — click one, then anchor it on the floor plan.`, "info");
}

function dismissAutoResult() {
  autoResult.value = null;
  autoSuggestedPoints.value = [];
}

// ── WebSocket: track latest MinIO key per camera for auto-calibrate ───────
function onLiveMessage(frame) {
  if (
    frame.type === "cts_live_frame" &&
    frame.camera_id === selectedCameraId.value &&
    frame.minio_key
  ) {
    latestMinioKey.value = frame.minio_key;
  }
}

// The WebSocket is kept alive for the lifetime of this view.  It is only
// used here to harvest the latest minio_key for the auto-calibrate feature;
// we do not render the live stream in the calibration view.
useCtsWebSocket(onLiveMessage);

onMounted(() => {
  loadCameras();
  loadFloorPlan();
});

onBeforeUnmount(() => {
  if (snapshotUrl.value) URL.revokeObjectURL(snapshotUrl.value);
  stopCameraDrag();
  stopFloorDrag();
  clearTimeout(_previewDebounceTimer);
});
</script>

<style scoped>
.snapshot-container {
  position: relative;
  display: inline-block;
  width: 100%;
  user-select: none;
}

.cursor-crosshair {
  cursor: crosshair;
}

.fp-idle {
  cursor: default;
  opacity: 0.85;
}

.fp-awaiting {
  outline: 2px solid #f59e0b;
  outline-offset: -2px;
  border-radius: 4px;
}

.snapshot-img {
  display: block;
  width: 100%;
  max-height: 380px;
  object-fit: contain;
}

.point-overlay {
  position: absolute;
  pointer-events: none;
}

.prereq-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  padding: 4px 8px;
  border-radius: 6px;
}

.prereq-ok {
  background: rgba(16, 185, 129, 0.1);
  color: #10b981;
}

.prereq-warn {
  background: rgba(245, 158, 11, 0.1);
  color: #f59e0b;
}

.prereq-none {
  background: var(--cc-surface-2, rgba(0,0,0,0.04));
  color: var(--cc-text-secondary, #888);
}

.coord-diagram {
  display: block;
  width: 100%;
  max-width: 320px;
  height: auto;
  margin-bottom: 4px;
}

.point-row {
  background: var(--cc-surface-2, rgba(0,0,0,0.03));
  border-radius: 8px;
  padding: 8px 10px 10px;
}

.tip-list {
  padding-left: 18px;
  line-height: 1.7;
}

.tip-list li {
  margin-bottom: 4px;
}
</style>
