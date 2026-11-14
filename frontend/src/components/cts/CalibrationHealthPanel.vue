<template>
  <div>
    <div v-if="loading" class="text-body-2 text-medium-emphasis pa-2">
      Loading calibration health...
    </div>
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
          @click="emit('test-projection', cam.camera_id)"
        >
          <span class="cal-dot" :class="'cal-dot--' + cam.severity" :title="describe(cam)" />
          <span class="text-caption">{{ cam.camera_id }}</span>
        </span>
      </div>
    </v-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { useNotify } from "@/composables/useNotify";
import { cts } from "@/services/cts.js";

const emit = defineEmits(["test-projection"]);

const loading = ref(true);
const cameras = ref([]);
const { notify } = useNotify();

async function loadHealth() {
  loading.value = true;
  try {
    // The endpoint returns { cameras, generated_at }; the panel renders the camera rows.
    const health = await cts.getCalibrationHealth();
    cameras.value = health?.cameras ?? [];
  } catch (e) {
    notify.error(e.message || "Failed to load calibration health");
  } finally {
    loading.value = false;
  }
}

const CODE_TEXT = {
  not_calibrated: "not calibrated (tracks in its own virtual room)",
  elevated_residual: "calibration error is elevated",
  high_residual: "calibration error is too high",
  runtime_matrix_missing: "saved but not yet in use by tracking",
  db_matrix_missing: "in use by tracking but no longer saved",
};

function describe(cam) {
  const what = cam.code ? CODE_TEXT[cam.code] || cam.code : "calibrated";
  const residual = cam.residual_m != null ? `, error ${cam.residual_m.toFixed(2)} m` : "";
  return `${cam.camera_id}: ${what}${residual}`;
}

defineExpose({ reload: loadHealth });

onMounted(loadHealth);
</script>

<style scoped>
.cal-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.cal-dot--ok {
  background: var(--cc-success);
}
.cal-dot--warning {
  background: var(--cc-warning);
}
.cal-dot--error {
  background: var(--cc-error);
}
/* Not calibrated: tracked in its own virtual room, so neither healthy nor failing. */
.cal-dot--info {
  border: 1.5px solid var(--cc-text-3);
}
</style>
