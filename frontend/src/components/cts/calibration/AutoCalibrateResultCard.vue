<template>
  <v-card class="mt-3">
    <v-card-title class="d-flex align-center">
      <v-icon start size="18">mdi-auto-fix</v-icon>
      <span>Auto-calibrate Result</span>
      <v-spacer />
      <v-chip
        :color="
          autoResult.confidence >= 0.6
            ? 'success'
            : autoResult.confidence >= 0.4
              ? 'warning'
              : 'error'
        "
        size="small"
      >
        {{ Math.round(autoResult.confidence * 100) }}% confidence
      </v-chip>
    </v-card-title>
    <v-card-text>
      <div class="text-body-2 mb-1">
        <strong>{{ autoResult.inlier_count }}</strong> of
        <strong>{{ autoResult.sample_count }}</strong> floor points used &nbsp;·&nbsp; FoV:
        <strong>{{ autoResult.fov_deg }}°</strong>
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
        This draft found {{ autoResult.suggested_points?.length || 0 }} candidate floor pixels. It
        has not been saved as calibration. Refine manually by anchoring the suggested camera points
        to the floor plan.
      </div>
    </v-card-text>
    <v-card-actions class="px-4 pb-4 pt-0">
      <v-btn variant="text" size="small" @click="$emit('dismiss')">Dismiss</v-btn>
      <v-spacer />
      <v-btn
        color="primary"
        variant="tonal"
        size="small"
        prepend-icon="mdi-pencil"
        @click="$emit('refine')"
      >
        Refine manually
      </v-btn>
    </v-card-actions>
  </v-card>
</template>

<script setup>
defineProps({
  autoResult: { type: Object, required: true },
});
defineEmits(["dismiss", "refine"]);
</script>
