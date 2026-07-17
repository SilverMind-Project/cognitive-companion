<template>
  <v-card class="mb-4">
    <v-card-title class="d-flex align-center">
      <span>Point Correspondences</span>
      <v-spacer />
      <v-chip size="x-small" :color="points.length >= 4 ? 'success' : 'default'">
        {{ points.length }}/4{{ points.length > 4 ? "+" : "" }}
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
          <v-btn icon="mdi-close" size="x-small" variant="text" @click="$emit('remove', i)" />
        </div>
        <!-- Show floor coords as read-only in pick mode, editable in manual mode -->
        <template v-if="pickModeActive">
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
      <v-btn variant="text" :disabled="points.length === 0" size="small" @click="$emit('clear')">
        Clear All
      </v-btn>
      <v-spacer />
      <v-btn
        color="primary"
        variant="flat"
        :loading="calibrating"
        :disabled="points.length < 4"
        @click="$emit('calibrate')"
      >
        Calibrate
      </v-btn>
    </v-card-actions>
  </v-card>
</template>

<script setup>
defineProps({
  pickModeActive: { type: Boolean, required: true },
  calibrating: { type: Boolean, required: true },
});
defineEmits(["remove", "clear", "calibrate"]);

const points = defineModel("points", { type: Array, required: true });
</script>

<style scoped>
.point-row {
  background: var(--cc-surface-2, rgba(0, 0, 0, 0.03));
  border-radius: 8px;
  padding: 8px 10px 10px;
}
</style>
