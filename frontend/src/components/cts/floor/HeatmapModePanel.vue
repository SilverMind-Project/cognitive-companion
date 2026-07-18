<template>
  <v-row class="floor-plan-layout">
    <!-- Floor plan canvas with heatmap overlay -->
    <v-col cols="12" md="9" class="floor-plan-main">
      <v-card class="glass-card floor-plan-visual-card">
        <v-card-title class="floor-plan-card-title d-flex align-center">
          Presence Heatmap
          <v-spacer />
          <v-chip
            v-if="!floorPlanUrl"
            color="warning"
            size="small"
            variant="tonal"
            prepend-icon="mdi-alert-outline"
          >
            No floor plan
          </v-chip>
        </v-card-title>
        <v-divider />
        <v-card-text class="pa-0">
          <div
            ref="heatmapCanvasRef"
            class="floor-plan-canvas"
            :style="{ aspectRatio: `${canvasW}/${canvasH}` }"
            @wheel.prevent="heatmapZoom.actions.onWheel"
          >
            <div
              class="floor-plan-zoom-content"
              :style="heatmapZoom.state.transformStyle"
              @mousedown="emit('canvas-mousedown', $event)"
            >
              <svg :viewBox="`0 0 ${canvasW} ${canvasH}`" class="floor-plan-svg">
                <image
                  v-if="floorPlanUrl"
                  :href="floorPlanUrl"
                  :width="canvasW"
                  :height="canvasH"
                  class="cc-floor-plan-background-image marauders-no-paint"
                />
                <g v-for="room in rooms" :key="room.id">
                  <MaraudersInkPolygon
                    v-if="maraudersEnabled && room.floor_polygon && room.floor_polygon.length >= 3"
                    :points="room.floor_polygon"
                    :canvas-w="canvasW"
                    :canvas-h="canvasH"
                    :seed-key="`room-${room.id}`"
                  />
                  <polygon
                    v-else-if="room.floor_polygon && room.floor_polygon.length >= 3"
                    :points="
                      room.floor_polygon.map(([x, y]) => `${x * canvasW},${y * canvasH}`).join(' ')
                    "
                    class="room-poly"
                  />
                </g>
                <MaraudersHeatmapLayer
                  v-if="maraudersEnabled"
                  :bins="mappedHeatmapBins"
                  :loading="heatmapState.loading"
                  :error="heatmapState.error"
                  :canvas-h="canvasH"
                />
                <HeatmapBinLayer
                  v-else
                  :bins="mappedHeatmapBins"
                  :loading="heatmapState.loading"
                  :error="heatmapState.error"
                  :canvas-h="canvasH"
                />
              </svg>
              <div
                v-if="heatmapState.loading"
                class="d-flex justify-center align-center"
                style="position: absolute; inset: 0; background: rgba(0, 0, 0, 0.25)"
              >
                <v-progress-circular indeterminate color="primary" />
              </div>
            </div>
            <CcZoomControls
              :zoom="heatmapZoom.state.zoom"
              :pan-x="heatmapZoom.state.panX"
              :pan-y="heatmapZoom.state.panY"
              :max-zoom="5"
              :min-zoom="0.3"
              @zoom-in="heatmapZoom.actions.zoomIn(heatmapCanvasRef)"
              @zoom-out="heatmapZoom.actions.zoomOut(heatmapCanvasRef)"
              @reset="heatmapZoom.actions.reset()"
            />
          </div>
        </v-card-text>
      </v-card>
    </v-col>

    <!-- Heatmap controls -->
    <v-col cols="12" md="3" class="floor-plan-sidebar">
      <v-card class="glass-card floor-plan-sidebar-card">
        <v-card-title class="floor-plan-card-title">Filters</v-card-title>
        <v-divider />
        <v-card-text>
          <v-select
            v-model="heatmapPersonId"
            :items="heatmapPersons"
            item-title="name"
            item-value="id"
            label="Person"
            variant="outlined"
            density="compact"
            hide-details
            class="mb-4"
          />
          <div class="text-caption text-medium-emphasis mb-2">Date Range</div>
          <div class="d-flex flex-wrap ga-2 mb-3">
            <v-btn
              v-for="preset in datePresets"
              :key="preset.key"
              size="x-small"
              :variant="heatmapDatePreset === preset.key ? 'flat' : 'outlined'"
              :color="heatmapDatePreset === preset.key ? 'primary' : undefined"
              @click="heatmapDatePreset = preset.key"
            >
              {{ preset.label }}
            </v-btn>
          </div>
          <template v-if="heatmapDatePreset === 'custom'">
            <v-text-field
              v-model="heatmapStartDate"
              type="date"
              label="From"
              variant="outlined"
              density="compact"
              hide-details
              class="mb-3"
            />
            <v-text-field
              v-model="heatmapEndDate"
              type="date"
              label="To"
              variant="outlined"
              density="compact"
              hide-details
              class="mb-3"
            />
          </template>

          <div class="text-caption text-medium-emphasis mb-2">
            Time of Day
            <span class="text-disabled">({{ appTzLabel }})</span>
          </div>
          <div class="d-flex flex-wrap ga-2 mb-3">
            <v-btn
              v-for="preset in timePresets"
              :key="preset.key"
              size="x-small"
              :variant="heatmapTimePreset === preset.key ? 'flat' : 'outlined'"
              :color="heatmapTimePreset === preset.key ? 'primary' : undefined"
              @click="heatmapTimePreset = preset.key"
            >
              {{ preset.label }}
            </v-btn>
          </div>
          <template v-if="heatmapTimePreset === 'custom'">
            <div class="d-flex ga-2 mb-1">
              <v-text-field
                v-model="heatmapStartTime"
                type="time"
                step="900"
                label="From"
                variant="outlined"
                density="compact"
                hide-details
              />
              <v-text-field
                v-model="heatmapEndTime"
                type="time"
                step="900"
                label="To"
                variant="outlined"
                density="compact"
                hide-details
              />
            </div>
            <div class="text-caption text-disabled mb-3">
              A "From" later than "To" spans midnight (e.g. 21:00 to 03:00 is overnight).
            </div>
          </template>
          <div v-else class="text-caption text-disabled mb-3">
            {{ heatmapTimeWindowLabel }}
          </div>

          <v-alert
            v-if="heatmapState.error"
            type="error"
            density="compact"
            variant="tonal"
            class="mb-3"
          >
            {{ heatmapState.error }}
          </v-alert>
          <v-btn
            color="primary"
            variant="flat"
            block
            :loading="heatmapState.loading"
            :disabled="!heatmapPersonId || !heatmapRangeReady || !heatmapTimeReady"
            @click="emit('generate')"
          >
            Generate
          </v-btn>
        </v-card-text>
      </v-card>
    </v-col>
  </v-row>
</template>

<script setup>
import { ref } from "vue";
import CcZoomControls from "@/components/common/CcZoomControls.vue";
import MaraudersInkPolygon from "@/components/marauders/MaraudersInkPolygon.vue";
import MaraudersHeatmapLayer from "@/components/marauders/MaraudersHeatmapLayer.vue";
import HeatmapBinLayer from "@/components/cts/floor/HeatmapBinLayer.vue";

defineProps({
  floorPlanUrl: { type: String, default: null },
  canvasW: { type: Number, required: true },
  canvasH: { type: Number, required: true },
  rooms: { type: Array, required: true },
  maraudersEnabled: { type: Boolean, default: false },
  heatmapZoom: { type: Object, required: true },
  mappedHeatmapBins: { type: Array, required: true },
  heatmapState: { type: Object, required: true },
  heatmapPersons: { type: Array, required: true },
  datePresets: { type: Array, required: true },
  timePresets: { type: Array, required: true },
  appTzLabel: { type: String, required: true },
  heatmapTimeWindowLabel: { type: String, required: true },
  heatmapRangeReady: { type: Boolean, required: true },
  heatmapTimeReady: { type: Boolean, required: true },
});
const emit = defineEmits(["canvas-mousedown", "generate"]);

const heatmapPersonId = defineModel("heatmapPersonId", { type: [String, Number], default: null });
const heatmapDatePreset = defineModel("heatmapDatePreset", { type: String, required: true });
const heatmapStartDate = defineModel("heatmapStartDate", { type: String, required: true });
const heatmapEndDate = defineModel("heatmapEndDate", { type: String, required: true });
const heatmapTimePreset = defineModel("heatmapTimePreset", { type: String, required: true });
const heatmapStartTime = defineModel("heatmapStartTime", { type: String, required: true });
const heatmapEndTime = defineModel("heatmapEndTime", { type: String, required: true });

const heatmapCanvasRef = ref(null);
</script>
