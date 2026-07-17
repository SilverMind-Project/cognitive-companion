<template>
  <v-app>
    <router-view />
    <CcSnackbarHost />
  </v-app>
</template>

<script setup>
import CcSnackbarHost from "@/components/CcSnackbarHost.vue";

// Service worker registration
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
</script>
