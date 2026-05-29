<template>
  <div>
    <!-- Sub-tabs: Live video and Floor Plan -->
    <v-tabs v-model="subTab" color="primary" density="compact" class="mb-4">
      <v-tab value="live" prepend-icon="mdi-video-outline">Live</v-tab>
      <v-tab value="floor" prepend-icon="mdi-floor-plan">Floor Plan</v-tab>
    </v-tabs>

    <v-window v-model="subTab">
      <v-window-item value="live">
        <CTSLiveView />
      </v-window-item>

      <v-window-item value="floor">
        <CTSFloorPlanView />
      </v-window-item>
    </v-window>
  </div>
</template>

<script setup>
import { ref } from "vue";
import CTSLiveView from "@/views/admin/CTSLiveView.vue";
import CTSFloorPlanView from "@/views/admin/CTSFloorPlanView.vue";

const subTab = ref("live");

defineExpose({ subTab });
</script>
