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
      <v-btn variant="tonal" prepend-icon="mdi-refresh" :loading="loading" @click="fetch()">
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
        <v-card class="glass-card pa-4">
          <div class="text-caption text-medium-emphasis">Currently in</div>
          <div v-if="currentLocation && currentLocation.room_name" class="text-h5 font-weight-bold mt-1">
            {{ currentLocation.room_name }}
          </div>
          <div v-else class="text-h5 font-weight-bold mt-1 text-medium-emphasis">Unknown</div>
          <div v-if="currentLocation && currentLocation.since" class="text-caption text-medium-emphasis mt-1">
            In for {{ formatDuration(currentLocation.dwell_seconds) }}
          </div>
          <div v-if="currentLocation && currentLocation.is_inferred" class="mt-2">
            <v-chip size="x-small" color="warning" variant="tonal" prepend-icon="mdi-timer-sand">
              Inferred
            </v-chip>
          </div>
        </v-card>
      </v-col>

      <!-- Dwell totals -->
      <v-col cols="12" md="8">
        <v-card class="glass-card">
          <v-card-title class="text-subtitle-2">Today's room dwell totals</v-card-title>
          <v-divider />
          <v-card-text>
            <div v-if="dwells.length === 0" class="text-caption text-medium-emphasis">
              No room dwell data for this period.
            </div>
            <div v-for="d in dwells" :key="d.room_id" class="d-flex align-center ga-2 mb-2">
              <span class="text-caption" style="min-width: 100px;">{{ d.room_name }}</span>
              <v-progress-linear
                :model-value="dwellPercent(d)"
                color="primary"
                height="8"
                rounded
                style="flex: 1;"
              />
              <span class="text-caption text-medium-emphasis" style="min-width: 60px;">
                {{ formatDuration(d.total_seconds) }}
              </span>
            </div>
          </v-card-text>
        </v-card>
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
            stroke="rgba(128,128,128,0.15)" stroke-width="0.5" />

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
            <!-- Inferred stripe pattern -->
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
            :x="tick.x" y="52" text-anchor="middle" font-size="8" fill="#888">
            {{ tick.label }}
          </text>

          <defs>
            <pattern id="inferred-stripe" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <line x1="0" y1="0" x2="0" y2="6" stroke="rgba(255,255,255,0.5)" stroke-width="2" />
            </pattern>
          </defs>
        </svg>
      </v-card-text>
    </v-card>

    <!-- Recent transitions -->
    <v-card v-if="recentTransitions.length > 0" class="glass-card mb-4">
      <v-card-title class="text-subtitle-2">Recent Transitions</v-card-title>
      <v-divider />
      <v-list density="compact">
        <v-list-item v-for="(t, i) in recentTransitions" :key="'t-' + i">
          <template #prepend>
            <v-icon size="14" color="medium-emphasis">mdi-arrow-right</v-icon>
          </template>
          <v-list-item-title class="text-caption">
            {{ t.from_room_name || 'Unknown' }} → {{ t.to_room_name }}
          </v-list-item-title>
          <v-list-item-subtitle class="text-caption text-medium-emphasis">
            {{ formatTime(t.transitioned_at) }}
          </v-list-item-subtitle>
        </v-list-item>
      </v-list>
    </v-card>

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
import { formatRelative } from "@/composables/useFormatRelative";
import { identityColor } from "@/composables/useIdentityColor";

export default {
  name: "PresenceTimelineView",

  setup() {
    const route = useRoute();
    const personId = ref(route.params.personId || "");
    const segments = ref([]);
    const dwells = ref([]);
    const currentLocation = ref(null);
    const signals = ref([]);
    const loading = ref(false);
    const error = ref("");

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
      const interval = span > 43200000 ? 4 * 3600000 : 3600000; // 4h or 1h
      const start = Math.ceil(windowStart.value / interval) * interval;
      for (let t = start; t <= windowEnd.value; t += interval) {
        const d = new Date(t);
        ticks.push({
          x: ((t - windowStart.value) / span) * timelineWidth,
          label: `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`,
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
      const palette = ["#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7", "#DDA0DD", "#FF6B6B", "#F7DC6F"];
      return palette[Math.abs(String(roomId).split("").reduce((h, c) => h * 31 + c.charCodeAt(0), 0)) % palette.length];
    }

    function dwellPercent(d) {
      const max = Math.max(...dwells.value.map((x) => x.total_seconds), 1);
      return (d.total_seconds / max) * 100;
    }

    function formatDuration(secs) {
      if (!secs || secs < 0) return "0m";
      const h = Math.floor(secs / 3600);
      const m = Math.floor((secs % 3600) / 60);
      return h > 0 ? `${h}h ${m}m` : `${m}m`;
    }

    function formatTime(iso) {
      if (!iso) return "";
      const d = new Date(iso);
      return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
    }

    async function fetch() {
      if (!personId.value) return;
      loading.value = true;
      error.value = "";
      try {
        const apiKey = localStorage.getItem("cc_api_key") || "";
        const headers = { "X-API-Key": apiKey };
        const BASE = "/api/v1/cts";
        const resp = await fetch(`${BASE}/presence/timeline/${encodeURIComponent(personId.value)}`, { headers });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        segments.value = data.segments || [];
        signals.value = data.signals || [];

        const [dwellsR, currentR] = await Promise.all([
          fetch(`${BASE}/presence/dwells/${encodeURIComponent(personId.value)}`, { headers }),
          fetch(`${BASE}/presence/currently_in`, { headers }),
        ]);
        dwells.value = (await dwellsR.json()).dwells || [];
        const currentData = await currentR.json();
        currentLocation.value =
          (currentData.occupants || []).find((o) => o.person_id === personId.value) || null;

        // Build person options
        personOptions.value = (currentData.occupants || []).map((o) => ({
          title: o.display_name || o.person_id,
          value: o.person_id,
        }));
      } catch (err) {
        error.value = String(err.message || err);
      } finally {
        loading.value = false;
      }
    }

    function onPersonChange(id) {
      personId.value = id;
      fetch();
    }

    // Initial load
    if (personId.value) fetch();

    return {
      personId,
      segments,
      dwells,
      currentLocation,
      signals,
      loading,
      error,
      personOptions,
      timelineWidth,
      timeTicks,
      recentTransitions,
      roomColor,
      dwellPercent,
      formatDuration,
      formatTime,
      formatRelative,
      timeToX,
      segWidth,
      fetch,
      onPersonChange,
    };
  },
};
</script>

<style scoped>
.timeline-svg { background: rgba(0, 0, 0, 0.02); border-radius: 8px; }
</style>
