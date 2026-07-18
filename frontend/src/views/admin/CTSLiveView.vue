<template>
  <div>
    <div class="d-flex align-center flex-wrap ga-3" :class="embedded ? 'mb-4' : 'mb-6'">
      <div>
        <h2 :class="embedded ? 'text-h6' : 'text-h4'" class="font-weight-bold tracking-tight">
          Live Tracking
        </h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Per-camera bbox overlay. Click a tracked identity to issue a manual correction. Revisions
          surface as toasts.
        </div>
      </div>
      <v-spacer />
      <v-chip :color="wsStatusColor" prepend-icon="mdi-circle" size="small" variant="tonal">
        {{ wsStatus }}
      </v-chip>
    </div>

    <v-alert v-if="error" type="error" class="mb-4" closable @click:close="error = ''">
      {{ error }}
    </v-alert>

    <v-card class="glass-card">
      <LiveToolbar
        v-model:layout="layout"
        v-model:show-bboxes="showBboxes"
        v-model:show-id-labels="showIdLabels"
        v-model:show-trail="showTrail"
        v-model:show-pose="showPose"
        v-model:show-evidence="showEvidence"
        v-model:show-posture="showPosture"
        :layout-options="layoutOptions"
      />

      <CrossCameraBanner v-if="multiCameraIdentities.length > 0" :entries="multiCameraIdentities" />

      <v-divider />

      <div :class="gridClass" class="pa-4 ga-4 live-grid">
        <LiveCameraTile
          v-for="slot in slots"
          :key="slot"
          :slot-index="slot"
          :camera-id="cameraIdForSlot(slot)"
          :camera="cameraForSlot(slot)"
          :available-cameras="availableCameras"
          :layout="layout"
          :show-bboxes="showBboxes"
          :show-id-labels="showIdLabels"
          :show-trail="showTrail"
          :show-pose="showPose"
          :show-evidence="showEvidence"
          :show-posture="showPosture"
          :marauders-enabled="maraudersState.enabled"
          :tile-style="tileLinkStyle(cameraIdForSlot(slot))"
          :link-entries="tileLinkEntries(cameraIdForSlot(slot))"
          :snapshot-url="snapshotUrls[cameraIdForSlot(slot)]"
          :display-src="displaySrc"
          :is-stale="isCameraStale(cameraForSlot(slot))"
          :stale-label-text="staleLabel(cameraForSlot(slot))"
          :is-multi-camera="isMultiCamera"
          :multi-camera-count="multiCameraCount"
          :multi-camera-tooltip="multiCameraTooltip"
          :bbox-color="bboxColor"
          @camera-change="(val) => onSlotCameraChange(slot, val)"
          @frame-error="onFrameError"
          @open-correction="openCorrection"
        />
      </div>
    </v-card>

    <CorrectionDialog
      v-model="correctionOpen"
      v-model:correction="correction"
      :saving="saving"
      @confirm="submitCorrection"
    />
  </div>
</template>

<script setup>
import { ref, computed } from "vue";
import { useDisplaySrc, useBlurMode } from "@/composables/useBlurMode.js";
import { useMaraudersMode } from "@/composables/useMaraudersMode.js";
import { useCtsLiveCameras } from "@/composables/useCtsLiveCameras.js";
import { useMultiCameraLinks } from "@/composables/useMultiCameraLinks.js";
import { cts } from "@/services/cts";
import LiveToolbar from "@/components/cts/live/LiveToolbar.vue";
import CrossCameraBanner from "@/components/cts/live/CrossCameraBanner.vue";
import LiveCameraTile from "@/components/cts/live/LiveCameraTile.vue";
import CorrectionDialog from "@/components/cts/live/CorrectionDialog.vue";

defineProps({
  embedded: { type: Boolean, default: false },
});

const { state: maraudersState } = useMaraudersMode();

const error = ref("");
const layout = ref(4);
const layoutOptions = [
  { label: "1 camera", value: 1 },
  { label: "4 cameras (2x2)", value: 4 },
  { label: "9 cameras (3x3)", value: 9 },
  { label: "16 cameras (4x4)", value: 16 },
];
const showBboxes = ref(true);
const showIdLabels = ref(true);
const showTrail = ref(false);
const showPose = ref(false);
const showEvidence = ref(false);
const showPosture = ref(true);

const { blurMode } = useBlurMode();
const { displaySrc } = useDisplaySrc(blurMode);

const {
  cameras,
  snapshotUrls,
  wsStatus,
  availableCameras,
  cameraIdForSlot,
  onSlotCameraChange,
  cameraForSlot,
  onFrameError,
  isCameraStale,
  staleLabel,
} = useCtsLiveCameras(layout);

const {
  multiCameraIdentities,
  isMultiCamera,
  multiCameraCount,
  multiCameraTooltip,
  bboxColor,
  tileLinkStyle,
  tileLinkEntries,
} = useMultiCameraLinks(cameras);

const correctionOpen = ref(false);
const saving = ref(false);
const correction = ref({
  ph_id: "",
  previous_identity_id: "",
  new_identity_id: "",
  camera_id: "",
  reason: "manual",
});

const slots = computed(() => Array.from({ length: layout.value }, (_, i) => i));

const gridClass = computed(() => {
  if (layout.value === 1) return "d-grid grid-1";
  if (layout.value === 4) return "d-grid grid-2";
  if (layout.value === 9) return "d-grid grid-3";
  return "d-grid grid-4";
});

const wsStatusColor = computed(() => {
  if (wsStatus.value === "open") return "success";
  if (wsStatus.value === "connecting") return "warning";
  return "error";
});

function openCorrection(det, cam) {
  correction.value = {
    ph_id: det.ph_id,
    previous_identity_id: det.identity_id || "",
    new_identity_id: "",
    camera_id: cam?.camera_id || "",
    reason: "manual",
  };
  correctionOpen.value = true;
}

async function submitCorrection() {
  if (!correction.value.ph_id) {
    error.value = "No ph_id on the selected detection.";
    return;
  }
  saving.value = true;
  try {
    await cts.applyCorrection({
      ph_id: correction.value.ph_id,
      new_identity_id: correction.value.new_identity_id || null,
      reason: correction.value.reason || "manual",
    });
    correctionOpen.value = false;
  } catch (err) {
    error.value = String(err.message || err);
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped>
.live-grid {
  display: grid;
  gap: 16px;
  align-items: start;
}
.grid-1 {
  grid-template-columns: minmax(0, 1fr);
}
.grid-2 {
  grid-template-columns: repeat(2, minmax(320px, 1fr));
}
.grid-3 {
  grid-template-columns: repeat(3, minmax(260px, 1fr));
}
.grid-4 {
  grid-template-columns: repeat(4, minmax(220px, 1fr));
}
.live-toolbar-action {
  margin-left: auto;
}

@media (max-width: 1400px) {
  .grid-4 {
    grid-template-columns: repeat(2, minmax(280px, 1fr));
  }
}

@media (max-width: 1100px) {
  .grid-3 {
    grid-template-columns: repeat(2, minmax(280px, 1fr));
  }
}

@media (max-width: 760px) {
  .grid-2,
  .grid-3,
  .grid-4 {
    grid-template-columns: minmax(0, 1fr);
  }

  .live-toolbar-action {
    margin-left: 0;
    width: 100%;
  }
}
</style>
