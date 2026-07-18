<template>
  <v-card>
    <v-card-title class="d-flex align-center">
      <span>Result</span>
      <v-spacer />
      <v-chip
        :color="
          result.status === 'ok' ? 'success' : result.status === 'warning' ? 'warning' : 'error'
        "
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
        This is how far off the computed transform is at its worst calibration point. Under 0.1 m is
        good; over 0.3 m means the points were poorly placed or measured.
      </div>
      <v-table density="compact">
        <thead>
          <tr>
            <th>Point</th>
            <th>Error (m)</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(r, i) in result.residuals_m" :key="i">
            <td>{{ i + 1 }}</td>
            <td>{{ r.toFixed(4) }}</td>
            <td>
              <v-chip size="x-small" :color="r < 0.05 ? 'success' : r < 0.15 ? 'warning' : 'error'">
                {{ r < 0.05 ? "excellent" : r < 0.15 ? "acceptable" : "poor" }}
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
          {{
            result.visibility_polygon_warning ||
            "Visibility polygon could not be computed from this homography."
          }}
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
        Tip: re-calibrate with more spread-out points and re-measure carefully. Points with a "poor"
        rating are dragging down accuracy — try replacing them.
      </div>
    </v-card-text>
  </v-card>
</template>

<script setup>
defineProps({
  result: { type: Object, required: true },
});
</script>
