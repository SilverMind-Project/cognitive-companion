<template>
  <div class="cc-provenance d-inline-flex align-center ga-1">
    <!-- Source badge -->
    <v-chip
      :prepend-icon="sourceConfig.icon"
      :color="sourceConfig.color"
      size="x-small"
      variant="tonal"
      :title="sourceConfig.description"
    >
      {{ sourceConfig.label }}
    </v-chip>

    <!-- Quality indicator: always shows a value or explicit "unknown" (D5/rule 15) -->
    <v-chip
      size="x-small"
      :color="qualityColor"
      variant="tonal"
      :title="qualityTitle"
    >
      <v-icon icon="mdi-signal" size="10" class="mr-1" />
      {{ qualityDisplay }}
    </v-chip>
  </div>
</template>

<script setup>
import { computed } from "vue";

/**
 * Renders the envelope `source` enum and `quality` as a compact provenance
 * badge. This is the visible expression of D5: every datum shows where it came
 * from and how trustworthy it is.
 *
 * Rule 15: a missing quality renders as an explicit "unknown" state.
 * It is NEVER fabricated or inferred client-side.
 */
const props = defineProps({
  /**
   * Canonical provenance source from PersonLocationEnvelope.
   * One of: 'observation' | 'transition' | 'manual_override' | 'ph_continuation'
   */
  source: {
    type: String,
    default: null,
    validator: (v) =>
      v === null ||
      ["observation", "transition", "manual_override", "ph_continuation"].includes(v),
  },
  /**
   * Data quality score in [0, 1]. Pass null / undefined when the score is
   * genuinely unknown — the badge will render "unknown", never a made-up value.
   */
  quality: {
    type: Number,
    default: null,
  },
});

const SOURCE_CONFIGS = {
  observation: {
    label: "Observed",
    icon: "mdi-eye",
    color: "success",
    description: "Directly observed by a camera",
  },
  transition: {
    label: "Transit",
    icon: "mdi-transit-transfer",
    color: "info",
    description: "Inferred during room transition",
  },
  manual_override: {
    label: "Manual",
    icon: "mdi-account-edit",
    color: "warning",
    description: "Manually overridden by staff",
  },
  ph_continuation: {
    label: "Continuation",
    icon: "mdi-history",
    color: "secondary",
    description: "Continued from prior physical hypothesis",
  },
};

const UNKNOWN_CONFIG = {
  label: "Unknown",
  icon: "mdi-help-circle",
  color: "default",
  description: "Source unknown",
};

const sourceConfig = computed(
  () => SOURCE_CONFIGS[props.source] ?? UNKNOWN_CONFIG
);

// Quality is null/undefined → explicit "unknown", never a fabricated number.
const qualityDisplay = computed(() => {
  if (props.quality === null || props.quality === undefined) return "unknown";
  return `${Math.round(props.quality * 100)}%`;
});

const qualityTitle = computed(() =>
  props.quality === null || props.quality === undefined
    ? "Quality score not available"
    : `Quality: ${(props.quality * 100).toFixed(1)}%`
);

const qualityColor = computed(() => {
  if (props.quality === null || props.quality === undefined) return "default";
  if (props.quality >= 0.8) return "success";
  if (props.quality >= 0.5) return "warning";
  return "error";
});

defineExpose({ sourceConfig, qualityDisplay, qualityColor, qualityTitle });
</script>

<style scoped>
.cc-provenance {
  flex-wrap: wrap;
}
</style>
