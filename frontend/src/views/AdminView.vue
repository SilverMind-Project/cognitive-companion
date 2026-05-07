<template>
  <v-app>
    <v-navigation-drawer permanent rail expand-on-hover :width="260" rail-width="68">
      <div class="d-flex align-center px-3 py-4 admin-brand">
        <div class="cc-brand-mark mr-3" aria-hidden="true">
          <img class="cc-brand-logo" src="/favicon.svg" alt="" />
        </div>
        <div class="brand-text">
          <div class="text-subtitle-1 font-weight-bold cc-gradient-text">Cognitive Companion</div>
          <!-- <div class="text-caption text-medium-emphasis">Companion</div> -->
        </div>
      </div>

      <v-list density="comfortable" nav>
        <v-list-item rounded="lg" prepend-icon="mdi-home-variant-outline" title="Companion" to="/" />
        <v-divider class="my-2 mx-3" />
        <v-list-item rounded="lg" prepend-icon="mdi-view-dashboard-outline" title="Dashboard" to="/admin/dashboard" />

        <v-list-subheader class="mt-2">Automation</v-list-subheader>
        <v-list-item rounded="lg" prepend-icon="mdi-shield-check-outline" title="Rules" to="/admin/rules" />
        <v-list-item rounded="lg" prepend-icon="mdi-sitemap-outline" title="Workflows" to="/admin/workflows" />
        <v-list-item rounded="lg" prepend-icon="mdi-calendar-text-outline" title="Events" to="/admin/events" />

        <v-list-subheader class="mt-2">Infrastructure</v-list-subheader>
        <v-list-item rounded="lg" prepend-icon="mdi-access-point" title="Sensors" to="/admin/sensors" />
        <v-list-item rounded="lg" prepend-icon="mdi-floor-plan" title="Rooms" to="/admin/rooms" />
        <v-list-item rounded="lg" prepend-icon="mdi-camera-burst" title="Camera Media" to="/admin/camera-media" />
        <v-list-item rounded="lg" prepend-icon="mdi-image-edit-outline" title="E-Ink Templates" to="/admin/eink-templates" />

        <v-list-subheader class="mt-2">Tracking (CTS)</v-list-subheader>
        <v-list-item rounded="lg" prepend-icon="mdi-view-dashboard-outline" title="Dashboard" to="/admin/cts/dashboard" />
        <v-list-item rounded="lg" prepend-icon="mdi-video-outline" title="Live View" to="/admin/cts/live" />
        <v-list-item rounded="lg" prepend-icon="mdi-cctv" title="Cameras" to="/admin/cts/cameras" />
        <v-list-item rounded="lg" prepend-icon="mdi-crosshairs-gps" title="Calibration" to="/admin/cts/calibration" />
        <v-list-item rounded="lg" prepend-icon="mdi-eye-off-outline" title="Privacy Zones" to="/admin/cts/privacy" />
        <v-list-item rounded="lg" prepend-icon="mdi-graph-outline" title="Camera Adjacency" to="/admin/cts/adjacency" />
        <v-list-item rounded="lg" prepend-icon="mdi-account-edit-outline" title="Identity Corrections" to="/admin/cts/identity-corrections" />
        <v-list-item rounded="lg" prepend-icon="mdi-alert-circle-outline" title="Signals" to="/admin/cts/signals" />
        <v-list-item rounded="lg" prepend-icon="mdi-image-search-outline" title="Keyframes" to="/admin/cts/keyframes" />
        <v-list-item rounded="lg" prepend-icon="mdi-map-marker-radius" title="Presence Fusion" to="/admin/cts/presence" />

        <v-list-subheader class="mt-2">People</v-list-subheader>
        <v-list-item rounded="lg" prepend-icon="mdi-account-group-outline" title="Members &amp; Enrollment" to="/admin/persons" />
        <v-list-item rounded="lg" prepend-icon="mdi-run" title="Activities" to="/admin/activities" />
        <v-list-item rounded="lg" prepend-icon="mdi-timeline-text-outline" title="Timeline" to="/admin/timeline" />
        <v-list-item rounded="lg" prepend-icon="mdi-chart-box" title="Daily Reports" to="/admin/reports" />
        <v-list-item rounded="lg" prepend-icon="mdi-alert-circle-outline" title="Alerts" to="/admin/alerts" />
      </v-list>
    </v-navigation-drawer>

    <v-app-bar flat>
      <v-app-bar-title>
        <span class="text-h6 font-weight-bold">Caregiver Console</span>
      </v-app-bar-title>
      <v-spacer />
      <div class="theme-toggle" :title="isDark ? 'Switch to light theme' : 'Switch to dark theme'" @click="toggleTheme">
        <div class="theme-toggle__track" :class="{ 'theme-toggle__track--dark': isDark }">
          <v-icon class="theme-toggle__icon theme-toggle__icon--sun" size="14">mdi-white-balance-sunny</v-icon>
          <v-icon class="theme-toggle__icon theme-toggle__icon--moon" size="14">mdi-moon-waning-crescent</v-icon>
          <div class="theme-toggle__thumb" :class="{ 'theme-toggle__thumb--dark': isDark }" />
        </div>
      </div>
      <v-btn icon="mdi-refresh" variant="text" title="Reload config" @click="reloadConfig" />
      <v-btn size="small" variant="tonal" class="mx-2" @click="showKeyDialog = true">
        <v-icon start>mdi-key-variant</v-icon>
        API Key
      </v-btn>
    </v-app-bar>

    <v-main>
      <v-container fluid class="px-6 py-6 cc-main-container">
        <router-view v-slot="{ Component }">
          <transition name="fade-slide" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </v-container>
    </v-main>

    <!-- API Key dialog -->
    <v-dialog v-model="showKeyDialog" max-width="440">
      <v-card>
        <v-card-title>Set API Key</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="apiKeyInput"
            label="API Key"
            :type="showKey ? 'text' : 'password'"
            hide-details
            :append-inner-icon="showKey ? 'mdi-eye-off' : 'mdi-eye'"
            @click:append-inner="showKey = !showKey"
          />
        </v-card-text>
        <v-card-actions class="px-6 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="showKeyDialog = false">Cancel</v-btn>
          <v-btn color="primary" variant="flat" @click="saveApiKey">Save</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snack" :color="snackColor" timeout="3000">
      {{ snackText }}
    </v-snackbar>
  </v-app>
</template>

<script setup>
import { ref, onMounted, computed } from "vue";
import { useTheme } from "vuetify";
import { api } from "../services/api.js";

const theme = useTheme();
const isDark = computed(() => theme.global.name.value === "ccDark");

function toggleTheme() {
  const newTheme = isDark.value ? "ccLight" : "ccDark";
  theme.global.name.value = newTheme;
  localStorage.setItem("cc_theme", newTheme);
}

const showKeyDialog = ref(false);
const showKey = ref(false);
const apiKeyInput = ref(localStorage.getItem("cc_api_key") || "");
const snack = ref(false);
const snackText = ref("");
const snackColor = ref("success");

function saveApiKey() {
  api.setApiKey(apiKeyInput.value);
  showKeyDialog.value = false;
  notify("API key saved");
}

async function reloadConfig() {
  try {
    await api.reloadConfig();
    notify("Config reloaded");
  } catch (e) {
    notify(e.message, "error");
  }
}

function notify(text, color = "success") {
  snackText.value = text;
  snackColor.value = color;
  snack.value = true;
}

onMounted(() => {
  if (!localStorage.getItem("cc_api_key")) {
    showKeyDialog.value = true;
  }
});
</script>

<style scoped>
.admin-brand {
  min-height: 56px;
}

.cc-brand-mark {
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.cc-brand-logo {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.brand-text {
  white-space: nowrap;
  overflow: hidden;
  opacity: 1;
  transition: opacity 0.18s ease;
}

.v-navigation-drawer--rail:not(.v-navigation-drawer--is-hovering) .brand-text {
  opacity: 0;
}

.theme-toggle {
  display: flex;
  align-items: center;
  cursor: pointer;
  padding: 6px;
  border-radius: var(--cc-radius-pill);
  transition: background-color 0.2s ease;
}
.theme-toggle:hover {
  background-color: var(--cc-surface-2);
}

.theme-toggle__track {
  position: relative;
  width: 48px;
  height: 26px;
  border-radius: 13px;
  background: linear-gradient(135deg, #5e5ce6 0%, #0a84ff 100%);
  transition: background 0.35s ease;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 5px;
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.15);
}
.theme-toggle__track--dark {
  background: linear-gradient(135deg, #1c1c2e 0%, #2c2c3e 100%);
  box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.4);
}

.theme-toggle__thumb {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #ffffff;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.2), 0 0 0 0.5px rgba(0, 0, 0, 0.08);
  transition: transform 0.3s cubic-bezier(0.2, 0.9, 0.4, 1);
}
.theme-toggle__thumb--dark {
  transform: translateX(22px);
  background: #ffd60a;
  box-shadow: 0 1px 6px rgba(255, 214, 10, 0.4), 0 0 0 0.5px rgba(0, 0, 0, 0.12);
}

.theme-toggle__icon {
  position: relative;
  z-index: 1;
  pointer-events: none;
}
.theme-toggle__icon--sun {
  color: #ffd60a;
}
.theme-toggle__icon--moon {
  color: #a1a1a6;
}
</style>
