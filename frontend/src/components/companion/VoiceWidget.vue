<template>
  <v-card class="glass-card fill-height d-flex flex-column" rounded="xl">
    <v-card-title class="text-center pt-6 pb-2">
      <div :class="['status-indicator', `status-${audioState}`]">
        <v-icon :color="statusColor" size="32">
          {{ statusIcon }}
        </v-icon>
      </div>
      <div class="text-body-1 mt-2" :style="{ color: `rgb(var(--v-theme-${statusColor}))` }">
        {{ statusText }}
      </div>
    </v-card-title>

    <v-card-text class="flex-grow-1 d-flex align-center justify-center">
      <AudioVisualizer
        ref="visualizer"
        :audio-state="audioState"
        @audio-data="$emit('audio-data', $event)"
        @state-change="$emit('state-change', $event)"
      />
    </v-card-text>

    <v-card-actions class="justify-center pb-6">
      <v-btn
        :class="['mic-btn', recording ? 'mic-btn-active' : '']"
        :color="recording ? 'error' : 'primary'"
        size="x-large"
        rounded="pill"
        @click="$emit('toggle-recording')"
        :icon="recording ? 'mdi-stop' : 'mdi-microphone'"
        elevation="8"
      />
    </v-card-actions>
  </v-card>
</template>

<script setup>
import { computed } from "vue";
import AudioVisualizer from "../AudioVisualizer.vue";

const props = defineProps({
  recording: { type: Boolean, default: false },
  audioState: { type: String, default: "idle" },
});

defineEmits(["audio-data", "state-change", "toggle-recording"]);

const statusMap = {
  idle: { icon: "mdi-sleep", color: "grey", text: "Tap to start" },
  listening: { icon: "mdi-ear-hearing", color: "primary", text: "Listening..." },
  speaking: { icon: "mdi-account-voice", color: "accent", text: "You're speaking..." },
  system_speaking: { icon: "mdi-robot-happy", color: "secondary", text: "Assistant is responding..." },
};

const statusIcon = computed(() => (statusMap[props.audioState] || statusMap.idle).icon);
const statusColor = computed(() => (statusMap[props.audioState] || statusMap.idle).color);
const statusText = computed(() => (statusMap[props.audioState] || statusMap.idle).text);
</script>

<style scoped>
.status-indicator {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 64px;
  border-radius: 50%;
  margin: 0 auto;
  transition: all 0.3s ease;
}

.status-idle {
  background: rgba(158, 158, 158, 0.1);
}

.status-listening {
  background: rgba(99, 102, 241, 0.15);
  animation: pulse 2s ease-in-out infinite;
}

.status-speaking {
  background: rgba(139, 92, 246, 0.15);
  animation: pulse 1.5s ease-in-out infinite;
}

.status-system_speaking {
  background: rgba(245, 158, 11, 0.15);
  animation: glow 1.5s ease-in-out infinite;
}

.mic-btn {
  transition: all 0.3s ease;
}

.mic-btn-active {
  animation: pulse-btn 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.08); opacity: 0.85; }
}

@keyframes glow {
  0%, 100% { box-shadow: 0 0 8px rgba(245, 158, 11, 0.2); }
  50% { box-shadow: 0 0 20px rgba(245, 158, 11, 0.4); }
}

@keyframes pulse-btn {
  0%, 100% { box-shadow: 0 0 0 0 rgba(244, 67, 54, 0.4); }
  50% { box-shadow: 0 0 0 12px rgba(244, 67, 54, 0); }
}
</style>
