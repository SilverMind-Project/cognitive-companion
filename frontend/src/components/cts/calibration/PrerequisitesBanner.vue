<template>
  <v-card class="glass-card mb-5">
    <v-card-text class="py-3">
      <div class="text-caption text-medium-emphasis mb-2 font-weight-medium">
        SETUP PREREQUISITES
      </div>
      <div class="d-flex flex-wrap ga-3 align-center">
        <span>Floor plan image</span>
        <div class="prereq-item" :class="floorPlanReady ? 'prereq-ok' : 'prereq-warn'">
          <v-icon size="16" :color="floorPlanReady ? 'success' : 'warning'">
            {{ floorPlanReady ? "mdi-check-circle" : "mdi-alert-circle-outline" }}
          </v-icon>
        </div>
        <div class="prereq-item" :class="scaleReady ? 'prereq-ok' : 'prereq-warn'">
          <v-icon size="16" :color="scaleReady ? 'success' : 'warning'">
            {{ scaleReady ? "mdi-check-circle" : "mdi-alert-circle-outline" }}
          </v-icon>
          <span>Scale set ({{ scaleReady ? `${fpMpp} m/px` : "missing" }})</span>
        </div>
        <div
          class="prereq-item"
          :class="selectedCameraId ? (existingCalibration ? 'prereq-ok' : 'prereq-none') : 'prereq-none'"
        >
          <v-icon size="16" :color="existingCalibration ? 'success' : 'default'">
            {{ existingCalibration ? "mdi-check-circle" : "mdi-circle-outline" }}
          </v-icon>
          <span>{{
            selectedCameraId
              ? existingCalibration
                ? "Camera calibrated"
                : "Camera not yet calibrated"
              : "Select a camera"
          }}</span>
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
</template>

<script setup>
defineProps({
  floorPlanReady: { type: Boolean, required: true },
  scaleReady: { type: Boolean, required: true },
  fpMpp: { type: Number, default: null },
  selectedCameraId: { type: String, default: null },
  existingCalibration: { type: Boolean, required: true },
});
</script>

<style scoped>
.prereq-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  padding: 4px 8px;
  border-radius: 6px;
}

.prereq-ok {
  background: var(--good-bg);
  color: var(--good-fg);
}

.prereq-warn {
  background: var(--notice-bg);
  color: var(--notice-fg);
}

.prereq-none {
  background: var(--cc-surface-2);
  color: var(--cc-text-3);
}
</style>
