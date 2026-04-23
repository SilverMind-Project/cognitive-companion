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
        <v-list-item prepend-icon="mdi-home-variant-outline" title="Companion" to="/" />
        <v-divider class="my-2 mx-3" />
        <v-list-item prepend-icon="mdi-view-dashboard-outline" title="Dashboard" to="/admin/dashboard" />

        <v-list-subheader class="mt-2">Automation</v-list-subheader>
        <v-list-item prepend-icon="mdi-shield-check-outline" title="Rules" to="/admin/rules" />
        <v-list-item prepend-icon="mdi-sitemap-outline" title="Workflows" to="/admin/workflows" />
        <v-list-item prepend-icon="mdi-calendar-text-outline" title="Events" to="/admin/events" />

        <v-list-subheader class="mt-2">Infrastructure</v-list-subheader>
        <v-list-item prepend-icon="mdi-access-point" title="Sensors" to="/admin/sensors" />
        <v-list-item prepend-icon="mdi-floor-plan" title="Rooms" to="/admin/rooms" />
        <v-list-item prepend-icon="mdi-camera-burst" title="Camera Media" to="/admin/camera-media" />
        <v-list-item prepend-icon="mdi-image-edit-outline" title="E-Ink Templates" to="/admin/eink-templates" />

        <v-list-subheader class="mt-2">Tracking (CTS)</v-list-subheader>
        <v-list-item prepend-icon="mdi-cctv" title="Cameras" to="/admin/cts/cameras" />
        <v-list-item prepend-icon="mdi-crosshairs-gps" title="Calibration" to="/admin/cts/calibration" />
        <v-list-item prepend-icon="mdi-eye-off-outline" title="Privacy Zones" to="/admin/cts/privacy" />
        <v-list-item prepend-icon="mdi-graph-outline" title="Camera Adjacency" to="/admin/cts/adjacency" />

        <v-list-subheader class="mt-2">People</v-list-subheader>
        <v-list-item prepend-icon="mdi-account-group-outline" title="Members &amp; Enrollment" to="/admin/persons" />
        <v-list-item prepend-icon="mdi-run" title="Activities" to="/admin/activities" />
        <v-list-item prepend-icon="mdi-timeline-text-outline" title="Timeline" to="/admin/timeline" />
        <v-list-item prepend-icon="mdi-chart-box" title="Daily Reports" to="/admin/reports" />
        <v-list-item prepend-icon="mdi-alert-circle-outline" title="Alerts" to="/admin/alerts" />
      </v-list>
    </v-navigation-drawer>

    <v-app-bar flat>
      <v-app-bar-title>
        <span class="text-h6 font-weight-bold">Caregiver Console</span>
      </v-app-bar-title>
      <v-spacer />
      <v-btn icon="mdi-refresh" variant="text" title="Reload config" @click="reloadConfig" />
      <v-btn size="small" variant="tonal" class="mx-2" @click="showKeyDialog = true">
        <v-icon start>mdi-key-variant</v-icon>
        API Key
      </v-btn>
    </v-app-bar>

    <v-main>
      <v-container fluid class="px-6 py-6">
        <router-view />
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
import { ref, onMounted } from "vue";
import { api } from "../services/api.js";

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
</style>
