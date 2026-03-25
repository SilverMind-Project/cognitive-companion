<template>
  <v-app>
    <router-view />
  </v-app>
</template>

<script setup>
// Service worker registration
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
</script>
