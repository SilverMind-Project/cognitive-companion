<template>
  <g :transform="`translate(${x}, ${y})`" @click="$emit('click', signal)" style="cursor: pointer;">
    <circle r="5" :fill="dotColor" stroke="var(--cc-bg)" stroke-width="1.5" />
    <title>{{ signal.kind.replace(/_/g, ' ') }} at {{ formatTimeOnly(signal.fired_at) }}</title>
  </g>
</template>

<script setup>
import { computed } from "vue";
import { formatTimeOnly } from "@/services/timezone.js";
import { useCtsSeverity } from "@/composables/useCtsSeverity";

const props = defineProps({
  signal: { type: Object, required: true },
  x: { type: Number, required: true },
  y: { type: Number, default: 0 },
});
defineEmits(["click"]);

const { severityColor } = useCtsSeverity();
const dotColor = computed(() => severityColor(props.signal.severity));
</script>
