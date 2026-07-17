<template>
  <v-timeline side="end" density="compact" align="start" class="timeline-with-sidebar">
    <v-timeline-item
      v-for="event in sortedEvents"
      :key="event.timestamp + '-' + event.event_type + '-' + Math.random()"
      :size="event.is_primary ? 'x-large' : 'small'"
      :color="eventColor(event)"
      :icon="eventIcon(event)"
      :trail="event.is_primary"
      :prepend-icon="event.is_primary ? undefined : 'mdi-circle-small'"
    >
      <!-- Primary events get a full card -->
      <v-card v-if="event.is_primary" class="primary-event-card glass-card" variant="elevated">
        <v-card-text class="pa-4">
          <div class="d-flex align-start">
            <div class="flex-grow-1">
              <div class="d-flex align-center mb-1">
                <span class="text-body-1 font-weight-medium">{{ eventTitle(event) }}</span>
                <v-chip
                  v-if="event.source"
                  size="x-small"
                  class="ml-2"
                  variant="tonal"
                  color="surface-variant"
                >
                  {{ eventSourceLabel(event.source) }}
                </v-chip>
              </div>
              <div class="text-caption text-medium-emphasis mb-1">
                {{ formatTime(event.timestamp) }}
              </div>
              <div v-if="event.room_name" class="text-caption d-flex align-center">
                <v-icon size="12" class="mr-1">mdi-map-marker</v-icon>
                {{ event.room_name }}
              </div>
              <div v-if="event.metadata?.confidence != null" class="text-caption">
                Confidence: {{ (event.metadata.confidence * 100).toFixed(0) }}%
              </div>
              <div v-if="event.metadata?.duration_minutes != null" class="text-caption">
                Duration: {{ event.metadata.duration_minutes }} min
              </div>
            </div>
          </div>
        </v-card-text>
      </v-card>

      <!-- Compact events -->
      <div v-else class="compact-event pa-2">
        <div class="text-body-2">{{ eventTitle(event) }}</div>
        <div class="text-caption text-medium-emphasis">
          {{ formatTime(event.timestamp) }}
          <span v-if="event.room_name" class="ml-1">| {{ event.room_name }}</span>
        </div>
      </div>
    </v-timeline-item>

    <!-- Empty state -->
    <v-timeline-item v-if="events.length === 0" size="small">
      <v-alert type="info" variant="tonal" class="mx-4">
        No events found for this person in the selected time window.
      </v-alert>
    </v-timeline-item>
  </v-timeline>
</template>

<script setup>
import { ref, computed } from "vue";
import { formatDateTime } from "../../services/timezone.js";

const props = defineProps({
  personId: { type: String, required: true },
  hours: { type: Number, default: 24 },
  eventTypes: { type: Array, default: () => ["activity", "session", "location", "sighting"] },
});

const events = ref([]);
const loading = ref(false);

const sortedEvents = computed(() =>
  [...events.value].sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp)),
);

async function load() {
  loading.value = true;
  try {
    const data = await api.getTimeline(props.personId, {
      hours: props.hours,
      event_types: props.eventTypes.join(","),
    });
    events.value = data || [];
  } catch (e) {
    console.error("Failed to load timeline:", e);
  } finally {
    loading.value = false;
  }
}

function eventColor(event) {
  switch (event.source) {
    case "activity":
      return "primary";
    case "session":
      return "success";
    case "location":
      return "info";
    case "sighting":
      return "warning";
    default:
      return "grey";
  }
}

function eventIcon(event) {
  switch (event.event_type) {
    case "activity_detected":
      return "mdi-check-circle";
    case "session_opened":
      return "mdi-play-circle";
    case "session_closed":
      return "mdi-stop-circle";
    case "room_entered":
      return "mdi-door";
    case "room_transited":
      return "mdi-walk";
    case "person_sighted":
      return "mdi-camera";
    default:
      return "mdi-circle";
  }
}

function eventTitle(event) {
  const titles = {
    activity_detected: event.activity_type
      ? event.activity_type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
      : "Activity detected",
    session_opened: `Session started${event.activity_type ? `: ${event.activity_type.replace(/_/g, " ")}` : ""}`,
    session_closed: `Session ended${event.activity_type ? `: ${event.activity_type.replace(/_/g, " ")}` : ""}`,
    room_entered: `Entered ${event.room_name || "a room"}`,
    room_transited: `Left ${event.room_name || "a room"}`,
    person_sighted: "Person detected",
  };
  return titles[event.event_type] || event.event_type;
}

function eventSourceLabel(source) {
  const labels = {
    activity: "Activity",
    session: "Session",
    location: "Location",
    sighting: "Sighting",
  };
  return labels[source] || source;
}

function formatTime(timestamp) {
  return formatDateTime(timestamp);
}

defineExpose({ load });
</script>

<style scoped>
.primary-event-card {
  border-left: 3px solid var(--cc-brand);
}

.compact-event {
  padding: 4px 8px;
  border-radius: 4px;
}

.compact-event:hover {
  background-color: rgba(0, 0, 0, 0.04);
}

.v-timeline {
  max-height: calc(100vh - 280px);
  overflow-y: auto;
}
</style>
