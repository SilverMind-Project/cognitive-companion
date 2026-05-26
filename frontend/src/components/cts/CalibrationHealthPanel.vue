<template>
  <div>
    <div v-if="loading" class="text-body-2 text-medium-emphasis pa-4">Loading calibration health...</div>
    <div v-else-if="error" class="text-body-2 text-error pa-4">{{ error }}</div>
    <div v-else-if="!cameras.length" class="text-body-2 text-medium-emphasis pa-4">
      No enabled cameras found.
    </div>
    <div v-else class="d-flex flex-wrap ga-4 pa-2">
      <v-card
        v-for="cam in cameras"
        :key="cam.camera_id"
        class="glass-card"
        width="320"
        :border="true"
      >
        <v-card-item>
          <template #title>
            <span class="text-body-1 font-weight-medium">{{ cam.camera_id }}</span>
          </template>
          <template #subtitle>
            <span v-if="cam.room_name" class="text-body-2">
              Room: {{ cam.room_name }}
            </span>
            <span v-else class="text-body-2 text-warning">Room: unknown</span>
          </template>
        </v-card-item>

        <v-card-text>
          <div class="d-flex align-center ga-2 mb-2">
            <span class="text-caption text-medium-emphasis">Status:</span>
            <v-chip
              v-if="!cam.has_homography"
              size="x-small"
              color="error"
              variant="tonal"
            >
              Not calibrated
            </v-chip>
            <v-chip
              v-else-if="cam.validation"
              size="x-small"
              :color="severityColor(cam.validation.severity)"
              variant="tonal"
            >
              {{ cam.validation.severity }}
            </v-chip>
            <v-chip v-else size="x-small" variant="tonal">Unknown</v-chip>
          </div>

          <div v-if="cam.homography_set_at" class="text-caption text-medium-emphasis mb-1">
            Calibrated: {{ formatDate(cam.homography_set_at) }}
          </div>

          <div v-if="cam.homography_method" class="text-caption text-medium-emphasis mb-2">
            Method: {{ cam.homography_method }}
          </div>

          <v-divider v-if="cam.validation?.issues?.length" class="my-2" />

          <div v-if="cam.validation?.issues?.length">
            <div
              v-for="(issue, idx) in cam.validation.issues"
              :key="idx"
              class="text-caption text-warning mb-1"
            >
              {{ issue }}
            </div>
          </div>
        </v-card-text>

        <v-card-actions>
          <v-btn
            v-if="cam.has_homography"
            size="small"
            variant="text"
            color="primary"
            @click="$emit('test-projection', cam.camera_id)"
          >
            Test Projection
          </v-btn>
        </v-card-actions>
      </v-card>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { cts } from "@/services/cts";
import { useNotify } from "@/composables/useNotify";

const emit = defineEmits(["test-projection"]);
const notify = useNotify();

const loading = ref(true);
const error = ref("");
const cameras = ref([]);

function severityColor(severity) {
  if (severity === "error") return "error";
  if (severity === "warning") return "warning";
  return "success";
}

function formatDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const data = await cts.getCalibrationDiagnostics();
    cameras.value = data.cameras || [];
  } catch (e) {
    error.value = e.message || "Failed to load calibration diagnostics";
    notify.error(error.value);
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>
