<template>
  <div>
    <!-- Current presence tiles (one per person, from usePersonPresence) -->
    <div class="text-subtitle-2 font-weight-bold mb-3">Current Presence</div>

    <v-skeleton-loader v-if="loading" type="card" class="mb-4" />

    <v-row v-else-if="locations.length" dense class="mb-6">
      <v-col v-for="loc in locations" :key="loc.person_id" cols="12" sm="6" md="4">
        <CcMetricTile
          :label="loc.display_name || loc.person_id"
          :value="loc.room_name || 'Unknown'"
          :status="loc.is_inferred ? 'warning' : 'running'"
          :to="`/admin/tracking?panel=presence-timeline&person=${loc.person_id}`"
        >
          <template #sparkline>
            <div class="d-flex align-center ga-2 mt-1">
              <CcProvenanceBadge :source="loc.source" :quality="loc.quality" />
              <v-chip v-if="loc.staleness_seconds > 120" size="x-small" color="warning" variant="tonal">
                {{ Math.round(loc.staleness_seconds / 60) }}m ago
              </v-chip>
            </div>
          </template>
        </CcMetricTile>
      </v-col>
    </v-row>

    <v-alert v-else-if="!loading" type="info" variant="tonal" density="compact" class="mb-6">
      No persons with current location data. Add household members in
      <router-link to="/admin/persons">Persons</router-link>.
    </v-alert>

    <!-- Signal summary from CTS dashboard -->
    <div class="text-subtitle-2 font-weight-bold mb-3">Signal Summary</div>

    <v-skeleton-loader v-if="signalLoading" type="card" class="mb-4" />

    <v-alert v-else-if="signalError" type="error" variant="tonal" density="compact" class="mb-4">
      {{ signalError }}
    </v-alert>

    <v-row v-else-if="signalSummary.length" dense class="mb-4">
      <v-col v-for="s in signalSummary" :key="s.kind" cols="6" sm="4" md="2">
        <v-card :color="severityColor(s.max_severity)" variant="tonal">
          <v-card-text class="text-center pa-3">
            <div class="text-h5 font-weight-bold">{{ s.count }}</div>
            <div class="text-caption">{{ s.kind.replace(/_/g, " ") }}</div>
            <v-chip :color="severityColor(s.max_severity)" size="x-small" class="mt-1" variant="flat">
              {{ s.max_severity }}
            </v-chip>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <v-alert v-else-if="!signalLoading" type="info" variant="tonal" density="compact">
      No signals in the last 24 hours.
    </v-alert>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { cts } from "@/services/cts.js";
import { severityColor } from "@/composables/useCtsSeverity.js";
import CcMetricTile from "@/components/dashboard/CcMetricTile.vue";
import CcProvenanceBadge from "@/components/dashboard/CcProvenanceBadge.vue";

const props = defineProps({
  locations: { type: Array, default: () => [] },
  loading:   { type: Boolean, default: false },
});

const signalSummary = ref([]);
const signalLoading = ref(false);
const signalError = ref(null);

async function loadSignalSummary() {
  signalLoading.value = true;
  try {
    const data = await cts.getSignalSummary();
    const byType = data.by_type || {};
    signalSummary.value = Object.entries(byType).map(([kind, info]) => ({
      kind,
      count: typeof info === "number" ? info : info.count,
      max_severity: typeof info === "object" ? info.max_severity : "info",
    }));
    signalError.value = null;
  } catch (e) {
    signalError.value = e?.message || "Failed to load signal summary";
  } finally {
    signalLoading.value = false;
  }
}

onMounted(loadSignalSummary);
</script>
