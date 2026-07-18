<template>
  <div class="floor-plan-header d-flex align-start flex-wrap ga-3 mb-4">
    <div>
      <h2
        :class="embedded ? 'text-h6' : 'floor-plan-page-title'"
        class="font-weight-bold tracking-tight"
      >
        Floor Plan
      </h2>
      <div class="floor-plan-page-subtitle text-medium-emphasis mt-1">
        Upload a floor plan image and draw room polygons. Active people appear as dots in real time.
      </div>
    </div>
    <v-spacer />
    <div class="floor-plan-mode-nav d-flex flex-wrap justify-end ga-2">
      <v-btn
        size="small"
        :variant="modelValue === 'live' ? 'flat' : 'outlined'"
        :color="modelValue === 'live' ? 'primary' : undefined"
        @click="emit('update:modelValue', 'live')"
      >
        Live
      </v-btn>
      <v-btn
        size="small"
        :variant="modelValue === 'heatmap' ? 'flat' : 'outlined'"
        :color="modelValue === 'heatmap' ? 'primary' : undefined"
        @click="emit('update:modelValue', 'heatmap')"
      >
        Heatmap
      </v-btn>
      <v-btn
        size="small"
        :variant="modelValue === 'edit' ? 'flat' : 'outlined'"
        :color="modelValue === 'edit' ? 'primary' : undefined"
        @click="emit('update:modelValue', 'edit')"
      >
        Edit Rooms
      </v-btn>
      <v-btn
        size="small"
        :variant="modelValue === 'upload' ? 'flat' : 'outlined'"
        :color="modelValue === 'upload' ? 'primary' : undefined"
        @click="emit('update:modelValue', 'upload')"
      >
        Floor Plan
      </v-btn>
      <v-btn
        size="small"
        :variant="modelValue === 'coverage' ? 'flat' : 'outlined'"
        :color="modelValue === 'coverage' ? 'primary' : undefined"
        @click="emit('update:modelValue', 'coverage')"
      >
        Coverage
      </v-btn>
      <v-btn
        size="small"
        :variant="modelValue === 'doors' ? 'flat' : 'outlined'"
        :color="modelValue === 'doors' ? 'primary' : undefined"
        @click="emit('update:modelValue', 'doors')"
      >
        Door Zones
      </v-btn>
      <MaraudersToggle />
    </div>
  </div>
</template>

<script setup>
import MaraudersToggle from "@/components/marauders/MaraudersToggle.vue";

defineProps({
  modelValue: { type: String, required: true },
  embedded: { type: Boolean, default: false },
});
const emit = defineEmits(["update:modelValue"]);
</script>

<style scoped>
.floor-plan-header {
  min-width: 0;
}

.floor-plan-page-title {
  font-size: clamp(1.6rem, 2vw, 1.8rem);
  line-height: 1.15;
}

.floor-plan-page-subtitle {
  max-width: 680px;
  font-size: 0.8125rem;
  line-height: 1.45;
}

.floor-plan-mode-nav {
  max-width: 100%;
}

@media (max-width: 959px) {
  .floor-plan-header .v-spacer {
    display: none;
  }

  .floor-plan-mode-nav {
    width: 100%;
    justify-content: flex-start !important;
  }
}
</style>
