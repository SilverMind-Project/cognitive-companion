<template>
  <v-card-text class="d-flex flex-wrap ga-3 align-center pa-4 live-toolbar">
    <v-select
      v-model="layout"
      :items="layoutOptions"
      item-title="label"
      item-value="value"
      label="Layout"
      variant="outlined"
      density="compact"
      hide-details
      style="max-width: 200px"
    />
    <v-switch
      v-model="showBboxes"
      color="primary"
      label="Bboxes"
      density="compact"
      hide-details
    />
    <v-switch
      v-model="showIdLabels"
      color="primary"
      label="Labels"
      density="compact"
      hide-details
    />
    <v-switch v-model="showTrail" color="primary" label="Trail" density="compact" hide-details />
    <v-switch v-model="showPose" color="primary" label="Pose" density="compact" hide-details />
    <v-switch
      v-model="showEvidence"
      color="primary"
      label="Evidence"
      density="compact"
      hide-details
    />
    <v-switch
      v-model="showPosture"
      color="primary"
      label="Posture"
      density="compact"
      hide-details
    />
    <BlurToggle />
  </v-card-text>
</template>

<script setup>
import BlurToggle from "@/components/cts/BlurToggle.vue";

defineProps({
  layoutOptions: { type: Array, required: true },
});

const layout = defineModel("layout", { type: Number, required: true });
const showBboxes = defineModel("showBboxes", { type: Boolean, required: true });
const showIdLabels = defineModel("showIdLabels", { type: Boolean, required: true });
const showTrail = defineModel("showTrail", { type: Boolean, required: true });
const showPose = defineModel("showPose", { type: Boolean, required: true });
const showEvidence = defineModel("showEvidence", { type: Boolean, required: true });
const showPosture = defineModel("showPosture", { type: Boolean, required: true });
</script>
