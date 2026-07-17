<template>
  <div class="px-4 pb-3 pt-1">
    <v-divider class="mb-2" />
    <div class="d-flex align-center ga-2 mb-2">
      <v-icon size="18" color="primary">mdi-camera-flip-outline</v-icon>
      <span class="text-body-2 font-weight-medium">Cross-camera activity</span>
      <v-chip size="x-small" color="primary" variant="flat" density="compact">
        {{ entries.length }}
        {{ entries.length > 1 ? "identities" : "identity" }}
      </v-chip>
    </div>
    <div class="d-flex flex-wrap ga-2">
      <v-chip
        v-for="entry in entries"
        :key="entry.identity_id"
        size="small"
        :color="entry.color"
        variant="outlined"
      >
        <template #prepend>
          <v-icon size="14" :color="entry.color">mdi-camera</v-icon>
        </template>
        <span class="font-weight-medium">{{ entry.identity_id }}</span>
        <v-chip size="x-small" variant="flat" :color="entry.color" class="ml-1" density="compact">
          {{ entry.cameraCount }} cam{{ entry.cameraCount > 1 ? "s" : "" }}
        </v-chip>
      </v-chip>
    </div>
  </div>
</template>

<script setup>
defineProps({
  entries: { type: Array, required: true },
});
</script>
