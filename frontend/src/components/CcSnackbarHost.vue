<template>
  <v-snackbar
    v-for="(item, index) in queue"
    :key="item.id"
    :model-value="true"
    :color="item.color"
    :timeout="item.timeout"
    location="bottom"
    :style="{ 'margin-bottom': `${index * 60}px` }"
    @update:model-value="dismiss(item.id)"
  >
    {{ item.text }}
  </v-snackbar>
</template>

<script setup lang="ts">
/**
 * The app's one notification renderer (M18). Mounted once, in App.vue.
 *
 * Messages stack upward so a burst stays readable rather than overwriting itself, which is what
 * the old per-view single-ref snackbar did. Vuetify clears `model-value` when a timeout expires
 * or the user dismisses; that event is what removes the entry from the queue, so the store never
 * needs its own timers.
 */

import { storeToRefs } from "pinia";

import { useNotificationsStore } from "@/stores/notifications";

const store = useNotificationsStore();
const { queue } = storeToRefs(store);
const { dismiss } = store;
</script>
