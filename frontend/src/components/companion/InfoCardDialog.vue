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
        <!-- Layout: single_hero -->
        <div v-if="layoutId === 'single_hero' && images.length > 0" class="single-hero mb-4 mt-2">
          <v-img
            :src="images[0].url"
            :width="images[0].width || undefined"
            :height="images[0].height || 220"
            :alt="images[0].alt_text || ''"
            cover
            class="rounded-lg hero-image"
          />
        </div>

        <!-- Layout: side_by_side -->
        <div v-else-if="layoutId === 'side_by_side' && images.length > 0" class="side-by-side mb-4 mt-2">
          <v-img
            :src="images[0].url"
            :width="images[0].width || undefined"
            :height="images[0].height || 180"
            :alt="images[0].alt_text || ''"
            cover
            class="rounded-lg side-image"
          />
          <p class="text-body-1 side-text">{{ body }}</p>
        </div>

        <!-- Layout: gallery_grid_2x2 -->
        <div v-else-if="layoutId === 'gallery_grid_2x2' && images.length > 0" class="gallery-grid mb-4 mt-2">
          <v-img
            v-for="img in images.slice(0, 4)"
            :key="img.slot_id"
            :src="img.url"
            :width="img.width || undefined"
            :height="img.height || 140"
            :alt="img.alt_text || ''"
            cover
            class="rounded-lg grid-image"
          />
        </div>

        <!-- Layout: unknown with images (fallback to vertical column) -->
        <div v-else-if="images.length > 0" class="image-gallery mb-4 mt-2">
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

        <!-- Body text (hidden for side_by_side since it renders inline) -->
        <p v-if="layoutId !== 'side_by_side'" class="text-body-1 body-text">{{ body }}</p>
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
const layoutId = ref("text_only");
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
  layoutId.value = data.layout_id || "text_only";
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
// Self-register on the shared wsClient
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
  border-radius: var(--cc-radius-lg);
}

/* single_hero layout */
.hero-image {
  border: 1px solid var(--cc-surface-3);
}

/* side_by_side layout */
.side-by-side {
  display: flex;
  flex-direction: row;
  gap: 12px;
  align-items: flex-start;
}
.side-image {
  flex: 0 0 45%;
}
.side-text {
  flex: 1;
  line-height: 1.7;
  white-space: pre-wrap;
}

/* gallery_grid_2x2 layout */
.gallery-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.grid-image {
  border: 1px solid var(--cc-surface-3);
}

/* fallback vertical column */
.image-gallery {
  display: flex;
  flex-direction: column;
}
.image-slot {
  border: 1px solid var(--cc-surface-3);
}

.body-text {
  line-height: 1.7;
  white-space: pre-wrap;
  color: var(--cc-text-1);
}

.dismiss-btn {
  letter-spacing: 0.02em;
  font-weight: 600;
  border-radius: var(--cc-radius-md);
}
</style>
