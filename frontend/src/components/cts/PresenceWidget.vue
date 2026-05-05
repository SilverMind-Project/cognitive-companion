<template>
  <v-card class="glass-card">
    <v-card-text class="pa-4">
      <div class="d-flex align-center mb-3">
        <v-icon size="20" class="mr-2">mdi-map-marker-radius</v-icon>
        <div class="text-subtitle-1 font-weight-medium">{{ personLabel }}</div>
        <v-spacer />
        <v-tooltip location="top" v-if="snapshot">
          <template #activator="{ props: actProps }">
            <v-btn
              v-bind="actProps"
              icon="mdi-refresh"
              size="x-small"
              variant="text"
              :loading="loading"
              aria-label="Refresh presence"
              @click="reload"
            />
          </template>
          Refresh now (auto-refreshes every {{ pollSeconds }}s)
        </v-tooltip>
      </div>

      <v-progress-linear v-if="loading && !snapshot" indeterminate color="primary" class="mb-2" />
      <v-alert v-if="error" type="error" variant="tonal" density="compact" closable class="mb-3" @click:close="error = null">
        {{ error }}
      </v-alert>

      <div v-if="snapshot" class="d-flex flex-wrap ga-2 align-center mb-2">
        <PresenceStatusChip :status="snapshot.status" variant="flat" density="comfortable" />
        <v-chip v-if="snapshot.room_name" color="surface-variant" variant="outlined" size="small">
          <v-icon start size="14">mdi-floor-plan</v-icon>
          {{ snapshot.room_name }}
        </v-chip>
        <v-chip color="surface-variant" variant="outlined" size="small">
          <v-icon start size="14">mdi-percent-outline</v-icon>
          {{ Math.round(snapshot.confidence * 100) }}%
        </v-chip>
        <v-chip v-if="snapshot.dwell_minutes !== null" color="surface-variant" variant="outlined" size="small">
          <v-icon start size="14">mdi-timer-outline</v-icon>
          {{ formatDwell(snapshot.dwell_minutes) }}
        </v-chip>
      </div>

      <div v-if="snapshot" class="text-caption text-medium-emphasis">
        <span v-if="snapshot.last_seen_at">Last seen {{ formatRelative(snapshot.last_seen_at) }}</span>
        <span v-else>No prior sighting recorded.</span>
      </div>

      <v-tooltip v-if="snapshot && snapshot.sources?.length" location="bottom">
        <template #activator="{ props: actProps }">
          <div v-bind="actProps" class="text-caption text-medium-emphasis mt-1" tabindex="0">
            Sources: {{ snapshot.sources.map(s => s.name).join(" → ") }}
          </div>
        </template>
        <div>
          <div v-for="s in snapshot.sources" :key="s.name">
            {{ s.name }} ({{ Math.round(s.confidence * 100) }}%)
          </div>
          <div v-if="snapshot.notes" class="mt-1 font-italic">{{ snapshot.notes }}</div>
        </div>
      </v-tooltip>

      <div v-if="!loading && !snapshot && !error" class="text-center text-medium-emphasis py-4">
        No presence data for {{ personLabel }}.
      </div>
    </v-card-text>
  </v-card>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from "vue";
import { cts } from "../../services/cts.js";
import PresenceStatusChip from "./PresenceStatusChip.vue";

const props = defineProps({
  personId: { type: String, required: true },
  personLabel: { type: String, default: null },
  pollSeconds: { type: Number, default: 10 },
});

const personLabel = computed(() => props.personLabel || props.personId);

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

function formatRelative(iso) {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const secs = Math.abs(Math.floor(diff / 1000));
  if (secs < 60) return secs < 10 ? "just now" : `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return mins === 1 ? "1 min ago" : `${mins} min ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return hrs === 1 ? "1 hr ago" : `${hrs} hr ago`;
  const days = Math.floor(hrs / 24);
  return days === 1 ? "yesterday" : `${days} days ago`;
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
</style>
