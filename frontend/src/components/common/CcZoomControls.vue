<template>
  <div class="cc-zoom-controls" @mousedown.stop @click.stop>
    <v-btn
      icon="mdi-plus"
      size="x-small"
      variant="tonal"
      density="compact"
      :disabled="zoom >= maxZoom"
      @click="$emit('zoom-in')"
    />
    <v-btn
      icon="mdi-minus"
      size="x-small"
      variant="tonal"
      density="compact"
      :disabled="zoom <= minZoom"
      @click="$emit('zoom-out')"
    />
    <v-btn
      icon="mdi-image-filter-center-focus-weak"
      size="x-small"
      variant="tonal"
      density="compact"
      :disabled="isReset"
      title="Reset zoom and pan"
      @click="$emit('reset')"
    />
    <v-chip size="x-small" variant="flat" class="cc-zoom-pct">
      {{ Math.round(zoom * 100) }}%
    </v-chip>
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
});

defineEmits(["zoom-in", "zoom-out", "reset"]);

// Use tolerance rather than exact equality — floating-point drift after
// multiple zoom/pan operations would keep the reset button permanently enabled.
const isReset = computed(
  () => Math.abs(props.zoom - 1) < 0.01 && Math.abs(props.panX) < 1 && Math.abs(props.panY) < 1
);
</script>
