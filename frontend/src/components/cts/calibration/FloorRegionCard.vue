<template>
  <v-card class="mt-3">
    <v-card-title class="d-flex align-center">
      <v-icon start size="18" color="success">mdi-floor-plan</v-icon>
      <span>Floor Region</span>
      <v-spacer />
      <v-chip size="small" color="success" variant="tonal">
        {{ floorRegionDraft.length }} vertices
      </v-chip>
    </v-card-title>
    <v-card-text class="pb-1">
      <div class="text-body-2 mb-2">
        The green polygon on the camera image shows the detected floor area. Drag vertices to
        adjust, then save.
      </div>
      <div class="text-caption text-medium-emphasis">
        Coordinate space: normalised image [0,1] — same as the visibility polygon, NOT floor-plan
        metres.
      </div>
    </v-card-text>
    <v-card-actions class="px-4 pb-4 pt-0">
      <v-btn variant="text" size="small" @click="$emit('discard')">Discard</v-btn>
      <v-spacer />
      <v-btn
        color="success"
        variant="flat"
        size="small"
        prepend-icon="mdi-content-save"
        :loading="saving"
        @click="$emit('save')"
      >
        Save Region
      </v-btn>
    </v-card-actions>
  </v-card>
</template>

<script setup>
defineProps({
  floorRegionDraft: { type: Array, required: true },
  saving: { type: Boolean, required: true },
});
defineEmits(["discard", "save"]);
</script>
