<template>
  <v-dialog
    :model-value="visible"
    max-width="520"
    persistent
    no-click-animation
  >
    <v-card class="info-card-dialog">
      <!-- Header: icon, title, countdown -->
      <v-card-item class="pb-0">
        <template #prepend>
          <v-icon color="primary" size="28">mdi-card-text-outline</v-icon>
        </template>
        <v-card-title class="text-h6 font-weight-bold text-wrap" style="line-height: 1.3">
          {{ title }}
        </v-card-title>
        <template #append>
          <v-chip
            :color="countdown <= 5 ? 'error' : 'grey'"
            size="small"
            variant="tonal"
            class="ml-1"
          >
            <v-icon start size="13">mdi-timer-outline</v-icon>
            {{ countdown }}s
          </v-chip>
        </template>
      </v-card-item>

      <v-divider class="mx-4 my-2" />

      <!-- Body -->
      <v-card-text class="pt-0">
        <!-- Image slots -->
        <div v-if="images.length > 0" class="image-gallery mb-4 mt-2">
          <v-img
            v-for="img in images"
            :key="img.slot_id"
            :src="img.url"
            :width="img.width || undefined"
            :height="img.height || 220"
            :alt="img.alt_text || ''"
            cover
            class="rounded-lg mb-2 image-slot"
          />
        </div>

        <!-- Body text -->
        <p class="text-body-1 body-text">{{ body }}</p>
      </v-card-text>

      <v-divider class="mx-4" />

      <!-- Actions -->
      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn
          color="primary"
          variant="flat"
          size="large"
          class="px-8 dismiss-btn"
          @click="dismiss('dismissed')"
        >
          Got it
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from "vue";
import { wsClient } from "../../services/WebSocketClient.js";

// ---------------------------------------------------------------------------
// Dialog visibility & content state
// ---------------------------------------------------------------------------
const visible = ref(false);
const title = ref("");
const body = ref("");
const images = ref([]);
const deliveryId = ref(null);
const dismissSeconds = ref(30);
const countdown = ref(30);

let timer = null;

// ---------------------------------------------------------------------------
// Countdown / auto-dismiss
// ---------------------------------------------------------------------------
function startCountdown() {
  countdown.value = dismissSeconds.value;
  clearInterval(timer);
  timer = setInterval(() => {
    countdown.value--;
    if (countdown.value <= 0) {
      dismiss("timeout");
    }
  }, 1000);
}

function stopCountdown() {
  clearInterval(timer);
  timer = null;
}

// ---------------------------------------------------------------------------
// Dismiss (called on manual close or auto-timeout)
// ---------------------------------------------------------------------------
function dismiss(action) {
  stopCountdown();
  visible.value = false;

  if (deliveryId.value != null) {
    wsClient._sendJson({
      type: "info_card_dismiss",
      delivery_id: deliveryId.value,
      action: action,
    });
  }
}

// ---------------------------------------------------------------------------
// Handle an incoming info_card message
// ---------------------------------------------------------------------------
function handleInfoCard(data) {
  title.value = data.title || "";
  body.value = data.body || "";
  images.value = data.image_slots || [];
  deliveryId.value = data.delivery_id;
  dismissSeconds.value = data.dismiss_seconds || 30;

  visible.value = true;
  startCountdown();

  // Notify the server that the card was displayed (viewed event)
  wsClient._sendJson({
    type: "info_card_dismiss",
    delivery_id: data.delivery_id,
    action: "viewed",
  });
}

// ---------------------------------------------------------------------------
// Self-register on the shared wsClient.  Unrecognised message types
// (info_card, quiz_*, etc.) are routed through the "onStatus" callback.
// ---------------------------------------------------------------------------
function onWsStatus(data) {
  if (data.type === "info_card") {
    handleInfoCard(data);
  }
}

onMounted(() => {
  wsClient.on("onStatus", onWsStatus);
});

onUnmounted(() => {
  stopCountdown();
});

// Allow CompanionView (or tests) to trigger the dialog programmatically.
defineExpose({ show: handleInfoCard });
</script>

<style scoped>
.info-card-dialog {
  border-radius: 16px;
}

.image-gallery {
  display: flex;
  flex-direction: column;
}

.image-slot {
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.body-text {
  line-height: 1.7;
  white-space: pre-wrap;
  color: rgba(255, 255, 255, 0.87);
}

.dismiss-btn {
  letter-spacing: 0.02em;
  font-weight: 600;
  border-radius: 12px;
}
</style>
