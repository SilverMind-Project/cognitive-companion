<template>
  <v-card variant="tonal" class="pa-4 mt-4">
    <div class="d-flex align-center justify-space-between flex-wrap ga-2 mb-3">
      <div>
        <div class="text-subtitle-2">Face resolution &amp; placement calculator</div>
        <div class="text-caption text-medium-emphasis">
          Expected frontal interocular distance (pinhole approximation, computed by the server).
        </div>
      </div>
      <v-chip
        v-if="observedWidthPx && observedHeightPx"
        size="small"
        variant="outlined"
        prepend-icon="mdi-monitor-screenshot"
      >
        Observed stream: {{ observedWidthPx }} × {{ observedHeightPx }} px
      </v-chip>
      <v-chip v-else size="small" variant="outlined" prepend-icon="mdi-monitor-off">
        Stream size not yet observed from CTS
      </v-chip>
    </div>

    <v-alert
      v-if="optics?.stream_size_mismatch"
      type="warning"
      variant="tonal"
      density="compact"
      class="mb-3"
    >
      Live stream resolution ({{ optics.observed_stream_width }} ×
      {{ optics.observed_stream_height }} px) differs from the saved calibration dimensions ({{
        optics.frame_natural_width
      }}
      × {{ optics.frame_natural_height }} px). Recalibrate if the camera stream changed.
    </v-alert>

    <v-row v-if="!observedWidthPx" dense class="mb-2">
      <v-col cols="12" sm="6">
        <v-text-field
          :model-value="previewWidthPx"
          label="Preview stream width (px, not saved)"
          type="number"
          min="320"
          max="7680"
          step="160"
          density="compact"
          clearable
          hint="Used only for this preview until CTS observes the first frame (e.g. 2560 for 4 MP)."
          persistent-hint
          @update:model-value="onPreviewWidthChange"
        />
      </v-col>
    </v-row>

    <div v-if="loading" class="d-flex align-center ga-2 py-2">
      <v-progress-circular indeterminate size="18" width="2" />
      <span class="text-body-2 text-medium-emphasis">Calculating optics...</span>
    </div>

    <v-alert v-else-if="error" type="error" variant="tonal" density="compact">
      {{ error }}
    </v-alert>

    <div v-else-if="optics && optics.distances && optics.distances.length > 0">
      <div class="d-flex flex-wrap ga-4 mb-3 text-body-2">
        <div>
          <span class="text-medium-emphasis">Derived focal length:</span>
          <strong class="ml-1">{{ formatNum(optics.focal_length_px, 0) }} px</strong>
        </div>
        <div>
          <span class="text-medium-emphasis">Good face range (≥ 24 px):</span>
          <strong class="ml-1">up to {{ formatNum(optics.distance_for_24px_m, 2) }} m</strong>
        </div>
      </div>

      <v-table density="compact">
        <thead>
          <tr>
            <th>Distance (m)</th>
            <th>Expected interocular (px)</th>
            <th>Band</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in optics.distances" :key="row.distance_m">
            <td>{{ row.distance_m }} m</td>
            <td>{{ formatNum(row.interocular_px, 1) }} px</td>
            <td>
              <v-chip :color="bandColor(row.band)" size="x-small" variant="tonal">
                {{ bandLabel(row.band) }}
              </v-chip>
            </td>
          </tr>
        </tbody>
      </v-table>

      <div
        v-if="optics.bands && optics.bands.length > 0"
        class="text-caption text-medium-emphasis mt-2"
      >
        Bands:
        <span v-for="(b, idx) in optics.bands" :key="b.band">
          {{ idx > 0 ? " · " : "" }}{{ bandLabel(b.band) }} ({{ formatBandRange(b) }})
        </span>
      </div>
    </div>

    <div v-else class="text-body-2 text-medium-emphasis">
      Enter horizontal FOV (and a preview stream width if CTS has not observed frames yet) to
      estimate interocular face pixels by distance.
    </div>
  </v-card>
</template>

<script setup>
defineProps({
  optics: {
    type: Object,
    default: null,
  },
  loading: {
    type: Boolean,
    default: false,
  },
  error: {
    type: String,
    default: null,
  },
  observedWidthPx: {
    type: Number,
    default: null,
  },
  observedHeightPx: {
    type: Number,
    default: null,
  },
  previewWidthPx: {
    type: Number,
    default: null,
  },
});

const emit = defineEmits(["update:previewWidthPx"]);

const BAND_COLORS = {
  poor: "error",
  marginal: "warning",
  good: "info",
  excellent: "success",
};

const BAND_LABELS = {
  poor: "Poor",
  marginal: "Marginal",
  good: "Good",
  excellent: "Excellent",
};

function bandColor(band) {
  return BAND_COLORS[band] ?? "default";
}

function bandLabel(band) {
  return BAND_LABELS[band] ?? band;
}

function formatNum(value, digits) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return Number(value).toFixed(digits);
}

function formatBandRange(spec) {
  if (spec.min_px == null && spec.max_px != null) return `< ${spec.max_px} px`;
  if (spec.min_px != null && spec.max_px == null) return `≥ ${spec.min_px} px`;
  return `${spec.min_px}–${spec.max_px} px`;
}

function onPreviewWidthChange(raw) {
  if (raw === "" || raw == null) {
    emit("update:previewWidthPx", null);
    return;
  }
  const parsed = Number(raw);
  emit("update:previewWidthPx", Number.isFinite(parsed) && parsed > 0 ? Math.round(parsed) : null);
}
</script>
