<template>
  <div>
    <div class="d-flex align-center mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Live Tracking</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Per-camera bbox overlay. Click a tracked identity to issue a manual
          correction. Revisions surface as toasts.
        </div>
      </div>
      <v-spacer />
      <v-chip
        :color="wsStatusColor"
        prepend-icon="mdi-circle"
        size="small"
        variant="tonal"
      >
        {{ wsStatus }}
      </v-chip>
    </div>

    <v-alert
      v-if="error"
      type="error"
      class="mb-4"
      closable
      @click:close="error = ''"
    >
      {{ error }}
    </v-alert>

    <v-card class="glass-card">
      <v-card-text class="d-flex ga-4 align-center pa-4">
        <v-select
          v-model="layout"
          :items="layoutOptions"
          item-title="label"
          item-value="value"
          label="Layout"
          variant="outlined"
          density="compact"
          hide-details
          style="max-width: 200px"
        />
        <v-switch
          v-model="showBboxes"
          color="primary"
          label="Show bboxes"
          density="compact"
          hide-details
        />
        <v-switch
          v-model="showIdLabels"
          color="primary"
          label="Show identity labels"
          density="compact"
          hide-details
        />
        <v-spacer />
        <v-btn
          variant="tonal"
          prepend-icon="mdi-account-edit"
          :to="{ name: 'cts-identity-corrections' }"
        >
          Manage corrections
        </v-btn>
      </v-card-text>

      <v-divider />

      <div :class="gridClass" class="pa-4 ga-4 live-grid">
        <v-card
          v-for="slot in slots"
          :key="slot"
          class="live-tile"
          variant="outlined"
        >
          <v-card-text class="d-flex align-center justify-space-between pa-2">
            <v-chip size="small" variant="tonal">{{
              cameraForSlot(slot)?.camera_id || "—"
            }}</v-chip>
            <span class="text-caption text-medium-emphasis">
              {{ cameraForSlot(slot)?.detections?.length || 0 }} detections
            </span>
          </v-card-text>
          <div class="live-tile-frame" :aria-label="`Live camera ${cameraForSlot(slot)?.camera_id || slot}`">
            <svg
              v-if="cameraForSlot(slot) && showBboxes"
              viewBox="0 0 1000 600"
              class="live-tile-overlay"
              preserveAspectRatio="none"
            >
              <g
                v-for="(det, idx) in cameraForSlot(slot).detections"
                :key="idx"
              >
                <rect
                  :x="(det.bbox.x_min || 0) / 2"
                  :y="(det.bbox.y_min || 0) / 2"
                  :width="((det.bbox.x_max || 0) - (det.bbox.x_min || 0)) / 2"
                  :height="((det.bbox.y_max || 0) - (det.bbox.y_min || 0)) / 2"
                  fill="none"
                  :stroke="det.identity_id ? '#4CAF50' : '#FFC107'"
                  stroke-width="3"
                  @click="openCorrection(det, cameraForSlot(slot))"
                  style="cursor: pointer"
                />
                <text
                  v-if="showIdLabels"
                  :x="(det.bbox.x_min || 0) / 2 + 4"
                  :y="(det.bbox.y_min || 0) / 2 + 14"
                  fill="#fff"
                  font-size="12"
                  font-weight="bold"
                  style="paint-order: stroke; stroke: rgba(0, 0, 0, 0.6); stroke-width: 3"
                >
                  {{ det.identity_id || "unknown" }}
                </text>
              </g>
            </svg>
          </div>
        </v-card>
      </div>
    </v-card>

    <v-snackbar v-model="revisionToast" :timeout="3500" color="info">
      {{ revisionToastText }}
    </v-snackbar>

    <v-dialog v-model="correctionOpen" max-width="520" persistent>
      <v-card>
        <DialogHeader
          icon="mdi-account-convert"
          label="Correct"
          title="Identity"
          @close="correctionOpen = false"
        />
        <v-card-text>
          <div class="text-body-2 mb-2">
            GlobalTrack: <strong>{{ correction.global_track_id }}</strong>
          </div>
          <div class="text-body-2 mb-2">
            Camera: {{ correction.camera_id }}
          </div>
          <div class="text-body-2 mb-4">
            Current identity: {{ correction.previous_identity_id || "unknown" }}
          </div>
          <v-text-field
            v-model="correction.new_identity_id"
            label="New identity id"
            variant="outlined"
            placeholder="Leave blank to mark as UNKNOWN"
          />
          <v-text-field
            v-model="correction.reason"
            label="Reason"
            variant="outlined"
          />
        </v-card-text>
        <DialogFooter
          hint="Correct misidentified persons to improve tracking accuracy."
          confirm-label="Apply override"
          :confirm-loading="saving"
          @cancel="correctionOpen = false"
          @confirm="submitCorrection"
        />
      </v-card>
    </v-dialog>
  </div>
</template>

<script>
import { cts } from "@/services/cts";
import DialogHeader from "@/components/common/DialogHeader.vue";
import DialogFooter from "@/components/common/DialogFooter.vue";

export default {
  name: "CTSLiveView",
  components: { DialogHeader, DialogFooter },
  data() {
    return {
      error: "",
      layout: 4,
      layoutOptions: [
        { label: "1 camera", value: 1 },
        { label: "4 cameras (2x2)", value: 4 },
        { label: "9 cameras (3x3)", value: 9 },
        { label: "16 cameras (4x4)", value: 16 },
      ],
      showBboxes: true,
      showIdLabels: true,
      cameras: {},
      ws: null,
      wsStatus: "connecting",
      revisionToast: false,
      revisionToastText: "",
      correctionOpen: false,
      saving: false,
      correction: {
        global_track_id: "",
        previous_identity_id: "",
        new_identity_id: "",
        camera_id: "",
        reason: "manual",
      },
    };
  },
  computed: {
    slots() {
      return Array.from({ length: this.layout }, (_, i) => i);
    },
    gridClass() {
      if (this.layout === 1) return "d-grid grid-1";
      if (this.layout === 4) return "d-grid grid-2";
      if (this.layout === 9) return "d-grid grid-3";
      return "d-grid grid-4";
    },
    wsStatusColor() {
      if (this.wsStatus === "open") return "success";
      if (this.wsStatus === "connecting") return "warning";
      return "error";
    },
  },
  mounted() {
    this.connect();
  },
  beforeUnmount() {
    if (this.ws) {
      this.ws.close();
    }
  },
  methods: {
    connect() {
      try {
        this.ws = cts.openLiveSocket((msg) => this.onMessage(msg));
        this.ws.onopen = () => (this.wsStatus = "open");
        this.ws.onerror = () => (this.wsStatus = "error");
        this.ws.onclose = () => (this.wsStatus = "closed");
      } catch (err) {
        this.error = String(err.message || err);
        this.wsStatus = "error";
      }
    },
    onMessage(msg) {
      if (msg.type === "cts_live_frame") {
        this.cameras = {
          ...this.cameras,
          [msg.camera_id]: {
            camera_id: msg.camera_id,
            detections: msg.detections || [],
            event_time: msg.event_time,
            room_name: msg.room_name,
          },
        };
      } else if (msg.type === "cts_identity_revision") {
        const prev = msg.previous_identity_id || "unknown";
        const next = msg.new_identity_id || "unknown";
        this.revisionToastText = `Identity corrected: ${prev} → ${next}`;
        this.revisionToast = true;
      }
    },
    cameraForSlot(slot) {
      const ids = Object.keys(this.cameras).sort();
      const id = ids[slot];
      return id ? this.cameras[id] : null;
    },
    openCorrection(det, cam) {
      this.correction = {
        global_track_id: det.global_track_id,
        previous_identity_id: det.identity_id || "",
        new_identity_id: "",
        camera_id: cam?.camera_id || "",
        reason: "manual",
      };
      this.correctionOpen = true;
    },
    async submitCorrection() {
      if (!this.correction.global_track_id) {
        this.error = "No global_track_id on the selected detection.";
        return;
      }
      this.saving = true;
      try {
        await cts.applyCorrection({
          global_track_id: this.correction.global_track_id,
          new_identity_id: this.correction.new_identity_id || null,
          reason: this.correction.reason || "manual",
        });
        this.correctionOpen = false;
      } catch (err) {
        this.error = String(err.message || err);
      } finally {
        this.saving = false;
      }
    },
  },
};
</script>

<style scoped>
.live-grid {
  display: grid;
  gap: 16px;
}
.grid-1 {
  grid-template-columns: 1fr;
}
.grid-2 {
  grid-template-columns: repeat(2, 1fr);
}
.grid-3 {
  grid-template-columns: repeat(3, 1fr);
}
.grid-4 {
  grid-template-columns: repeat(4, 1fr);
}
.live-tile {
  background: var(--cc-surface-2);
}
.live-tile-frame {
  position: relative;
  background: var(--cc-bg);
  aspect-ratio: 16 / 9;
  overflow: hidden;
}
.live-tile-overlay {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
</style>
