<template>
  <v-chip
    :color="meta.color"
    :prepend-icon="meta.icon"
    :variant="variant"
    :density="density"
    :size="size"
    :aria-label="`Status: ${meta.label}`"
  >
    {{ meta.label }}
  </v-chip>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  status: { type: String, required: true },
  variant: { type: String, default: "tonal" },
  density: { type: String, default: "default" },
  size: { type: String, default: "small" },
});

const STATUS_META = {
  present_room: { label: "In room",  color: "success",          icon: "mdi-map-marker" },
  present_home: { label: "At home",  color: "info",             icon: "mdi-home" },
  asleep:       { label: "Asleep",   color: "purple",           icon: "mdi-sleep" },
  stale:        { label: "Stale",    color: "grey-darken-1",    icon: "mdi-clock-alert-outline" },
  away:         { label: "Away",     color: "orange",           icon: "mdi-walk" },
  unknown:      { label: "Unknown",  color: "grey",             icon: "mdi-help-circle" },
};

const meta = computed(() => STATUS_META[props.status] || STATUS_META.unknown);
</script>
