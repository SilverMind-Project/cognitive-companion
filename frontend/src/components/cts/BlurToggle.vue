<template>
  <v-switch
    v-model="blurMode"
    color="primary"
    label="Blur frames"
    density="compact"
    hide-details
    title="Blur camera frames to obscure faces during demos"
  />
</template>

<script setup>
import { useBlurMode } from "@/composables/useBlurMode";

const { blurMode } = useBlurMode();
</script>
