<template>
  <div>
    <div class="d-flex align-center mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Activity Timeline</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">Unified chronological feed of activities, sessions, and detections.</div>
      </div>
      <v-spacer />
      <v-btn variant="tonal" prepend-icon="mdi-refresh" @click="load" :loading="loading">
        Refresh
      </v-btn>
    </div>

    <v-card class="glass-card">
      <v-card-text class="d-flex ga-4 flex-wrap align-center pa-4">
        <v-select
          v-model="selectedPerson"
          :items="persons"
          item-value="id"
          item-title="name"
          label="Person"
          variant="outlined"
          density="compact"
          clearable
          hide-details
          rounded="lg"
          style="max-width: 240px"
          @update:model-value="onPersonChange"
        />
        <v-select
          v-model="hours"
          :items="timeWindows"
          label="Time Window"
          variant="outlined"
          density="compact"
          hide-details
          rounded="lg"
          style="max-width: 160px"
          @update:model-value="load"
        />
        <v-chip-group column>
          <v-chip @click="toggleSource('activity')" :color="activeSources.includes('activity') ? 'primary' : ''" :variant="activeSources.includes('activity') ? 'flat' : 'tonal'" size="small" rounded="pill">
            <v-icon start size="14">mdi-check-circle</v-icon> Activity
          </v-chip>
          <v-chip @click="toggleSource('session')" :color="activeSources.includes('session') ? 'success' : ''" :variant="activeSources.includes('session') ? 'flat' : 'tonal'" size="small" rounded="pill">
            <v-icon start size="14">mdi-play-circle</v-icon> Session
          </v-chip>
          <v-chip @click="toggleSource('location')" :color="activeSources.includes('location') ? 'info' : ''" :variant="activeSources.includes('location') ? 'flat' : 'tonal'" size="small" rounded="pill">
            <v-icon start size="14">mdi-door</v-icon> Location
          </v-chip>
          <v-chip @click="toggleSource('sighting')" :color="activeSources.includes('sighting') ? 'warning' : ''" :variant="activeSources.includes('sighting') ? 'flat' : 'tonal'" size="small" rounded="pill">
            <v-icon start size="14">mdi-camera</v-icon> Sighting
          </v-chip>
        </v-chip-group>
      </v-card-text>
      <v-divider />
      <template v-if="selectedPerson">
        <PersonTimeline
          ref="timelineRef"
          :person-id="selectedPerson"
          :hours="hours"
          :event-types="activeSources"
        />
      </template>
      <template v-else>
        <div class="pa-4">
          <v-alert type="info" variant="tonal">
            Select a person to view their activity timeline.
          </v-alert>
        </div>
      </template>
    </v-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { api } from "../../services/api.js";
import PersonTimeline from "../../components/person/PersonTimeline.vue";

const persons = ref([]);
const selectedPerson = ref(null);
const hours = ref(24);
const timeWindows = [6, 12, 24, 48, 168];
const activeSources = ref(["activity", "session", "location", "sighting"]);
const loading = ref(false);
const timelineRef = ref(null);

async function loadPersons() {
  try {
    const data = await api.getPersons();
    persons.value = data || [];
  } catch (e) {
    console.error("Failed to load persons:", e);
  }
}

function onPersonChange() {
  // Timeline will auto-load via its own load method
}

function toggleSource(source) {
  const idx = activeSources.value.indexOf(source);
  if (idx >= 0) {
    if (activeSources.value.length > 1) activeSources.value.splice(idx, 1);
  } else {
    activeSources.value.push(source);
  }
  load();
}

async function load() {
  if (!selectedPerson.value) return;
  loading.value = true;
  try {
    if (timelineRef.value) await timelineRef.value.load();
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  loadPersons();
});
</script>
