<template>
  <div>
    <h2 class="text-h5 mb-4">Dashboard</h2>

    <v-row>
      <v-col cols="12" sm="6" md="3" v-for="stat in stats" :key="stat.label">
        <v-card rounded="xl" class="pa-4">
          <div class="d-flex align-center">
            <v-icon :color="stat.color" size="36" class="mr-3">{{ stat.icon }}</v-icon>
            <div>
              <div class="text-h4 font-weight-bold">{{ stat.value }}</div>
              <div class="text-body-2 text-medium-emphasis">{{ stat.label }}</div>
            </div>
          </div>
        </v-card>
      </v-col>
    </v-row>

    <!-- Person Locations -->
    <h3 class="text-h6 mt-6 mb-3">Person Locations</h3>
    <v-row>
      <v-col cols="12" sm="6" md="4" v-for="loc in personLocations" :key="loc.person_id">
        <v-card rounded="xl" class="pa-4">
          <div class="d-flex align-center">
            <v-icon color="primary" size="28" class="mr-3">mdi-account-circle</v-icon>
            <div>
              <div class="font-weight-bold">{{ loc.person_name }}</div>
              <div class="text-body-2">
                <v-icon size="14" class="mr-1">mdi-map-marker</v-icon>
                {{ loc.current_room_name || 'Unknown' }}
                <v-chip size="x-small" class="ml-1">{{ loc.status }}</v-chip>
              </div>
              <div class="text-body-2 text-medium-emphasis" v-if="loc.last_seen_at">
                {{ formatTime(loc.last_seen_at) }}
              </div>
            </div>
          </div>
        </v-card>
      </v-col>
      <v-col v-if="personLocations.length === 0" cols="12">
        <v-alert type="info" variant="tonal">No person location data yet</v-alert>
      </v-col>
    </v-row>

    <!-- Occupancy -->
    <h3 class="text-h6 mt-6 mb-3">Room Occupancy</h3>
    <v-row>
      <v-col cols="12" sm="6" md="4" v-for="(occ, sensorId) in occupancy" :key="sensorId">
        <v-card rounded="xl" class="pa-4">
          <div class="d-flex align-center">
            <v-icon :color="occ.occupied ? 'success' : 'grey'" size="28" class="mr-3">
              {{ occ.occupied ? 'mdi-account' : 'mdi-account-off' }}
            </v-icon>
            <div>
              <div class="font-weight-bold">{{ occ.room }}</div>
              <div class="text-body-2 text-medium-emphasis">
                {{ occ.occupied ? `Since ${formatTime(occ.since)}` : 'Unoccupied' }}
              </div>
            </div>
          </div>
        </v-card>
      </v-col>
      <v-col v-if="Object.keys(occupancy).length === 0" cols="12">
        <v-alert type="info" variant="tonal">No occupancy data available</v-alert>
      </v-col>
    </v-row>

    <!-- Recent Alerts -->
    <h3 class="text-h6 mt-6 mb-3">Recent Alerts</h3>
    <v-card rounded="xl">
      <v-list v-if="alerts.length">
        <v-list-item v-for="alert in alerts" :key="alert.id" :subtitle="alert.description">
          <template #prepend>
            <v-icon :color="alert.resolved ? 'grey' : 'error'">mdi-alert-circle</v-icon>
          </template>
          <template #title>
            {{ alert.alert_type }} – {{ alert.room_name }}
          </template>
        </v-list-item>
      </v-list>
      <v-card-text v-else class="text-center text-medium-emphasis">
        No recent alerts
      </v-card-text>
    </v-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { api } from "../../services/api.js";

const stats = ref([
  { label: "Rooms", value: "–", icon: "mdi-floor-plan", color: "primary" },
  { label: "Sensors", value: "–", icon: "mdi-access-point", color: "secondary" },
  { label: "Rules", value: "–", icon: "mdi-shield-check", color: "accent" },
  { label: "Active Alerts", value: "–", icon: "mdi-alert", color: "error" },
]);
const occupancy = ref({});
const alerts = ref([]);
const personLocations = ref([]);

function formatTime(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString();
}

async function loadData() {
  try {
    const [rooms, sensors, rules, alertData, occData, locData] = await Promise.all([
      api.getRooms().catch(() => []),
      api.getSensors().catch(() => []),
      api.getRules().catch(() => []),
      api.getAlerts({ limit: 5 }).catch(() => []),
      api.getOccupancy().catch(() => ({ occupancy: {} })),
      api.getPersonLocations().catch(() => []),
    ]);
    stats.value[0].value = Array.isArray(rooms) ? rooms.length : 0;
    stats.value[1].value = Array.isArray(sensors) ? sensors.length : 0;
    stats.value[2].value = Array.isArray(rules) ? rules.length : 0;
    const activeAlerts = Array.isArray(alertData)
      ? alertData.filter((a) => !a.resolved)
      : [];
    stats.value[3].value = activeAlerts.length;
    alerts.value = Array.isArray(alertData) ? alertData.slice(0, 5) : [];
    occupancy.value = occData.occupancy || {};
    personLocations.value = Array.isArray(locData) ? locData : [];
  } catch (e) {
    console.error("Failed to load dashboard data:", e);
  }
}

onMounted(loadData);
</script>
