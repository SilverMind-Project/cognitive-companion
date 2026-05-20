<template>
  <div>
    <div class="d-flex align-center ga-2 mb-3">
      <v-icon color="warning" size="18">mdi-account-question</v-icon>
      <span class="text-body-2 font-weight-medium">Unidentified sightings</span>
      <v-chip size="x-small" color="warning" variant="tonal">{{ tracks.length }}</v-chip>
    </div>

    <div v-if="!tracks.length" class="text-center py-6">
      <v-icon size="36" color="success" class="mb-2">mdi-check-circle-outline</v-icon>
      <div class="text-body-2 text-medium-emphasis">All active sightings are identified</div>
    </div>

    <div v-else class="unknown-grid">
      <div
        v-for="track in tracks"
        :key="track.global_track_id"
        class="unknown-card"
      >
        <!-- Thumbnail -->
        <div class="unknown-thumb-wrap" @click="$emit('open-track', track)">
          <v-img
            v-if="track.latest_keyframe_minio_key"
            :src="displaySrc(frameUrl(track.latest_keyframe_minio_key))"
            aspect-ratio="4/3"
            cover
            class="unknown-thumb"
          />
          <v-sheet
            v-else
            class="unknown-thumb d-flex align-center justify-center"
            color="surface-variant"
          >
            <v-icon size="28" color="medium-emphasis">mdi-account-outline</v-icon>
          </v-sheet>
          <!-- Duration badge -->
          <div class="duration-badge">{{ trackDuration(track) }}</div>
          <!-- Camera badge -->
          <div v-if="(track.camera_ids || []).length" class="camera-badge">
            <v-icon size="10">mdi-cctv</v-icon>
            {{ track.camera_ids[0] }}
          </div>
        </div>

        <!-- Quick assign -->
        <div class="pa-1">
          <v-select
            v-model="assignments[track.global_track_id]"
            :items="identityItems"
            item-value="identity_id"
            item-title="label"
            label="Who is this?"
            variant="outlined"
            density="compact"
            hide-details
            clearable
            :loading="saving[track.global_track_id]"
            @update:model-value="(val) => assign(track, val)"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { useBlurMode, useDisplaySrc } from "@/composables/useBlurMode";

export default {
  name: "UnknownTracksPanel",

  setup() {
    const { blurMode } = useBlurMode();
    const { displaySrc } = useDisplaySrc(blurMode);
    return { displaySrc };
  },

  props: {
    tracks: { type: Array, default: () => [] },
    identities: { type: Array, default: () => [] },
  },

  emits: ["open-track", "assigned"],

  data() {
    return {
      assignments: {},
      saving: {},
    };
  },

  computed: {
    identityItems() {
      return this.identities.map((id) => ({
        identity_id: id.identity_id,
        label: id.display_name || id.identity_id,
      }));
    },
  },

  methods: {
    frameUrl(minioKey) {
      if (!minioKey) return "";
      const encodedKey = minioKey.split("/").map(encodeURIComponent).join("/");
      const apiKey = encodeURIComponent(localStorage.getItem("cc_api_key") || "");
      return `/api/v1/cts/frames/${encodedKey}?api_key=${apiKey}`;
    },
    trackDuration(track) {
      if (!track.started_at) return "—";
      const s = Math.round(
        ((track.last_seen_at ? new Date(track.last_seen_at) : new Date()) -
          new Date(track.started_at)) /
          1000
      );
      if (s < 60) return `${s}s`;
      const m = Math.floor(s / 60);
      if (m < 60) return `${m}m`;
      return `${Math.floor(m / 60)}h${m % 60 ? " " + (m % 60) + "m" : ""}`;
    },
    async assign(track, identityId) {
      if (!identityId) return;
      this.saving = { ...this.saving, [track.global_track_id]: true };
      try {
        this.$emit("assigned", { track, identity_id: identityId });
      } finally {
        // Parent controls reload; clear saving state after a short delay.
        setTimeout(() => {
          this.saving = { ...this.saving, [track.global_track_id]: false };
        }, 800);
      }
    },
  },
};
</script>

<style scoped>
.unknown-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 10px;
}

.unknown-card {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 10px;
  overflow: hidden;
  background: rgba(var(--v-theme-surface), 1);
  transition: border-color 0.15s;
}

.unknown-card:hover {
  border-color: rgba(var(--v-theme-primary), 0.5);
}

.unknown-thumb-wrap {
  position: relative;
  cursor: pointer;
}

.unknown-thumb {
  width: 100%;
  aspect-ratio: 4 / 3;
}

.duration-badge {
  position: absolute;
  bottom: 4px;
  right: 4px;
  background: rgba(0, 0, 0, 0.6);
  color: white;
  font-size: 9px;
  padding: 1px 4px;
  border-radius: 4px;
  line-height: 1.4;
}

.camera-badge {
  position: absolute;
  top: 4px;
  left: 4px;
  background: rgba(0, 0, 0, 0.55);
  color: white;
  font-size: 9px;
  padding: 1px 4px;
  border-radius: 4px;
  line-height: 1.4;
  display: flex;
  align-items: center;
  gap: 2px;
}
</style>
