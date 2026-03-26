<template>
  <v-app class="companion-app">
    <!-- Header -->
    <v-app-bar flat color="transparent" class="px-4">
      <v-app-bar-title>
        <span class="text-h5 font-weight-bold gradient-text">Cognitive Companion</span>
      </v-app-bar-title>
      <v-spacer />
      <v-chip
        :color="connected ? 'success' : 'grey'"
        size="small"
        variant="tonal"
        class="mr-2"
      >
        <v-icon start size="12">{{ connected ? 'mdi-wifi' : 'mdi-wifi-off' }}</v-icon>
        {{ connected ? 'Connected' : 'Disconnected' }}
      </v-chip>
      <v-btn icon="mdi-cog" variant="text" to="/admin" />
    </v-app-bar>

    <v-main>
      <v-container fluid class="fill-height pa-4">
        <v-row class="fill-height">
          <!-- Main widgets (left/center column) -->
          <v-col cols="12" md="6">
            <component
              v-for="w in mainWidgets"
              :key="w.id"
              :is="w.component"
              v-bind="getWidgetProps(w.id)"
              v-on="getWidgetEvents(w.id)"
            />
          </v-col>

          <!-- Sidebar widgets (right column) -->
          <v-col cols="12" md="6">
            <component
              v-for="w in sidebarWidgets"
              :key="w.id"
              :is="w.component"
              v-bind="getWidgetProps(w.id)"
              v-on="getWidgetEvents(w.id)"
            />
          </v-col>
        </v-row>
      </v-container>
    </v-main>

    <!-- Overlay widgets (dialogs, alerts) -->
    <component
      v-for="w in overlayWidgets"
      :key="w.id"
      :is="w.component"
      v-bind="getWidgetProps(w.id)"
      v-on="getWidgetEvents(w.id)"
    />
  </v-app>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from "vue";
import { wsClient } from "../services/WebSocketClient.js";
import { getWidgets } from "../components/companion/WidgetRegistry.js";

// Register built-in widgets
import "../components/companion/index.js";

// Reactive state shared across widgets
const recording = ref(false);
const audioState = ref("idle");
const transcript = ref([]);
const alertDialog = ref(false);
const alertMessage = ref("");
const connected = ref(false);

// Widget lists by position
const mainWidgets = computed(() => getWidgets("main"));
const sidebarWidgets = computed(() => getWidgets("sidebar"));
const overlayWidgets = computed(() => getWidgets("overlay"));

// Provide props to widgets based on their ID
function getWidgetProps(widgetId) {
  switch (widgetId) {
    case "voice":
      return { recording: recording.value, audioState: audioState.value };
    case "transcript":
      return { transcript: transcript.value };
    case "alert":
      return { visible: alertDialog.value, message: alertMessage.value };
    default:
      return {};
  }
}

// Provide event handlers to widgets based on their ID
function getWidgetEvents(widgetId) {
  switch (widgetId) {
    case "voice":
      return {
        "toggle-recording": toggleRecording,
        "audio-data": onAudioData,
        "state-change": onAudioStateChange,
      };
    case "transcript":
      return {
        clear: clearTranscript,
      };
    case "alert":
      return {
        dismiss: dismissAlert,
        "request-assistance": requestAssistance,
      };
    default:
      return {};
  }
}

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

function clearTranscript() {
  transcript.value = [];
}

function dismissAlert() {
  alertDialog.value = false;
}

function requestAssistance() {
  alertDialog.value = false;
}

onMounted(() => {
  wsClient.on("onTranscript", (data) => {
    transcript.value.push({
      source: data.source,
      text: data.text,
      timestamp: new Date().toISOString(),
    });
  });

  wsClient.on("onCommand", (data) => {
    if (data.type === "emergency_alert") {
      alertMessage.value = data.message;
      alertDialog.value = true;
    }
  });

  wsClient.on("onAudioBlob", (buffer) => {
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

  wsClient.on("onOpen", () => { connected.value = true; });
  wsClient.on("onClose", () => { connected.value = false; });
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
