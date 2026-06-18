<template>
  <div v-if="state.isActive" class="kiosk-shell">
    <div v-if="state.gateVisible" class="kiosk-gate">
      <v-btn
        class="kiosk-start"
        color="primary"
        variant="flat"
        prepend-icon="mdi-microphone"
        @click="$emit('begin')"
      >
        Tap to begin
      </v-btn>
    </div>

    <v-btn
      class="kiosk-settings-btn"
      icon="mdi-cog"
      variant="tonal"
      size="large"
      @click="openSettings"
    />

    <v-dialog v-model="settingsDialog" max-width="520" persistent>
      <v-card>
        <v-card-title>Kiosk settings</v-card-title>
        <v-card-text>
          <v-form @submit.prevent="save">
            <v-text-field
              v-if="!state.settingsUnlocked"
              v-model="pinEntry"
              label="PIN"
              type="password"
              autocomplete="current-password"
              :error-messages="pinError"
              @keyup.enter="unlock"
            />

            <template v-else>
              <v-switch v-model="form.kioskEnabled" label="Kiosk mode" />
              <v-text-field v-model="form.surfaceId" label="Surface ID" />
              <v-select
                v-model="form.roomId"
                label="Room"
                :items="roomItems"
                :loading="state.roomsLoading"
                item-title="name"
                item-value="id"
                clearable
              />
              <v-text-field
                v-model="form.pin"
                label="Settings PIN"
                type="password"
                autocomplete="new-password"
              />
            </template>
          </v-form>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="settingsDialog = false">Cancel</v-btn>
          <v-btn v-if="!state.settingsUnlocked" color="primary" variant="flat" @click="unlock">
            Unlock
          </v-btn>
          <v-btn v-else color="primary" variant="flat" @click="save">Save</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from "vue";

const props = defineProps({
  state: {
    type: Object,
    required: true,
  },
});

const emit = defineEmits(["begin", "unlock-settings", "save-settings", "load-rooms"]);

const settingsDialog = ref(false);
const pinEntry = ref("");
const pinError = ref("");
const form = reactive({
  kioskEnabled: false,
  surfaceId: "",
  roomId: null,
  pin: "",
});

const roomItems = computed(() =>
  (props.state.rooms || []).map((room) => ({
    id: room.id,
    name: room.name || room.display_name || `Room ${room.id}`,
  })),
);

function syncForm() {
  form.kioskEnabled = props.state.settings.kioskEnabled;
  form.surfaceId = props.state.settings.surfaceId;
  form.roomId = props.state.settings.roomId;
  form.pin = props.state.settings.pin;
}

function openSettings() {
  syncForm();
  pinEntry.value = "";
  pinError.value = "";
  settingsDialog.value = true;
  emit("load-rooms");
}

function unlock() {
  emit("unlock-settings", pinEntry.value);
  if (!props.state.settingsUnlocked) {
    pinError.value = "Invalid PIN";
  } else {
    pinError.value = "";
  }
}

function save() {
  emit("save-settings", { ...form });
  settingsDialog.value = false;
}
</script>

<style scoped>
.kiosk-shell {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 3000;
}

.kiosk-gate {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background: var(--cc-bg);
  pointer-events: auto;
}

.kiosk-start {
  min-width: min(480px, calc(100vw - 48px));
  min-height: 96px;
  border-radius: var(--cc-radius-lg);
  font-size: clamp(1.6rem, 4vw, 2.4rem);
}

.kiosk-settings-btn {
  position: absolute;
  right: 24px;
  bottom: 24px;
  pointer-events: auto;
}
</style>
