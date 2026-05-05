<template>
  <div>
    <div class="d-flex align-center mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Presence Fusion</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Active provider chain that resolves "where is each person?" from CTS, Home Assistant, and anchoring rules.
          Edit <code>config/presence.yaml</code> on the host, then click Reload.
        </div>
      </div>
      <v-spacer />
      <v-btn
        variant="tonal"
        prepend-icon="mdi-refresh"
        :loading="reloading"
        @click="onReload"
        aria-label="Reload presence configuration from disk"
      >
        Reload
      </v-btn>
    </div>

    <v-card class="glass-card">
      <v-progress-linear v-if="loading" indeterminate color="primary" />

      <v-alert v-if="error" type="error" variant="tonal" closable class="ma-4" @click:close="error = null">
        {{ error }}
      </v-alert>

      <template v-if="config">
        <v-card-text class="pa-4">
          <div class="d-flex align-center ga-4 flex-wrap mb-3">
            <v-chip color="primary" variant="tonal" size="small">
              <v-icon start size="14">mdi-file-cog</v-icon>
              {{ config.config_path }}
            </v-chip>
            <v-chip color="surface-variant" variant="outlined" size="small">
              <v-icon start size="14">mdi-clock-outline</v-icon>
              Loaded {{ formatRelative(config.loaded_at) }}
            </v-chip>
            <v-chip color="surface-variant" variant="outlined" size="small">
              <v-icon start size="14">mdi-tune-vertical</v-icon>
              {{ config.fusion.rule }} (floor {{ config.fusion.confidence_floor }})
            </v-chip>
          </div>
        </v-card-text>

        <v-divider />

        <v-list lines="two">
          <v-list-item v-for="(provider, idx) in sortedProviders" :key="provider.name + idx">
            <template #prepend>
              <v-avatar :color="providerColor(provider.name)" size="36">
                <v-icon size="20" color="white">{{ providerIcon(provider.name) }}</v-icon>
              </v-avatar>
            </template>
            <v-list-item-title class="d-flex align-center ga-2">
              <span class="font-weight-medium">{{ provider.name }}</span>
              <v-chip size="x-small" variant="tonal" color="surface-variant">priority {{ provider.priority }}</v-chip>
            </v-list-item-title>
            <v-list-item-subtitle>{{ provider.config_summary }}</v-list-item-subtitle>
          </v-list-item>
        </v-list>
      </template>

      <div v-if="!loading && !config && !error" class="text-center text-medium-emphasis py-8">
        Presence configuration not loaded.
      </div>
    </v-card>

    <v-snackbar v-model="snack" :color="snackColor" timeout="3000">{{ snackText }}</v-snackbar>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { cts } from "../../services/cts.js";
import { useNotify } from "../../composables/useNotify.js";

const { snack, snackText, snackColor, notify } = useNotify();

const loading = ref(false);
const reloading = ref(false);
const error = ref(null);
const config = ref(null);

const PROVIDER_META = {
  cts_location:    { color: "blue",         icon: "mdi-cctv" },
  ha_bed_sensor:   { color: "purple",       icon: "mdi-bed" },
  ha_device_tracker: { color: "teal",        icon: "mdi-cellphone" },
  night_anchor:    { color: "indigo",       icon: "mdi-weather-night" },
  stale_fallback:  { color: "grey-darken-1", icon: "mdi-clock-alert-outline" },
  unknown_sentinel: { color: "grey",        icon: "mdi-help-circle" },
};

function providerColor(name) {
  return PROVIDER_META[name]?.color || "grey";
}
function providerIcon(name) {
  return PROVIDER_META[name]?.icon || "mdi-puzzle";
}

const sortedProviders = computed(() => {
  if (!config.value) return [];
  return [...config.value.providers].sort((a, b) => b.priority - a.priority);
});

function formatRelative(iso) {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const secs = Math.abs(Math.floor(diff / 1000));
  if (secs < 60) return secs < 10 ? "just now" : `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return mins === 1 ? "1 min ago" : `${mins} min ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return hrs === 1 ? "1 hr ago" : `${hrs} hr ago`;
  const days = Math.floor(hrs / 24);
  return days === 1 ? "yesterday" : `${days} days ago`;
}

async function load() {
  loading.value = true;
  try {
    config.value = await cts.getPresenceConfig();
    error.value = null;
  } catch (e) {
    console.error("getPresenceConfig failed", e);
    error.value = e?.message || "Could not load presence configuration.";
  } finally {
    loading.value = false;
  }
}

async function onReload() {
  reloading.value = true;
  try {
    config.value = await cts.reloadPresenceConfig();
    notify("Presence configuration reloaded.");
  } catch (e) {
    console.error("reloadPresenceConfig failed", e);
    const detail = e?.message || "Reload failed.";
    notify(detail, "error");
  } finally {
    reloading.value = false;
  }
}

onMounted(load);
</script>
