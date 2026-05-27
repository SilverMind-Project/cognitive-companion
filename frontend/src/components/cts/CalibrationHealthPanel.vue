<template>
  <div>
    <div v-if="loading" class="text-body-2 text-medium-emphasis pa-2">Loading calibration health...</div>
    <div v-else-if="error" class="text-body-2 text-error pa-2">{{ error }}</div>
    <div v-else-if="!cameras.length" class="text-body-2 text-medium-emphasis pa-2">
      No enabled cameras found.
    </div>
    <v-card v-else variant="flat" border class="mb-3 px-3 py-2">
      <div class="d-flex align-center flex-wrap ga-3">
        <span class="text-caption font-weight-medium">Calibration Health:</span>
        <span
          v-for="cam in cameras"
          :key="cam.camera_id"
          class="d-flex align-center ga-1"
          style="cursor: pointer"
          :data-testid="`calibration-dot-${cam.camera_id}`"
          @click="$router.push({ name: 'CTSCalibration', query: { camera_id: cam.camera_id } })"
        >
          <span
            class="cal-dot"
            :class="'cal-dot--' + cam.severity"
            :title="`${cam.camera_id}: ${cam.severity}${cam.code ? ' (' + cam.code + ')' : ''}${cam.residual_m != null ? ', residual: ' + cam.residual_m.toFixed(3) + 'm' : ''}`"
          />
          <span class="text-caption">{{ cam.camera_id }}</span>
        </span>
      </div>
    </v-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";

const loading = ref(true);
const error = ref("");
const cameras = ref([]);

async function fetch() {
  loading.value = true;
  error.value = "";
  try {
    const apiKey = localStorage.getItem("cc_api_key") || "";
    const resp = await fetch("/api/v1/cts/calibration/health", {
      headers: { "X-API-Key": apiKey },
    });
    if (resp.ok) cameras.value = await resp.json();
    else error.value = `HTTP ${resp.status}`;
  } catch (e) {
    error.value = e.message || "Failed to load calibration health";
  } finally {
    loading.value = false;
  }
}

onMounted(fetch);
</script>

<style scoped>
.cal-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.cal-dot--ok { background: #4caf50; }
.cal-dot--warning { background: #ff9800; }
.cal-dot--error { background: #f44336; }
</style>
