<template>
  <v-card variant="flat" border rounded="lg" class="person-track-card">
    <!-- Header row -->
    <div class="d-flex align-center ga-3 pa-3 pb-2">
      <v-avatar :color="avatarColor" size="40">
        <span class="text-body-2 font-weight-bold" style="color: white">{{ initials }}</span>
      </v-avatar>

      <div class="flex-grow-1 min-width-0">
        <div class="d-flex align-center ga-2">
          <span class="text-body-1 font-weight-medium text-truncate">
            {{ identity.display_name || identity.identity_id }}
          </span>
          <v-chip v-if="isActive" color="success" size="x-small" variant="flat">active</v-chip>
          <v-chip v-else-if="lastSeenLabel" color="default" size="x-small" variant="tonal">
            {{ lastSeenLabel }}
          </v-chip>
        </div>
        <div class="text-caption text-medium-emphasis">{{ segmentSummary }}</div>
      </div>

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
          :icon="expanded ? 'mdi-chevron-up' : 'mdi-chevron-down'"
          size="x-small"
          variant="text"
          @click="expanded = !expanded"
        />
      </div>
    </div>

    <!-- Timeline strip -->
    <div class="px-3 pb-2">
      <div class="timeline-outer">
        <div class="timeline-hours">
          <span
            v-for="h in visibleHours"
            :key="h.ts"
            class="timeline-hour-label"
            :class="{ 'timeline-hour-label--midnight': h.isMidnight }"
            :style="{ left: hourPct(h) + '%' }"
          >{{ h.label }}</span>
        </div>
        <div class="timeline-bar">
          <div
            v-for="seg in timelineSegments"
            :key="seg.id"
            class="timeline-seg"
            :class="{ 'timeline-seg--closed': seg.closed }"
            :style="{
              left: seg.left + '%',
              width: Math.max(seg.width, 0.6) + '%',
              background: trackColor,
              opacity: seg.closed ? 0.45 : 0.85,
            }"
            :title="seg.tooltip"
            @click="$emit('open-track', seg.track)"
          />
          <div
            v-for="gap in gapMarkers"
            :key="'gap-' + gap.pos"
            class="timeline-gap"
            :style="{ left: gap.pos + '%' }"
            :title="`Gap: ${gap.label}`"
          />
          <div
            v-if="midnightPct !== null"
            class="timeline-midnight"
            :style="{ left: midnightPct + '%' }"
            title="Midnight"
          />
        </div>
      </div>
      <div class="d-flex justify-space-between mt-1">
        <span class="text-caption text-disabled">{{ timelineStart }}</span>
        <span class="text-caption text-disabled">{{ timelineEnd }}</span>
      </div>
    </div>

    <!-- Posture teaser (always visible, compact) -->
    <div v-if="!expanded && trailPoints.length" class="px-3 pb-2">
      <PostureDistributionBar :points="trailPoints" />
    </div>

    <!-- Expanded detail -->
    <v-expand-transition>
      <div v-if="expanded" class="px-3 pb-3">
        <v-divider class="mb-3" />

        <!-- Day summary stats -->
        <div class="d-flex flex-wrap ga-4 mb-3">
          <div class="stat-pill">
            <span class="stat-value">{{ fragmentCount }}</span>
            <span class="stat-label">sighting{{ fragmentCount !== 1 ? "s" : "" }}</span>
          </div>
          <div class="stat-pill">
            <span class="stat-value">{{ totalDurationToday }}</span>
            <span class="stat-label">total today</span>
          </div>
          <div v-if="largestGapLabel" class="stat-pill">
            <span class="stat-value">{{ largestGapLabel }}</span>
            <span class="stat-label">longest gap</span>
          </div>
          <div class="stat-pill">
            <span class="stat-value">{{ coveragePct }}%</span>
            <span class="stat-label">coverage</span>
          </div>
        </div>

        <!-- Posture section -->
        <div class="mb-3">
          <div class="d-flex align-center ga-1 mb-1">
            <v-icon size="14" color="medium-emphasis">mdi-human-greeting-variant</v-icon>
            <span class="text-caption font-weight-medium text-medium-emphasis">Posture distribution</span>
            <span class="text-caption text-disabled ml-1">· all sightings today</span>
          </div>
          <PostureDistributionBar :points="trailPoints" :loading="trailLoading" />
        </div>

        <!-- Segment table -->
        <div class="segment-table">
          <div class="segment-table-head">
            <div />
            <div>Start</div>
            <div>End</div>
            <div>Dur</div>
            <div>Cameras</div>
            <div>Posture</div>
            <div />
          </div>

          <div
            v-for="track in paginatedTracks"
            :key="track.global_track_id"
            class="segment-row"
            :class="{ 'segment-row--closed': track.state !== 'active' }"
            @click="$emit('open-track', track)"
          >
            <!-- Thumbnail -->
            <div class="seg-col-thumb">
              <v-img
                v-if="track.latest_keyframe_minio_key"
                :src="displaySrc(frameUrl(track.latest_keyframe_minio_key))"
                width="80"
                height="60"
                cover
                rounded="sm"
                class="segment-thumb"
              />
              <v-sheet
                v-else
                width="80"
                height="60"
                rounded="sm"
                color="surface-variant"
                class="d-flex align-center justify-center"
              >
                <v-icon size="16" color="medium-emphasis">mdi-camera-off</v-icon>
              </v-sheet>
            </div>

            <!-- Start -->
            <div class="seg-col-time">
              <span class="text-caption font-weight-medium">{{ trackStartTime(track) }}</span>
            </div>

            <!-- End -->
            <div class="seg-col-time">
              <span class="text-caption font-weight-medium">{{ trackEndTime(track) }}</span>
              <v-chip v-if="track.state === 'active'" color="success" size="x-small" variant="flat" class="seg-live-chip">live</v-chip>
            </div>

            <!-- Duration -->
            <div class="seg-col-dur">
              <span class="text-caption text-medium-emphasis">{{ segmentDuration(track) }}</span>
            </div>

            <!-- Cameras -->
            <div class="seg-col-cams">
              <div v-if="(track.camera_ids || []).length" class="d-flex flex-column ga-1">
                <v-chip
                  v-for="cid in track.camera_ids"
                  :key="cid"
                  size="x-small"
                  variant="tonal"
                  prepend-icon="mdi-cctv"
                  class="text-caption"
                >{{ cid }}</v-chip>
              </div>
              <span v-else class="text-caption text-disabled">—</span>
            </div>

            <!-- Posture -->
            <div class="seg-col-posture">
              <PostureDistributionBar
                :points="trailsByTrack[track.global_track_id] || []"
                :loading="trailLoading && !trailsByTrack[track.global_track_id]"
                compact
              />
            </div>

            <!-- Action -->
            <div class="seg-col-action">
              <v-btn
                icon="mdi-account-edit"
                size="x-small"
                variant="text"
                @click.stop="$emit('correct-track', track)"
              />
            </div>
          </div>

          <!-- Segment pagination -->
          <div class="d-flex align-center justify-space-between mt-3 gap-3 flex-wrap">
            <div class="d-flex align-center ga-2">
              <v-select
                v-model="itemsPerPage"
                :items="itemsPerPageOptions"
                density="compact"
                variant="outlined"
                hide-details
                style="max-width: 72px"
                aria-label="Tracks per page"
              />
              <span class="text-caption text-medium-emphasis">{{ showingRange }}</span>
            </div>
            <v-pagination
              v-if="totalSegmentPages > 1"
              v-model="segmentPage"
              :length="totalSegmentPages"
              size="x-small"
              density="compact"
              variant="tonal"
              :total-visible="5"
            />
          </div>
        </div>
      </div>
    </v-expand-transition>
  </v-card>
</template>

<script>
import { identityColor } from "@/composables/useIdentityColor";
import { useBlurMode, useDisplaySrc } from "@/composables/useBlurMode";
import { formatTimeOnly } from "@/services/timezone";
import { cts } from "@/services/cts";
import PostureDistributionBar from "./PostureDistributionBar.vue";


export default {
  name: "PersonTrackCard",
  components: { PostureDistributionBar },

  setup() {
    const { blurMode } = useBlurMode();
    const { displaySrc } = useDisplaySrc(blurMode);
    return { displaySrc };
  },

  props: {
    identity: { type: Object, required: true },
    tracks:   { type: Array,  default: () => [] },
  },

  emits: ["open-track", "correct-track", "merge-fragments"],

  data() {
    return {
      expanded:        false,
      trailPoints:     [],
      trailsByTrack:   {},
      trailLoading:    false,
      now:             Date.now(),
      _nowTimer:       null,
      segmentPage:       1,
      itemsPerPage:      5,
      itemsPerPageOptions: [5, 10, 15, 20],
    };
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
    avatarColor() { return identityColor(this.identity.identity_id); },
    trackColor()  { return identityColor(this.identity.identity_id); },
    sortedTracks() {
      return [...this.tracks].sort((a, b) => new Date(a.started_at) - new Date(b.started_at));
    },
    totalSegmentPages() {
      return Math.max(1, Math.ceil(this.sortedTracks.length / this.itemsPerPage));
    },
    paginatedTracks() {
      const start = (this.segmentPage - 1) * this.itemsPerPage;
      return this.sortedTracks.slice(start, start + this.itemsPerPage);
    },
    showingRange() {
      if (!this.sortedTracks.length) return "No tracks";
      const start = (this.segmentPage - 1) * this.itemsPerPage + 1;
      const end = Math.min(start + this.itemsPerPage - 1, this.sortedTracks.length);
      return `${start}–${end} of ${this.sortedTracks.length}`;
    },
    fragmentCount() { return this.tracks.length; },
    isActive() { return this.tracks.some((t) => t.state === "active"); },
    lastSeenLabel() {
      const last = this.sortedTracks[this.sortedTracks.length - 1];
      if (!last?.last_seen_at) return null;
      const diffMin = Math.round((this.now - new Date(last.last_seen_at).getTime()) / 60_000);
      if (diffMin < 1) return "just now";
      if (diffMin < 60) return `${diffMin}m ago`;
      const h = Math.floor(diffMin / 60);
      return `${h}h ago`;
    },
    segmentSummary() {
      const n = this.fragmentCount;
      if (n === 0) return "No sightings today";
      if (n === 1) return "1 sighting today";
      const gaps = this.gapMarkers.length;
      return `${n} sightings · ${gaps} gap${gaps === 1 ? "" : "s"}`;
    },
    _startMs() {
      const cutoff = this.now - 24 * 3_600_000;
      if (!this.tracks.length) return cutoff;
      const earliest = Math.min(...this.tracks.map((t) => new Date(t.started_at).getTime()));
      // Floor to the hour boundary, but never further back than 24h ago.
      const floored = Math.floor(earliest / 3_600_000) * 3_600_000;
      return Math.max(floored, cutoff);
    },
    _endMs() {
      // Bar ends at current time, not midnight — user explicitly requested this.
      return this.now;
    },
    _spanMs() { return this._endMs - this._startMs; },
    timelineStart() {
      const d = new Date(this._startMs);
      return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
    },
    timelineEnd() {
      const d = new Date(this.now);
      return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
    },
    visibleHours() {
      const step = 2 * 3_600_000;
      const firstEven = Math.ceil((this._startMs + 1) / step) * step;
      const labels = [];
      for (let ts = firstEven; ts < this._endMs; ts += step) {
        const d = new Date(ts);
        labels.push({
          ts,
          label: `${String(d.getHours()).padStart(2, "0")}:00`,
          isMidnight: d.getHours() === 0,
        });
      }
      return labels;
    },
    midnightPct() {
      const end = new Date(this._endMs);
      const midnight = new Date(end.getFullYear(), end.getMonth(), end.getDate()).getTime();
      if (midnight > this._startMs && midnight < this._endMs) {
        return ((midnight - this._startMs) / this._spanMs) * 100;
      }
      return null;
    },
    timelineSegments() {
      return this.sortedTracks.map((track) => {
        const rawStart = new Date(track.started_at).getTime();
        const rawEnd = track.state === "active"
          ? this.now
          : (track.last_seen_at ? new Date(track.last_seen_at).getTime() : this.now);
        const start = Math.max(rawStart, this._startMs);
        const end   = Math.min(rawEnd, this._endMs);
        const startFull = new Date(rawStart);
        const endFull   = new Date(rawEnd);
        return {
          id:      track.global_track_id,
          left:    Math.max(0, ((start - this._startMs) / this._spanMs) * 100),
          width:   Math.max(0, ((end - start) / this._spanMs) * 100),
          closed:  track.state !== "active",
          track,
          tooltip: `${this._fmtTime(startFull)} – ${track.state === "active" ? "now" : this._fmtTime(endFull)} · ${this.segmentDuration(track)}`,
        };
      });
    },
    gapMarkers() {
      if (this.sortedTracks.length < 2) return [];
      const markers = [];
      for (let i = 0; i < this.sortedTracks.length - 1; i++) {
        const endMs   = new Date(this.sortedTracks[i].last_seen_at || Date.now()).getTime();
        const startMs = new Date(this.sortedTracks[i + 1].started_at).getTime();
        const gapMs   = startMs - endMs;
        if (gapMs > 60_000) {
          const midMs  = (endMs + startMs) / 2;
          const pos    = ((midMs - this._startMs) / this._spanMs) * 100;
          const gapMin = Math.round(gapMs / 60_000);
          markers.push({
            pos: Math.max(0, Math.min(100, pos)),
            label: gapMin < 60
              ? `${gapMin}m`
              : `${Math.floor(gapMin / 60)}h${gapMin % 60 ? " " + (gapMin % 60) + "m" : ""}`,
          });
        }
      }
      return markers;
    },
    totalDurationToday() {
      let totalS = 0;
      for (const t of this.tracks) {
        if (!t.started_at) continue;
        const end = t.state === "active" ? this.now : (t.last_seen_at ? new Date(t.last_seen_at).getTime() : this.now);
        totalS += Math.max(0, (end - new Date(t.started_at).getTime()) / 1000);
      }
      return this._fmtDuration(Math.round(totalS));
    },
    largestGapLabel() {
      if (this.gapMarkers.length === 0) return null;
      const gapMins = this.gapMarkers.map((g) => {
        const match = g.label.match(/^(\d+)h(?:\s*(\d+)m)?$/);
        if (match) return parseInt(match[1]) * 60 + (parseInt(match[2]) || 0);
        const mMatch = g.label.match(/^(\d+)m$/);
        return mMatch ? parseInt(mMatch[1]) : 0;
      });
      const max = Math.max(...gapMins);
      return max < 60 ? `${max}m` : `${Math.floor(max / 60)}h${max % 60 ? " " + (max % 60) + "m" : ""}`;
    },
    coveragePct() {
      if (!this._spanMs || this._spanMs <= 0) return 0;
      let covered = 0;
      for (const t of this.tracks) {
        if (!t.started_at) continue;
        const s = Math.max(new Date(t.started_at).getTime(), this._startMs);
        const rawEnd = t.state === "active" ? this.now : (t.last_seen_at ? new Date(t.last_seen_at).getTime() : this.now);
        const e = Math.min(rawEnd, this._endMs);
        if (e > s) covered += e - s;
      }
      return Math.round((covered / this._spanMs) * 100);
    },
  },

  mounted() {
    this._nowTimer = setInterval(() => { this.now = Date.now(); }, 30_000);
  },

  beforeUnmount() {
    clearInterval(this._nowTimer);
  },

  watch: {
    expanded(val) {
      if (val && !this.trailPoints.length) {
        this.loadAllTrails();
      }
    },
    sortedTracks() {
      this.segmentPage = 1;
    },
    itemsPerPage() {
      this.segmentPage = 1;
    },
  },

  methods: {
    hourPct(h) { return ((h.ts - this._startMs) / this._spanMs) * 100; },
    _fmtDuration(s) {
      if (s < 60)  return `${s}s`;
      const m = Math.floor(s / 60);
      if (m < 60)  return `${m}m`;
      const h = Math.floor(m / 60);
      const rem = m % 60;
      return rem ? `${h}h ${rem}m` : `${h}h`;
    },
    segmentDuration(track) {
      if (!track.started_at) return "—";
      const end = track.state === "active" ? this.now : (track.last_seen_at ? new Date(track.last_seen_at).getTime() : this.now);
      return this._fmtDuration(Math.round((end - new Date(track.started_at).getTime()) / 1000));
    },
    segmentTimeRange(track) {
      const start = this._fmtTime(new Date(track.started_at));
      const end   = track.state === "active" ? "now" : (track.last_seen_at ? this._fmtTime(new Date(track.last_seen_at)) : "?");
      return `${start} – ${end}`;
    },
    _fmtTime(d) {
      return formatTimeOnly(d.toISOString());
    },
    frameUrl(minioKey) {
      if (!minioKey) return "";
      const encoded = minioKey.split("/").map(encodeURIComponent).join("/");
      const key     = encodeURIComponent(localStorage.getItem("cc_api_key") || "");
      return `/api/v1/cts/frames/${encoded}?api_key=${key}`;
    },

    trackStartTime(track) {
      return this._fmtTime(new Date(track.started_at));
    },
    trackEndTime(track) {
      if (track.state === "active") return "now";
      return track.last_seen_at ? this._fmtTime(new Date(track.last_seen_at)) : "?";
    },

    async loadAllTrails() {
      if (!this.sortedTracks.length) return;
      this.trailLoading = true;
      try {
        const byTrack = {};
        const results = await Promise.all(
          this.sortedTracks.map((track) =>
            cts.getTrackTrail(track.global_track_id, { since: track.started_at })
              .then((d) => { byTrack[track.global_track_id] = d.points || []; return d.points || []; })
              .catch(() => { byTrack[track.global_track_id] = []; return []; })
          )
        );
        this.trailsByTrack = byTrack;
        this.trailPoints   = results.flat();
      } finally {
        this.trailLoading = false;
      }
    },
  },
};
</script>

<style scoped>
.person-track-card { transition: box-shadow 0.15s; }
.min-width-0 { min-width: 0; }

/* Timeline */
.timeline-outer { position: relative; padding-top: 16px; }
.timeline-hours { position: absolute; top: 0; left: 0; right: 0; height: 14px; pointer-events: none; }
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
  transition: opacity 0.15s, transform 0.1s;
}
.timeline-seg:hover { opacity: 1 !important; transform: scaleY(1.25); z-index: 1; }
.timeline-gap {
  position: absolute;
  top: -3px;
  width: 2px;
  height: 18px;
  background: rgba(var(--v-theme-on-surface), 0.25);
  border-radius: 1px;
  transform: translateX(-50%);
}
.timeline-midnight {
  position: absolute;
  top: -4px;
  width: 2px;
  height: 20px;
  background: rgba(var(--v-theme-primary), 0.5);
  border-radius: 1px;
  transform: translateX(-50%);
  border-left: 2px dashed rgba(var(--v-theme-primary), 0.6);
  background: transparent;
}
.timeline-hour-label--midnight {
  color: rgba(var(--v-theme-primary), 0.7);
  font-weight: 600;
}

/* Day stats */
.stat-pill {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 48px;
}
.stat-value {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.2;
  color: rgba(var(--v-theme-on-surface), 0.87);
}
.stat-label {
  font-size: 10px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  white-space: nowrap;
}

/* Segment table */
.segment-table {
  display: flex;
  flex-direction: column;
}

.segment-table-head,
.segment-row {
  display: grid;
  grid-template-columns: 80px 52px 52px 40px 80px 1fr 28px;
  align-items: center;
  gap: 8px;
}

.segment-table-head {
  padding: 0 4px 6px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  margin-bottom: 2px;
}

.segment-table-head > div {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: rgba(var(--v-theme-on-surface), 0.4);
}

.segment-row {
  cursor: pointer;
  border-radius: 8px;
  padding: 6px 4px;
  transition: background 0.1s;
}

.segment-row:hover { background: rgba(var(--v-theme-on-surface), 0.04); }
.segment-row--closed { opacity: 0.65; }
.segment-thumb { cursor: pointer; }

.seg-col-thumb { flex-shrink: 0; }
.seg-col-time  { overflow: hidden; display: flex; flex-direction: column; gap: 2px; }
.seg-col-dur   { overflow: hidden; }
.seg-col-cams  { overflow: hidden; min-width: 0; }
.seg-col-posture { min-width: 0; }
.seg-col-action { display: flex; justify-content: center; }
.seg-live-chip  { font-size: 9px !important; height: 14px !important; }
</style>
