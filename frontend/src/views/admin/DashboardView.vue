<template>
  <div>
    <div class="d-flex align-center mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Dashboard</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">A live snapshot of the household and the system's health.</div>
      </div>
      <v-spacer />
      <v-btn variant="tonal" prepend-icon="mdi-refresh" @click="loadData" :loading="refreshing">
        Refresh
      </v-btn>
    </div>

    <!-- Stats Row -->
    <v-row>
      <v-col cols="12" sm="6" md="3" v-for="stat in stats" :key="stat.label">
        <v-card class="pa-5 stat-card" :to="stat.to" :ripple="!!stat.to">
          <div class="d-flex align-center">
            <v-avatar :color="stat.color" size="48" variant="tonal" class="mr-4">
              <v-icon size="24">{{ stat.icon }}</v-icon>
            </v-avatar>
            <div>
              <div class="text-h4 font-weight-bold tracking-tight">{{ stat.value }}</div>
              <div class="text-body-2 text-medium-emphasis">{{ stat.label }}</div>
            </div>
          </div>
        </v-card>
      </v-col>
    </v-row>

    <!-- System Health -->
    <h3 class="text-h6 mt-6 mb-3">System Health</h3>
    <v-row>
      <v-col cols="12" sm="6" md="4" v-for="svc in healthServices" :key="svc.name">
        <v-card class="pa-4">
          <div class="d-flex align-center">
            <v-icon :color="svc.color ?? (svc.ok ? 'success' : 'error')" size="24" class="mr-3">
              {{ svc.ok ? 'mdi-check-circle' : 'mdi-alert-circle' }}
            </v-icon>
            <div>
              <div class="font-weight-medium">{{ svc.name }}</div>
              <div class="text-body-2 text-medium-emphasis">{{ svc.detail }}</div>
            </div>
          </div>
        </v-card>
      </v-col>
    </v-row>

    <!-- Person Locations -->
    <h3 class="text-h6 mt-6 mb-3">Person Locations</h3>
    <v-row>
      <v-col cols="12" sm="6" md="4" v-for="loc in personLocations" :key="loc.person_id">
        <v-card class="pa-4">
          <div class="d-flex align-center">
            <v-avatar color="primary" size="40" variant="tonal" class="mr-3">
              <v-icon>mdi-account</v-icon>
            </v-avatar>
            <div class="flex-grow-1">
              <div class="font-weight-bold">{{ loc.person_name }}</div>
              <div class="text-body-2 d-flex align-center">
                <v-icon size="14" class="mr-1">mdi-map-marker</v-icon>
                {{ loc.current_room_name || 'Unknown' }}
                <v-chip size="x-small" :color="locStatusColor(loc.status)" class="ml-2">{{ loc.status }}</v-chip>
              </div>
              <div class="text-caption text-medium-emphasis" v-if="loc.last_seen_at">
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

    <!-- Room Occupancy -->
    <h3 class="text-h6 mt-6 mb-3">Room Occupancy</h3>
    <v-row>
      <v-col cols="12" sm="6" md="4" v-for="(occ, roomKey) in occupancy" :key="roomKey">
        <v-card class="pa-4">
          <div class="d-flex align-center">
            <v-avatar :color="occ.occupied ? 'success' : 'grey'" size="40" variant="tonal" class="mr-3">
              <v-icon>{{ occ.occupied ? 'mdi-home-account' : 'mdi-home-outline' }}</v-icon>
            </v-avatar>
            <div class="flex-grow-1">
              <div class="font-weight-bold">{{ occ.room_name }}</div>
              <div class="text-body-2 text-medium-emphasis">
                {{ occ.occupied ? `Since ${formatTime(occ.since)}` : 'Unoccupied' }}
              </div>
              <div v-if="occ.person_ids && occ.person_ids.length" class="text-caption mt-1">
                <v-chip
                  v-for="pid in occ.person_ids"
                  :key="pid"
                  size="x-small"
                  color="primary"
                  variant="tonal"
                  class="mr-1"
                >{{ personName(pid) }}</v-chip>
              </div>
              <div class="text-caption text-disabled mt-1">
                via {{ occ.source === 'cts' ? 'Camera' : occ.source === 'ha_sensor' ? 'Motion Sensor' : occ.source }}
              </div>
            </div>
          </div>
        </v-card>
      </v-col>
      <v-col v-if="Object.keys(occupancy).length === 0" cols="12">
        <v-alert type="info" variant="tonal">No occupancy data available yet</v-alert>
      </v-col>
    </v-row>

    <!-- Recent Alerts -->
    <h3 class="text-h6 mt-6 mb-3">Recent Alerts</h3>
    <v-card>
      <v-list v-if="alerts.length">
        <v-list-item v-for="alert in alerts" :key="alert.id" :subtitle="alert.description">
          <template #prepend>
            <v-icon :color="alert.resolved ? 'grey' : 'error'">
              {{ alert.resolved ? 'mdi-check-circle' : 'mdi-alert-circle' }}
            </v-icon>
          </template>
          <template #title>
            {{ alert.alert_type }} &middot; {{ alert.room_name }}
          </template>
          <template #append>
            <span class="text-caption text-medium-emphasis">{{ formatTime(alert.created_at) }}</span>
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
import { formatDateTimeShort } from "../../services/timezone.js";

const refreshing = ref(false);

const stats = ref([
  { label: "Rooms", value: "-", icon: "mdi-floor-plan", color: "primary", to: "/admin/rooms" },
  { label: "Sensors", value: "-", icon: "mdi-access-point", color: "secondary", to: "/admin/sensors" },
  { label: "Rules", value: "-", icon: "mdi-shield-check", color: "accent", to: "/admin/rules" },
  { label: "Active Alerts", value: "-", icon: "mdi-alert", color: "error", to: "/admin/alerts" },
]);

const healthServices = ref([]);
const occupancy = ref({});
const alerts = ref([]);
const personLocations = ref([]);

const formatTime = formatDateTimeShort;

// Map person_id → display name built from person locations list.
const personNameMap = ref({});

function personName(personId) {
  return personNameMap.value[personId] || personId;
}

function locStatusColor(status) {
  const map = { home: "success", away: "warning", unknown: "grey", sleeping: "info" };
  return map[status] || "grey";
}

async function loadData() {
  refreshing.value = true;
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
    const locList = Array.isArray(locData) ? locData : [];
    personLocations.value = locList;
    // Build id→name map so occupancy cards can show names instead of raw IDs.
    const nameMap = {};
    for (const loc of locList) {
      if (loc.person_id && loc.person_name) nameMap[loc.person_id] = loc.person_name;
    }
    personNameMap.value = nameMap;
  } catch (e) {
    console.error("Failed to load dashboard data:", e);
  }

  // Health checks
  const services = [];
  try {
    const h = await api.health();
    services.push({ name: "Backend", ok: h?.status === "ok", detail: h?.version || "Running" });
  } catch {
    services.push({ name: "Backend", ok: false, detail: "Unreachable" });
  }

  try {
    const pid = await api.personIdHealth();
    if (!pid.configured) {
      services.push({ name: "Person-ID Service", ok: false, detail: "Not configured" });
    } else if (pid.status === "unreachable") {
      services.push({ name: "Person-ID Service", ok: false, detail: "Unreachable" });
    } else {
      const gpu = pid.gpu_available ? "GPU" : "CPU";
      const model = pid.model || "unknown";
      services.push({ name: "Person-ID Service", ok: true, detail: `${model} · ${pid.enrolled_members} enrolled · ${gpu}` });
    }
  } catch {
    services.push({ name: "Person-ID Service", ok: false, detail: "Unreachable" });
  }

  try {
    const tts = await api.ttsHealth();
    if (!tts.configured) {
      services.push({ name: "TTS Service", ok: false, detail: "Not configured" });
    } else if (tts.status === "unreachable") {
      services.push({ name: "TTS Service", ok: false, detail: "Unreachable" });
    } else {
      const engine = tts.default_engine || "unknown";
      const gpu = tts.gpu_available ? (tts.gpu_name || "GPU") : "CPU";
      services.push({ name: "TTS Service", ok: true, detail: `${engine} · ${gpu}` });
    }
  } catch {
    services.push({ name: "TTS Service", ok: false, detail: "Unreachable" });
  }

  try {
    const to = await api.trackingOrchestratorHealth();
    if (!to.configured) {
      services.push({ name: "Tracking Orchestrator", ok: false, detail: "Not configured" });
    } else if (to.status === "unreachable") {
      services.push({ name: "Tracking Orchestrator", ok: false, detail: "Unreachable" });
    } else {
      const st = to.status || "unknown";
      const ver = to.version ? ` · v${to.version}` : "";
      services.push({ name: "Tracking Orchestrator", ok: st === "healthy", detail: `${st}${ver}` });
    }
  } catch {
    services.push({ name: "Tracking Orchestrator", ok: false, detail: "Unreachable" });
  }

  try {
    const th = await api.tritonHealth();
    if (!th.configured) {
      services.push({ name: "Triton Inference Server", ok: false, detail: "Not configured" });
    } else if (th.status === "unreachable") {
      services.push({ name: "Triton Inference Server", ok: false, detail: "Unreachable" });
    } else {
      services.push({ name: "Triton Inference Server", ok: th.status === "ready", detail: th.status === "ready" ? "Ready" : "Not ready" });
    }
  } catch {
    services.push({ name: "Triton Inference Server", ok: false, detail: "Unreachable" });
  }

  try {
    const sa = await api.sceneAnalysisHealth();
    if (!sa.configured) {
      services.push({ name: "Scene Analysis", ok: false, detail: "Not configured" });
    } else if (sa.status === "unreachable") {
      services.push({ name: "Scene Analysis", ok: false, detail: "Unreachable" });
    } else {
      const parts = [];
      if (sa.detector_available) parts.push("detector");
      if (sa.describer_available) parts.push("describer");
      if (sa.embedder_available) parts.push("embedder");
      const detail = parts.length ? parts.join(" · ") : (sa.status || "ok");
      services.push({ name: "Scene Analysis", ok: sa.status === "ok", detail });
    }
  } catch {
    services.push({ name: "Scene Analysis", ok: false, detail: "Unreachable" });
  }

  try {
    const sm = await api.semanticMemoryHealth();
    if (!sm.configured) {
      services.push({ name: "Semantic Memory", ok: false, detail: "Not configured" });
    } else if (sm.status === "unreachable") {
      services.push({ name: "Semantic Memory", ok: false, detail: "Unreachable" });
    } else {
      services.push({ name: "Semantic Memory", ok: sm.status === "healthy", detail: sm.status || "healthy" });
    }
  } catch {
    services.push({ name: "Semantic Memory", ok: false, detail: "Unreachable" });
  }

  try {
    const llmResults = await api.llmHealth();
    for (const m of llmResults) {
      if (m.status === "success") {
        services.push({ name: m.name, ok: true, detail: m.configured_model });
      } else if (m.status === "warning") {
        services.push({ name: m.name, ok: false, color: "warning", detail: m.detail });
      } else {
        services.push({ name: m.name, ok: false, detail: m.detail || "Unreachable" });
      }
    }
  } catch {
    services.push({ name: "LLM Models", ok: false, detail: "Health check failed" });
  }

  healthServices.value = services;
  refreshing.value = false;
}

onMounted(loadData);
</script>

<style scoped>
.stat-card {
  transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
  cursor: pointer;
}
.stat-card:hover {
  transform: translateY(-2px);
  border-color: var(--cc-brand-soft);
  box-shadow: var(--cc-shadow-lg);
}
.tracking-tight {
  letter-spacing: -0.018em;
}
</style>
