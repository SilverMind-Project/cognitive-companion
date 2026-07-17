<template>
  <div class="cc-zoom-controls" @mousedown.stop @click.stop>
    <v-btn
      icon="mdi-plus"
      size="x-small"
      variant="tonal"
      :disabled="zoom >= maxZoom"
      title="Zoom in"
      @click="$emit('zoom-in')"
    />
    <v-btn
      icon="mdi-minus"
      size="x-small"
      variant="tonal"
      :disabled="zoom <= minZoom"
      title="Zoom out"
      @click="$emit('zoom-out')"
    />
    <v-btn
      icon="mdi-image-filter-center-focus-weak"
      size="x-small"
      variant="tonal"
      :disabled="isReset"
      title="Reset zoom and pan"
      @click="$emit('reset')"
    />
    <v-btn
      v-if="showFit"
      icon="mdi-fit-to-screen-outline"
      size="x-small"
      variant="tonal"
      title="Fit to view"
      @click="$emit('fit')"
    />
    <v-btn
      v-if="showFullscreen"
      icon="mdi-fullscreen"
      size="x-small"
      variant="tonal"
      title="Fullscreen"
      @click="$emit('fullscreen')"
    />
    <v-chip size="small" variant="flat" class="cc-zoom-pct"> {{ Math.round(zoom * 100) }}% </v-chip>
  </div>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  zoom: { type: Number, required: true },
  panX: { type: Number, default: 0 },
  panY: { type: Number, default: 0 },
  minZoom: { type: Number, default: 0.2 },
  maxZoom: { type: Number, default: 6 },
  showFit: { type: Boolean, default: false },
  showFullscreen: { type: Boolean, default: false },
});

defineEmits(["zoom-in", "zoom-out", "reset", "fit", "fullscreen"]);

// Use tolerance rather than exact equality because floating-point drift after
// multiple zoom operations can otherwise leave reset permanently enabled.
const isReset = computed(
  () => Math.abs(props.zoom - 1) < 0.01 && Math.abs(props.panX) < 1 && Math.abs(props.panY) < 1,
);
</script>
