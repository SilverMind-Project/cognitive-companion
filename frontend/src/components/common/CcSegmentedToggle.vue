<!--
  CcSegmentedToggle — the DS segmented single-select picker for period/mode
  choices in page headers and table toolbars.

  Replaces v-btn-toggle, which collapses the border between adjacent buttons
  (border-inline-end: none) and visually merges them into one block; spacing
  utilities cannot fix that shared-border collapse. This renders individual
  v-btn elements in a `d-flex ga-2` row and manages active state manually, so
  each option keeps its own pill shape, hover, and focus states.

  Mandatory by nature: clicking an option selects it; there is no toggle-off.
-->
<template>
  <div class="d-flex ga-2" role="group">
    <v-btn
      v-for="opt in options"
      :key="opt.value"
      :size="size"
      :variant="modelValue === opt.value ? 'flat' : 'outlined'"
      :color="modelValue === opt.value ? color : undefined"
      :prepend-icon="opt.icon || undefined"
      :aria-pressed="modelValue === opt.value"
      @click="select(opt.value)"
    >
      {{ opt.label }}
    </v-btn>
  </div>
</template>

<script setup>
defineProps({
  modelValue: { type: [String, Number], default: null },
  // [{ value, label, icon? }]
  options: { type: Array, required: true },
  size: { type: String, default: "small" },
  // Active-option color; sage by default per DS.
  color: { type: String, default: "primary" },
});

const emit = defineEmits(["update:modelValue"]);

function select(value) {
  emit("update:modelValue", value);
}
</script>
