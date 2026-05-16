<template>
  <div class="mb-4">
    <div class="d-flex align-center ga-2 mb-2">
      <v-icon size="16" color="medium-emphasis">mdi-account-group</v-icon>
      <span class="text-caption font-weight-medium text-uppercase">Co-occurring Tracks</span>
    </div>
    <div v-if="tracks.length">
      <div
        v-for="t in tracks"
        :key="t.global_track_id"
        class="d-flex align-center ga-2 py-1"
      >
        <v-chip
          :color="t.current_identity_id ? 'success' : 'warning'"
          size="x-small"
          variant="tonal"
        >
          {{ t.current_identity_id || "UNKNOWN" }}
        </v-chip>
        <span class="text-caption text-medium-emphasis font-mono">
          {{ t.global_track_id.slice(0, 8) }}…
        </span>
      </div>
    </div>
    <span v-else class="text-caption text-medium-emphasis">No other tracks in same cameras</span>
  </div>
</template>

<script>
export default {
  name: "CoOccurringPanel",
  props: {
    tracks: { type: Array, default: () => [] },
  },
};
</script>
