<template>
  <div>
    <!-- Header -->
    <div class="d-flex align-center mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold">Presence Timeline</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Where each person is, how long, and recent transitions.
        </div>
      </div>
      <v-spacer />
      <v-btn variant="tonal" prepend-icon="mdi-refresh" :loading="loading" @click="fetchTimeline(personId)">
        Refresh
      </v-btn>
    </div>

    <v-alert v-if="error" type="error" class="mb-4" closable @click:close="error = ''">
      {{ error }}
    </v-alert>

    <!-- Person selector -->
    <v-card variant="flat" class="mb-4 px-4 py-2" border>
      <v-row dense align="center">
        <v-col cols="12" sm="4">
          <v-select
            :model-value="personId"
            :items="personOptions"
            label="Household member"
            variant="outlined"
            density="compact"
            hide-details
            @update:model-value="onPersonChange"
          />
        </v-col>
      </v-row>
    </v-card>

    <!-- HUD card -->
    <v-row class="mb-4">
      <v-col cols="12" md="4">
        <PresenceHudCard
          :current-room="currentLocation?.room_name || null"
          :since="currentLocation?.since || null"
          :is-inferred="currentLocation?.is_inferred || false"
          :active-duration="activeDuration"
        />
      </v-col>
      <v-col cols="12" md="8">
        <RoomDwellTotalsCard :dwells="dwells" />
      </v-col>
    </v-row>

    <!-- Timeline SVG -->
    <v-card class="glass-card mb-4">
      <v-card-title class="text-subtitle-2">Presence Segments</v-card-title>
      <v-divider />
      <v-card-text class="pa-2">
        <div v-if="segments.length === 0" class="pa-4 text-center text-medium-emphasis">
          No presence data for this window.
        </div>
        <svg v-else :viewBox="`0 0 ${timelineWidth} 60`" width="100%" height="60" class="timeline-svg">
          <!-- Background grid lines -->
          <line v-for="(tick, i) in timeTicks" :key="'tick-' + i"
            :x1="tick.x" y1="0" :x2="tick.x" y2="60"
            stroke="var(--cc-divider)" stroke-width="0.5" />

          <!-- Segments -->
          <g v-for="seg in segments" :key="seg.segment_id">
            <rect
              :x="timeToX(seg.entered_at)"
              y="10"
              :width="Math.max(segWidth(seg), 4)"
              height="20"
              rx="3"
              :fill="roomColor(seg.room_id)"
              :opacity="seg.is_inferred ? 0.5 : 0.85"
            >
              <title>{{ seg.room_name }}: {{ formatDuration(seg.dwell_seconds) }}</title>
            </rect>
            <rect
              v-if="seg.is_inferred"
              :x="timeToX(seg.entered_at)"
              y="10"
              :width="Math.max(segWidth(seg), 4)"
              height="20"
              rx="3"
              fill="url(#inferred-stripe)"
              opacity="0.6"
            />
          </g>

          <!-- Time labels -->
          <text v-for="(tick, i) in timeTicks.filter((_, i) => i % 3 === 0)" :key="'label-' + i"
            :x="tick.x" y="52" text-anchor="middle" font-size="8" fill="var(--cc-text-3)">
            {{ tick.label }}
          </text>

          <defs>
            <pattern id="inferred-stripe" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <line x1="0" y1="0" x2="0" y2="6" stroke="var(--cc-divider-strong)" stroke-width="2" />
            </pattern>
          </defs>
        </svg>
      </v-card-text>
    </v-card>

    <!-- Recent transitions -->
    <RecentTransitionsList :transitions="recentTransitions" />

    <!-- Signals strip -->
    <v-card v-if="signals.length > 0" class="glass-card">
      <v-card-title class="text-subtitle-2">Signals</v-card-title>
      <v-divider />
      <v-card-text>
        <div class="d-flex flex-wrap ga-1">
          <v-chip
            v-for="sig in signals"
            :key="sig.signal_id"
            size="x-small"
            :color="sig.severity === 'emergency' ? 'error' : 'warning'"
            variant="tonal"
            @click="$router.push({ name: 'cts-signals', query: { signal_id: sig.signal_id } })"
          >
            {{ sig.signal_kind.replace(/_/g, ' ') }}
          </v-chip>
        </div>
      </v-card-text>
    </v-card>
  </div>
</template>

<script>
import { ref, computed } from "vue";
import { useRoute } from "vue-router";
import { useTheme } from "vuetify";
import { formatTimeOnly, isoToLocalHHMM } from "@/services/timezone.js";
import { usePresenceTimeline } from "@/composables/usePresenceTimeline";
import { useNotify } from "@/composables/useNotify";
import PresenceHudCard from "@/components/cts/presence/PresenceHudCard.vue";
import RoomDwellTotalsCard from "@/components/cts/presence/RoomDwellTotalsCard.vue";
import RecentTransitionsList from "@/components/cts/presence/RecentTransitionsList.vue";

export default {
  name: "PresenceTimelineView",
  components: { PresenceHudCard, RoomDwellTotalsCard, RecentTransitionsList },

  setup() {
    const route = useRoute();
    const { notify } = useNotify();
    const theme = useTheme();
    const {
      personId,
      segments,
      dwells,
      currentLocation,
      loading,
      error,
      activeDuration,
      fetch: fetchTimeline,
      handleWsEvent,
    } = usePresenceTimeline(notify);

    if (route.params.personId) {
      personId.value = route.params.personId;
    }

    const signals = ref([]);
    const personOptions = ref([
      { title: "All members (select one)", value: "", disabled: true },
    ]);

    const timelineWidth = 800;

    const windowStart = computed(() => {
      if (segments.value.length === 0) return Date.now() - 86400000;
      return Math.min(...segments.value.map((s) => new Date(s.entered_at).getTime()));
    });

    const windowEnd = computed(() => {
      if (segments.value.length === 0) return Date.now();
      return Math.max(
        ...segments.value.map((s) =>
          s.exited_at ? new Date(s.exited_at).getTime() : Date.now()
        )
      );
    });

    const windowSpan = computed(() => Math.max(windowEnd.value - windowStart.value, 60000));

    function timeToX(iso) {
      if (!iso) return 0;
      const t = new Date(iso).getTime();
      return ((t - windowStart.value) / windowSpan.value) * timelineWidth;
    }

    function segWidth(seg) {
      const start = new Date(seg.entered_at).getTime();
      const end = seg.exited_at ? new Date(seg.exited_at).getTime() : Date.now();
      return ((end - start) / windowSpan.value) * timelineWidth;
    }

    const timeTicks = computed(() => {
      const ticks = [];
      const span = windowSpan.value;
      const interval = span > 43200000 ? 4 * 3600000 : 3600000;
      const start = Math.ceil(windowStart.value / interval) * interval;
      for (let t = start; t <= windowEnd.value; t += interval) {
        ticks.push({
          x: ((t - windowStart.value) / span) * timelineWidth,
          label: isoToLocalHHMM(new Date(t).toISOString()),
        });
      }
      return ticks;
    });

    const recentTransitions = computed(() => {
      const transitions = [];
      let prev = null;
      for (const seg of segments.value) {
        if (prev && seg.room_id !== prev.room_id) {
          transitions.push({
            from_room_id: prev.room_id,
            from_room_name: prev.room_name,
            to_room_id: seg.room_id,
            to_room_name: seg.room_name,
            transitioned_at: seg.entered_at,
          });
        }
        prev = seg;
      }
      return transitions.slice(-10);
    });

    function roomColor(roomId) {
      const keys = ["primary", "secondary", "info", "success", "warning", "tertiary"];
      const hash = Math.abs(
        String(roomId).split("").reduce((h, c) => (h * 31 + c.charCodeAt(0)) | 0, 0)
      );
      const key = keys[hash % keys.length];
      return theme.current.value.colors[key] ?? "#888";
    }

    function formatDuration(secs) {
      if (!secs || secs < 0) return "0m";
      const h = Math.floor(secs / 3600);
      const m = Math.floor((secs % 3600) / 60);
      return h > 0 ? `${h}h ${m}m` : `${m}m`;
    }

    function onPersonChange(id) {
      personId.value = id;
      fetchTimeline(id);
    }

    // Initial load
    if (personId.value) fetchTimeline(personId.value);

    return {
      personId,
      segments,
      dwells,
      currentLocation,
      loading,
      error,
      activeDuration,
      signals,
      personOptions,
      timelineWidth,
      timeTicks,
      recentTransitions,
      roomColor,
      formatDuration,
      formatTimeOnly,
      timeToX,
      segWidth,
      fetchTimeline,
      onPersonChange,
    };
  },
};
</script>

<style scoped>
.timeline-svg {
  background: var(--cc-surface-2);
  border-radius: 8px;
}
</style>
