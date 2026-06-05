<template>
  <g
    class="marauders-footprint-glyph"
    :transform="transform"
    :opacity="opacity"
    :fill="fill"
    aria-hidden="true"
  >
    <g :transform="mirrored ? 'scale(-1 1)' : undefined">
      <use :href="`${footstepUrl}#marauders-footstep`" />
    </g>
  </g>
</template>

<script setup>
import footstepUrl from "@/assets/marauders/footstep.svg?no-inline";

defineProps({
  transform: { type: String,  default: undefined },
  opacity:   { type: Number,  default: undefined },
  fill:      { type: String,  default: "currentColor" },
  mirrored:  { type: Boolean, default: false },
});
</script>
