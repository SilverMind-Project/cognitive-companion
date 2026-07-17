<template>
  <v-card
    class="glass-card"
    :class="{ 'presence-widget--selected': selected }"
    :style="selected ? { borderColor: 'rgb(var(--v-theme-primary))' } : {}"
    style="cursor: pointer"
    @click="$emit('click')"
  >
    <v-card-text class="pa-4">
      <div class="d-flex align-center mb-3">
        <v-icon size="20" class="mr-2">mdi-map-marker-radius</v-icon>
        <div class="text-subtitle-1 font-weight-medium">{{ personLabel }}</div>
        <v-spacer />
        <v-tooltip v-if="snapshot" location="top">
          <template #activator="{ props: actProps }">
            <v-btn
              v-bind="actProps"
              icon="mdi-refresh"
              size="x-small"
              variant="text"
              :loading="loading"
              aria-label="Refresh presence"
              @click.stop="reload"
            />
          </template>
          Refresh now (auto-refreshes every {{ pollSeconds }}s)
        </v-tooltip>
      </div>

      <v-progress-linear v-if="loading && !snapshot" indeterminate color="primary" class="mb-2" />
      <v-alert
        v-if="error"
        type="error"
        variant="tonal"
        density="compact"
        closable
        class="mb-3"
        @click:close="error = null"
      >
        {{ error }}
      </v-alert>

      <div class="d-flex flex-wrap ga-2 align-center mb-2 presence-chips-row">
        <template v-if="snapshot">
          <PresenceStatusChip :status="snapshot.status" variant="flat" density="comfortable" />
          <v-chip v-if="snapshot.room_name" color="surface-variant" variant="outlined" size="small">
            <v-icon start size="14">mdi-floor-plan</v-icon>
            {{ snapshot.room_name }}
          </v-chip>
          <v-chip color="surface-variant" variant="outlined" size="small">
            <v-icon start size="14">mdi-percent-outline</v-icon>
            {{ Math.round(snapshot.confidence * 100) }}%
          </v-chip>
          <v-chip
            v-if="snapshot.dwell_minutes !== null"
            color="surface-variant"
            variant="outlined"
            size="small"
          >
            <v-icon start size="14">mdi-timer-outline</v-icon>
            {{ formatDwell(snapshot.dwell_minutes) }}
          </v-chip>
        </template>
      </div>

      <div class="text-caption text-medium-emphasis presence-last-seen">
        <template v-if="snapshot">
          <span v-if="snapshot.last_seen_at"
            >Last seen {{ formatRelative(snapshot.last_seen_at) }}</span
          >
          <span v-else>No prior sighting recorded.</span>
        </template>
        <template v-else-if="!loading && !error">
          No presence data for {{ personLabel }}.
        </template>
      </div>

      <v-tooltip v-if="snapshot && snapshot.sources?.length" location="bottom">
        <template #activator="{ props: actProps }">
          <div v-bind="actProps" class="text-caption text-medium-emphasis mt-1" tabindex="0">
            Sources: {{ snapshot.sources.map((s) => sourceLabel(s.name)).join(" → ") }}
          </div>
        </template>
        <div>
          <div v-for="s in snapshot.sources" :key="s.name">
            {{ sourceLabel(s.name) }} ({{ Math.round(s.confidence * 100) }}%)
          </div>
          <div v-if="snapshot.notes" class="mt-1 font-italic">{{ snapshot.notes }}</div>
        </div>
      </v-tooltip>
      <div v-else class="text-caption mt-1 presence-sources-placeholder">&nbsp;</div>
    </v-card-text>
  </v-card>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from "vue";
import { cts } from "../../services/cts.js";
import PresenceStatusChip from "./PresenceStatusChip.vue";
import { formatRelative } from "../../composables/useFormatRelative";

const props = defineProps({
  personId: { type: String, required: true },
  personLabel: { type: String, default: null },
  pollSeconds: { type: Number, default: 10 },
  selected: { type: Boolean, default: false },
});

defineEmits(["click"]);

const personLabel = computed(() => props.personLabel || props.personId);

// Maps internal provider names to human-readable labels shown in the Sources tooltip.
const SOURCE_LABELS = {
  cts_location: "Continuous Tracking System",
  ha_bed_sensor: "Bed Sensor",
  ha_device_tracker: "Phone Location",
  night_anchor: "Night Mode (Light Sensor)",
  stale_fallback: "Last Known Location",
  unknown_sentinel: "No Data",
};

function sourceLabel(name) {
  return SOURCE_LABELS[name] ?? name;
}

const snapshot = ref(null);
const loading = ref(false);
const error = ref(null);
let pollTimer = null;
let visibilityListener = null;

async function reload() {
  loading.value = true;
  try {
    snapshot.value = await cts.getPresence(props.personId);
    error.value = null;
  } catch (e) {
    console.error("PresenceWidget reload failed", e);
    error.value = e?.message || "Could not load presence.";
  } finally {
    loading.value = false;
  }
}

function startPolling() {
  stopPolling();
  if (document.visibilityState !== "visible") return;
  pollTimer = setInterval(reload, props.pollSeconds * 1000);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function formatDwell(minutes) {
  if (minutes < 1) return "<1 min";
  if (minutes < 60) return `${Math.round(minutes)} min`;
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes - h * 60);
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

onMounted(() => {
  reload();
  startPolling();
  visibilityListener = () => {
    if (document.visibilityState === "visible") {
      reload();
      startPolling();
    } else {
      stopPolling();
    }
  };
  document.addEventListener("visibilitychange", visibilityListener);
});

onBeforeUnmount(() => {
  stopPolling();
  if (visibilityListener) document.removeEventListener("visibilitychange", visibilityListener);
});

watch(() => props.personId, reload);
</script>

<style scoped>
.text-caption[tabindex="0"]:focus {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
  border-radius: 4px;
}

.presence-widget--selected {
  border: 2px solid rgb(var(--v-theme-primary));
}

.presence-chips-row {
  min-height: 28px;
}

.presence-last-seen {
  min-height: 1.25rem;
}

.presence-sources-placeholder {
  visibility: hidden;
}
</style>
