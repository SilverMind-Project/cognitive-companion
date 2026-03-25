<template>
  <v-app class="companion-app">
    <!-- Header -->
    <v-app-bar flat color="transparent" class="px-4">
      <v-app-bar-title>
        <span class="text-h5 font-weight-bold gradient-text">Cognitive Companion</span>
      </v-app-bar-title>
      <v-spacer />
      <v-btn icon="mdi-cog" variant="text" to="/admin" />
    </v-app-bar>

    <v-main>
      <v-container fluid class="fill-height pa-4">
        <v-row class="fill-height">
          <!-- Audio + Visualizer -->
          <v-col cols="12" md="6">
            <v-card class="glass-card fill-height d-flex flex-column" rounded="xl">
              <v-card-title class="text-center py-6">
                <v-icon :color="statusColor" size="x-large" class="mb-2">
                  {{ statusIcon }}
                </v-icon>
                <div class="text-body-1 text-medium-emphasis">{{ statusText }}</div>
              </v-card-title>

              <v-card-text class="flex-grow-1 d-flex align-center justify-center">
                <AudioVisualizer
                  ref="visualizer"
                  :audio-state="audioState"
                  @audio-data="onAudioData"
                  @state-change="onAudioStateChange"
                />
              </v-card-text>

              <v-card-actions class="justify-center pb-6">
                <v-btn
                  :color="recording ? 'error' : 'primary'"
                  size="x-large"
                  rounded="pill"
                  @click="toggleRecording"
                  :icon="recording ? 'mdi-stop' : 'mdi-microphone'"
                />
              </v-card-actions>
            </v-card>
          </v-col>

          <!-- Transcript + Notifications -->
          <v-col cols="12" md="6">
            <v-card class="glass-card fill-height d-flex flex-column" rounded="xl">
              <v-card-title>
                <v-icon class="mr-2">mdi-message-text</v-icon>
                Conversation
              </v-card-title>

              <v-card-text class="flex-grow-1 overflow-y-auto" ref="transcriptPanel">
                <div v-for="(msg, i) in transcript" :key="i" class="mb-3">
                  <v-chip
                    :color="msg.source === 'user' ? 'primary' : 'secondary'"
                    variant="tonal"
                    size="small"
                    class="mb-1"
                  >
                    {{ msg.source === 'user' ? 'You' : 'Assistant' }}
                  </v-chip>
                  <div class="text-body-2 pl-2">{{ msg.text }}</div>
                </div>

                <div v-if="transcript.length === 0" class="text-center text-medium-emphasis py-8">
                  <v-icon size="64" color="grey-darken-1">mdi-microphone-off</v-icon>
                  <div class="mt-4">Tap the microphone to start talking</div>
                </div>
              </v-card-text>
            </v-card>
          </v-col>
        </v-row>
      </v-container>
    </v-main>

    <!-- Emergency Alert Dialog -->
    <v-dialog v-model="alertDialog" max-width="500" persistent>
      <v-card color="error" rounded="xl">
        <v-card-title class="text-h5">
          <v-icon class="mr-2">mdi-alert</v-icon>
          Emergency Alert
        </v-card-title>
        <v-card-text class="text-h6">{{ alertMessage }}</v-card-text>
        <v-card-actions>
          <v-btn variant="outlined" @click="dismissAlert">Dismiss</v-btn>
          <v-spacer />
          <v-btn variant="elevated" color="white" @click="requestAssistance">
            Need Assistance
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-app>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick, watch } from "vue";
import { wsClient } from "../services/WebSocketClient.js";
import AudioVisualizer from "../components/AudioVisualizer.vue";

const recording = ref(false);
const audioState = ref("idle");
const transcript = ref([]);
const transcriptPanel = ref(null);

// Alert state
const alertDialog = ref(false);
const alertMessage = ref("");
const alertId = ref(null);

const statusMap = {
  idle: { icon: "mdi-sleep", color: "grey", text: "Ready" },
  listening: { icon: "mdi-ear-hearing", color: "primary", text: "Listening..." },
  speaking: { icon: "mdi-account-voice", color: "accent", text: "You're speaking..." },
  system_speaking: { icon: "mdi-robot", color: "secondary", text: "Assistant speaking..." },
};
const statusIcon = ref("mdi-sleep");
const statusColor = ref("grey");
const statusText = ref("Ready");

watch(audioState, (state) => {
  const s = statusMap[state] || statusMap.idle;
  statusIcon.value = s.icon;
  statusColor.value = s.color;
  statusText.value = s.text;
});

function toggleRecording() {
  recording.value = !recording.value;
  if (recording.value) {
    wsClient.connect();
  }
}

function onAudioData(buffer) {
  if (recording.value) {
    wsClient.sendAudio(buffer);
  }
}

function onAudioStateChange(state) {
  audioState.value = state;
}

function scrollToBottom() {
  nextTick(() => {
    const el = transcriptPanel.value?.$el;
    if (el) el.scrollTop = el.scrollHeight;
  });
}

function dismissAlert() {
  alertDialog.value = false;
}

function requestAssistance() {
  alertDialog.value = false;
  // TODO: call alert action API
}

onMounted(() => {
  wsClient.on("onTranscript", (data) => {
    transcript.value.push({ source: data.source, text: data.text });
    scrollToBottom();
  });

  wsClient.on("onCommand", (data) => {
    if (data.type === "emergency_alert") {
      alertMessage.value = data.message;
      alertId.value = data.alert_id;
      alertDialog.value = true;
    }
  });

  wsClient.on("onAudioBlob", (buffer) => {
    // Play audio through AudioContext
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    audioCtx.decodeAudioData(buffer.slice(0), (decoded) => {
      const source = audioCtx.createBufferSource();
      source.buffer = decoded;
      source.connect(audioCtx.destination);
      source.start(0);
      audioState.value = "system_speaking";
      source.onended = () => { audioState.value = "listening"; };
    }).catch(() => {});
  });
});

onUnmounted(() => {
  wsClient.disconnect();
});
</script>

<style scoped>
.companion-app {
  background: linear-gradient(135deg, #0f0e16 0%, #1a1333 50%, #0f0e16 100%);
}

.gradient-text {
  background: linear-gradient(135deg, #6366f1, #8b5cf6, #f59e0b);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.glass-card {
  background: rgba(30, 27, 46, 0.6) !important;
  backdrop-filter: blur(20px);
  border: 1px solid rgba(99, 102, 241, 0.15);
}
</style>
