<template>
  <v-card variant="flat" border rounded="lg" class="person-track-card">
    <div class="d-flex align-center ga-3 pa-3 pb-2">
      <!-- Avatar -->
      <v-avatar :color="avatarColor" size="40">
        <span class="text-body-2 font-weight-bold" style="color: white">
          {{ initials }}
        </span>
      </v-avatar>

      <!-- Name + status -->
      <div class="flex-grow-1 min-width-0">
        <div class="d-flex align-center ga-2">
          <span class="text-body-1 font-weight-medium text-truncate">{{ identity.display_name || identity.identity_id }}</span>
          <v-chip
            v-if="isActive"
            color="success"
            size="x-small"
            variant="flat"
          >
            active
          </v-chip>
        </div>
        <div class="text-caption text-medium-emphasis">
          {{ segmentSummary }}
        </div>
      </div>

      <!-- Actions -->
      <div class="d-flex align-center ga-1">
        <v-btn
          v-if="fragmentCount > 1"
          size="x-small"
          variant="tonal"
          color="warning"
          prepend-icon="mdi-merge"
          @click="$emit('merge-fragments', tracks)"
        >
          Merge {{ fragmentCount }}
        </v-btn>
        <v-btn
          icon="mdi-chevron-down"
          size="x-small"
          variant="text"
          :class="{ 'rotate-180': expanded }"
          @click="expanded = !expanded"
        />
      </div>
    </div>

    <!-- Timeline strip -->
    <div class="px-3 pb-2">
      <div class="timeline-outer">
        <!-- Hour markers -->
        <div class="timeline-hours">
          <span
            v-for="h in visibleHours"
            :key="h"
            class="timeline-hour-label"
            :style="{ left: hourPct(h) + '%' }"
          >{{ h }}:00</span>
        </div>
        <!-- Track segments -->
        <div class="timeline-bar">
          <div
            v-for="seg in timelineSegments"
            :key="seg.id"
            class="timeline-seg"
            :style="{
              left: seg.left + '%',
              width: Math.max(seg.width, 0.6) + '%',
              background: trackColor,
            }"
            :title="seg.tooltip"
            @click="$emit('open-track', seg.track)"
          />
          <!-- Gap indicators -->
          <div
            v-for="gap in gapMarkers"
            :key="'gap-' + gap.pos"
            class="timeline-gap"
            :style="{ left: gap.pos + '%' }"
            :title="`Gap: ${gap.label}`"
          />
        </div>
        <!-- Now cursor -->
        <div
          v-if="nowPct !== null"
          class="timeline-now"
          :style="{ left: nowPct + '%' }"
        />
      </div>
      <div class="d-flex justify-space-between mt-1">
        <span class="text-caption text-disabled">{{ timelineStart }}</span>
        <span class="text-caption text-disabled">{{ timelineEnd }}</span>
      </div>
    </div>

    <!-- Expanded: segment list -->
    <v-expand-transition>
      <div v-if="expanded && tracks.length" class="px-3 pb-3">
        <v-divider class="mb-2" />
        <div
          v-for="track in sortedTracks"
          :key="track.global_track_id"
          class="segment-row d-flex align-center ga-2 py-1"
          @click="$emit('open-track', track)"
        >
          <!-- Thumbnail -->
          <v-img
            v-if="track.latest_keyframe_minio_key"
            :src="frameUrl(track.latest_keyframe_minio_key)"
            width="40"
            height="30"
            cover
            rounded="sm"
            class="flex-shrink-0 segment-thumb"
          />
          <v-sheet
            v-else
            width="40"
            height="30"
            rounded="sm"
            color="surface-variant"
            class="d-flex align-center justify-center flex-shrink-0"
          >
            <v-icon size="12" color="medium-emphasis">mdi-camera-off</v-icon>
          </v-sheet>

          <!-- Time range -->
          <div class="flex-grow-1 min-width-0">
            <div class="text-caption font-weight-medium">
              {{ segmentTimeRange(track) }}
            </div>
            <div class="d-flex flex-wrap ga-1 mt-0">
              <v-chip
                v-for="cid in (track.camera_ids || [])"
                :key="cid"
                size="x-small"
                variant="text"
                class="text-caption text-medium-emphasis"
                prepend-icon="mdi-cctv"
              >
                {{ cid }}
              </v-chip>
            </div>
          </div>

          <!-- Duration -->
          <span class="text-caption text-medium-emphasis">{{ segmentDuration(track) }}</span>

          <!-- Correct action -->
          <v-btn
            icon="mdi-account-edit"
            size="x-small"
            variant="text"
            @click.stop="$emit('correct-track', track)"
          />
        </div>
      </div>
    </v-expand-transition>
  </v-card>
</template>

<script>
import { identityColor } from "@/composables/useIdentityColor";

const TIMELINE_START_H = 6;  // 6am
const TIMELINE_END_H = 24;   // midnight
const TIMELINE_SPAN_H = TIMELINE_END_H - TIMELINE_START_H;

export default {
  name: "PersonTrackCard",

  props: {
    identity: { type: Object, required: true },
    tracks: { type: Array, default: () => [] },
  },

  emits: ["open-track", "correct-track", "merge-fragments"],

  data() {
    return { expanded: false };
  },

  computed: {
    initials() {
      const name = this.identity.display_name || this.identity.identity_id || "?";
      return name
        .split(/\s+/)
        .slice(0, 2)
        .map((w) => w[0]?.toUpperCase() || "")
        .join("");
    },
    avatarColor() {
      return identityColor(this.identity.identity_id);
    },
    trackColor() {
      return identityColor(this.identity.identity_id);
    },
    sortedTracks() {
      return [...this.tracks].sort(
        (a, b) => new Date(a.started_at) - new Date(b.started_at)
      );
    },
    fragmentCount() {
      return this.tracks.length;
    },
    isActive() {
      return this.tracks.some((t) => t.state === "active");
    },
    segmentSummary() {
      const n = this.fragmentCount;
      if (n === 0) return "No sightings today";
      if (n === 1) return "1 sighting today";
      const gaps = this.gapMarkers.length;
      return `${n} sightings · ${gaps} gap${gaps === 1 ? "" : "s"}`;
    },
    // Timeline helpers
    _startMs() {
      const now = new Date();
      const d = new Date(now.getFullYear(), now.getMonth(), now.getDate(), TIMELINE_START_H, 0, 0);
      return d.getTime();
    },
    _endMs() {
      const now = new Date();
      const d = new Date(now.getFullYear(), now.getMonth(), now.getDate(), TIMELINE_END_H, 0, 0);
      return d.getTime();
    },
    _spanMs() {
      return this._endMs - this._startMs;
    },
    timelineStart() {
      return `${TIMELINE_START_H}:00`;
    },
    timelineEnd() {
      const now = new Date();
      const hh = String(now.getHours()).padStart(2, "0");
      const mm = String(now.getMinutes()).padStart(2, "0");
      return `${hh}:${mm}`;
    },
    visibleHours() {
      const hours = [];
      for (let h = TIMELINE_START_H + 2; h < TIMELINE_END_H; h += 2) {
        hours.push(h);
      }
      return hours;
    },
    nowPct() {
      const now = Date.now();
      if (now < this._startMs || now > this._endMs) return null;
      return ((now - this._startMs) / this._spanMs) * 100;
    },
    timelineSegments() {
      return this.sortedTracks.map((track) => {
        const start = Math.max(new Date(track.started_at).getTime(), this._startMs);
        const end = Math.min(
          track.last_seen_at ? new Date(track.last_seen_at).getTime() : Date.now(),
          this._endMs
        );
        const left = ((start - this._startMs) / this._spanMs) * 100;
        const width = ((end - start) / this._spanMs) * 100;
        const startTime = new Date(track.started_at);
        const endTime = track.last_seen_at ? new Date(track.last_seen_at) : new Date();
        return {
          id: track.global_track_id,
          left: Math.max(0, left),
          width: Math.max(0, width),
          track,
          tooltip: `${this._fmtTime(startTime)} – ${this._fmtTime(endTime)} · ${this.segmentDuration(track)}`,
        };
      });
    },
    gapMarkers() {
      if (this.sortedTracks.length < 2) return [];
      const markers = [];
      for (let i = 0; i < this.sortedTracks.length - 1; i++) {
        const endMs = new Date(this.sortedTracks[i].last_seen_at || Date.now()).getTime();
        const startMs = new Date(this.sortedTracks[i + 1].started_at).getTime();
        const gapMs = startMs - endMs;
        if (gapMs > 60_000) {
          const midMs = (endMs + startMs) / 2;
          const pos = ((midMs - this._startMs) / this._spanMs) * 100;
          const gapMin = Math.round(gapMs / 60_000);
          markers.push({
            pos: Math.max(0, Math.min(100, pos)),
            label: gapMin < 60 ? `${gapMin}m` : `${Math.floor(gapMin / 60)}h${gapMin % 60 ? " " + (gapMin % 60) + "m" : ""}`,
          });
        }
      }
      return markers;
    },
  },

  methods: {
    hourPct(h) {
      return ((h - TIMELINE_START_H) / TIMELINE_SPAN_H) * 100;
    },
    segmentDuration(track) {
      if (!track.started_at) return "—";
      const s = Math.round(
        ((track.last_seen_at ? new Date(track.last_seen_at) : new Date()) - new Date(track.started_at)) / 1000
      );
      if (s < 60) return `${s}s`;
      const m = Math.floor(s / 60);
      if (m < 60) return `${m}m`;
      const h = Math.floor(m / 60);
      const rem = m % 60;
      return rem ? `${h}h ${rem}m` : `${h}h`;
    },
    segmentTimeRange(track) {
      const start = this._fmtTime(new Date(track.started_at));
      const end = track.last_seen_at ? this._fmtTime(new Date(track.last_seen_at)) : "now";
      return `${start} – ${end}`;
    },
    _fmtTime(d) {
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    },
    frameUrl(minioKey) {
      if (!minioKey) return "";
      const encodedKey = minioKey.split("/").map(encodeURIComponent).join("/");
      const apiKey = encodeURIComponent(localStorage.getItem("cc_api_key") || "");
      return `/api/v1/cts/frames/${encodedKey}?api_key=${apiKey}`;
    },
  },
};
</script>

<style scoped>
.person-track-card {
  transition: box-shadow 0.15s;
}

.min-width-0 {
  min-width: 0;
}

.rotate-180 {
  transform: rotate(180deg);
}

/* Timeline */
.timeline-outer {
  position: relative;
  padding-top: 16px;
}

.timeline-hours {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 14px;
  pointer-events: none;
}

.timeline-hour-label {
  position: absolute;
  transform: translateX(-50%);
  font-size: 9px;
  color: rgba(var(--v-theme-on-surface), 0.35);
  white-space: nowrap;
}

.timeline-bar {
  position: relative;
  height: 12px;
  background: rgba(var(--v-theme-on-surface), 0.06);
  border-radius: 6px;
  overflow: visible;
}

.timeline-seg {
  position: absolute;
  top: 0;
  height: 100%;
  border-radius: 6px;
  cursor: pointer;
  opacity: 0.85;
  transition: opacity 0.15s, transform 0.1s;
}

.timeline-seg:hover {
  opacity: 1;
  transform: scaleY(1.25);
  z-index: 1;
}

.timeline-gap {
  position: absolute;
  top: -3px;
  width: 2px;
  height: 18px;
  background: rgba(var(--v-theme-on-surface), 0.25);
  border-radius: 1px;
  transform: translateX(-50%);
}

.timeline-now {
  position: absolute;
  top: -4px;
  width: 2px;
  height: 20px;
  background: rgb(var(--v-theme-primary));
  border-radius: 1px;
  transform: translateX(-50%);
  z-index: 2;
}

/* Segment list */
.segment-row {
  cursor: pointer;
  border-radius: 8px;
  padding-left: 4px;
  padding-right: 4px;
  transition: background 0.1s;
}

.segment-row:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}

.segment-thumb {
  cursor: pointer;
}
</style>
