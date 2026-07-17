<template>
  <div>
    <TrackingPanelHeader
      title="Presence Timeline"
      description="Review room occupancy, dwell time, and transitions for one household member."
    >
      <template #actions>
        <v-btn
          variant="tonal"
          prepend-icon="mdi-refresh"
          size="small"
          :loading="loading"
          @click="personId && fetchTimeline(personId)"
        >
          Refresh
        </v-btn>
      </template>
    </TrackingPanelHeader>

    <v-alert
      v-if="error"
      type="error"
      variant="tonal"
      density="compact"
      class="mb-4"
      closable
      @click:close="error = ''"
    >
      {{ error }}
    </v-alert>

    <!-- Person selector -->
    <v-card variant="tonal" class="pa-2 mb-4">
      <v-row dense align="center">
        <v-col cols="12" sm="4">
          <v-select
            v-model="personId"
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

    <!-- HUD cards -->
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

    <!-- CcStatusTimeline: segments as swimlane events (D2) -->
    <v-card class="glass-card mb-4">
      <v-card-title class="text-subtitle-2">Presence Segments (Timeline)</v-card-title>
      <v-divider />
      <v-card-text>
        <CcStatusTimeline
          :lanes="timelineLanes"
          :events="timelineEvents"
          :loading="loading"
          height="180"
        />
      </v-card-text>
    </v-card>

    <!-- Recent transitions -->
    <RecentTransitionsList :transitions="recentTransitions" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { useRoute } from "vue-router";
import { usePresenceTimeline } from "@/composables/usePresenceTimeline.js";
import { useNotify } from "@/composables/useNotify.js";
import { api } from "@/services/api.js";
import CcStatusTimeline from "@/components/process/CcStatusTimeline.vue";
import PresenceHudCard from "@/components/cts/presence/PresenceHudCard.vue";
import RoomDwellTotalsCard from "@/components/cts/presence/RoomDwellTotalsCard.vue";
import RecentTransitionsList from "@/components/cts/presence/RecentTransitionsList.vue";
import TrackingPanelHeader from "@/components/tracking/TrackingPanelHeader.vue";

const route = useRoute();
const { notify } = useNotify();
const {
  personId,
  segments,
  dwells,
  currentLocation,
  loading,
  error,
  activeDuration,
  fetch: fetchTimeline,
} = usePresenceTimeline(notify);

const personOptions = ref([]);

onMounted(async () => {
  try {
    const persons = await api.getPersons();
    personOptions.value = (persons || []).map((p) => ({
      title: p.display_name || p.name || p.id,
      value: p.id,
    }));
  } catch {
    // Non-fatal: person list stays empty
  }

  const routePerson = route.query.person || "";
  if (routePerson) {
    personId.value = routePerson;
    fetchTimeline(routePerson);
  }
});

function onPersonChange(id) {
  personId.value = id;
  if (id) fetchTimeline(id);
}

// Map segments to CcStatusTimeline format
const timelineLanes = computed(() => {
  const roomIds = [...new Set(segments.value.map((s) => s.room_id))];
  return roomIds.map((id) => ({
    id: String(id),
    label: segments.value.find((s) => s.room_id === id)?.room_name || `Room ${id}`,
  }));
});

const timelineEvents = computed(() =>
  segments.value.map((seg) => ({
    laneId: String(seg.room_id),
    t: seg.entered_at,
    label: seg.room_name || `Room ${seg.room_id}`,
    status: seg.is_inferred ? "pending" : "succeeded",
  })),
);

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
</script>
