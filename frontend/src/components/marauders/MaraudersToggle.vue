<template>
  <v-btn
    :icon="state.enabled ? 'mdi-map-marker-path' : 'mdi-script-outline'"
    :color="state.enabled ? 'primary' : undefined"
    variant="text"
    size="small"
    :title="label"
    :aria-label="label"
    @click="actions.toggle()"
  />
</template>

<script setup>
import { computed } from "vue";
import { useMaraudersMode } from "@/composables/useMaraudersMode.js";

const { state, actions } = useMaraudersMode();

const label = computed(() =>
  state.enabled ? "Disable Marauder's Map mode" : "Enable Marauder's Map mode"
);
</script>
