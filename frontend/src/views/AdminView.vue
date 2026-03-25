<template>
  <v-app>
    <v-navigation-drawer permanent rail expand-on-hover>
      <v-list density="compact" nav>
        <v-list-item prepend-icon="mdi-home" title="Companion" to="/" />
        <v-divider class="my-2" />
        <v-list-item prepend-icon="mdi-view-dashboard" title="Dashboard" to="/admin/dashboard" />
        <v-list-item prepend-icon="mdi-shield-check" title="Rules" to="/admin/rules" />
        <v-list-item prepend-icon="mdi-access-point" title="Sensors" to="/admin/sensors" />
        <v-list-item prepend-icon="mdi-floor-plan" title="Rooms" to="/admin/rooms" />
        <v-list-item prepend-icon="mdi-calendar-text" title="Events" to="/admin/events" />
        <v-list-item prepend-icon="mdi-alert-circle" title="Alerts" to="/admin/alerts" />
        <v-list-item prepend-icon="mdi-account-group" title="Persons" to="/admin/persons" />
        <v-list-item prepend-icon="mdi-run" title="Activities" to="/admin/activities" />
        <v-list-item prepend-icon="mdi-sitemap" title="Workflows" to="/admin/workflows" />
        <v-list-item prepend-icon="mdi-image-edit" title="E-Ink Templates" to="/admin/eink-templates" />
      </v-list>
    </v-navigation-drawer>

    <v-app-bar flat color="surface" elevation="1">
      <v-app-bar-title>
        <span class="text-h6 font-weight-bold">Admin Console</span>
      </v-app-bar-title>
      <v-spacer />
      <v-btn icon="mdi-refresh" variant="text" @click="reloadConfig" />
      <v-btn size="small" variant="tonal" class="mx-2" @click="showKeyDialog = true">
        <v-icon start>mdi-key</v-icon>
        API Key
      </v-btn>
    </v-app-bar>

    <v-main>
      <v-container fluid>
        <router-view />
      </v-container>
    </v-main>

    <!-- API Key dialog -->
    <v-dialog v-model="showKeyDialog" max-width="400">
      <v-card rounded="xl">
        <v-card-title>Set API Key</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="apiKeyInput"
            label="API Key"
            type="password"
            variant="outlined"
            hide-details
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="saveApiKey" color="primary">Save</v-btn>
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
