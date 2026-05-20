<template>
  <div class="mb-4">
    <div class="d-flex align-center ga-2 mb-2">
      <v-icon size="16" color="medium-emphasis">mdi-information-outline</v-icon>
      <span class="text-caption font-weight-medium text-uppercase">Track Summary</span>
    </div>
    <div class="d-flex flex-wrap ga-2">
      <v-chip size="x-small" variant="tonal" prepend-icon="mdi-clock-outline">
        {{ durationText }}
      </v-chip>
      <v-chip
        v-for="cam in cameras"
        :key="cam.camera_id"
        size="x-small"
        variant="tonal"
        prepend-icon="mdi-cctv"
      >
        {{ cam.camera_id }}: {{ formatDuration(cam.dwell_seconds) }}
      </v-chip>
    </div>
    <div class="d-flex flex-wrap ga-2 mt-1" v-if="lastSeenText">
      <v-chip size="x-small" variant="tonal" prepend-icon="mdi-eye-outline">
        Last seen {{ lastSeenText }}
      </v-chip>
    </div>
  </div>
</template>

<script>
import { formatRelative } from "@/composables/useFormatRelative";

export default {
  name: "TrackSummaryHeader",
  props: {
    track: { type: Object, required: true },
  },
  computed: {
    durationText() {
      const ts = this.track.started_at || this.track.first_seen_at;
      if (!ts) return "—";
      const started = new Date(ts);
      const ended = this.track.last_seen_at ? new Date(this.track.last_seen_at) : new Date();
      const sec = Math.round((ended - started) / 1000);
      return this.formatDuration(sec);
    },
    cameras() {
      return this.track.cameras || [];
    },
    lastSeenText() {
      if (!this.track.last_seen_at) return "";
      return formatRelative(this.track.last_seen_at);
    },
  },
  methods: {
    formatDuration(sec) {
      if (sec == null) return "—";
      if (sec < 60) return `${sec}s`;
      const min = Math.floor(sec / 60);
      if (min < 60) return `${min}m`;
      const hr = Math.floor(min / 60);
      const rem = min % 60;
      return rem ? `${hr}h ${rem}m` : `${hr}h`;
    },
  },
};
</script>
