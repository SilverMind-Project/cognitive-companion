<template>
  <v-app ref="appRoot" class="companion-app">
    <!-- Header -->
    <v-app-bar flat color="transparent" class="px-4">
      <v-app-bar-title>
        <span class="text-h5 font-weight-bold cc-gradient-text">Cognitive Companion</span>
      </v-app-bar-title>
      <v-spacer />
      <!-- She can always see when the screen is listening or watching, and is never
           told it is listening when the microphone could not be opened. -->
      <v-chip
        v-if="recording && micCapture.live"
        color="primary"
        size="small"
        variant="tonal"
        class="mr-2"
        data-test="capture-mic"
      >
        <v-icon start size="12">mdi-microphone</v-icon>
        Listening
      </v-chip>
      <v-chip
        v-else-if="recording && micCapture.error"
        color="warning"
        size="small"
        variant="tonal"
        class="mr-2"
        data-test="capture-mic-unavailable"
      >
        <v-icon start size="12">mdi-microphone-off</v-icon>
        Microphone unavailable
      </v-chip>
      <v-chip
        v-if="hardware.state.cameraActive"
        color="primary"
        size="small"
        variant="tonal"
        class="mr-2"
        data-test="capture-camera"
      >
        <v-icon start size="12">mdi-camera</v-icon>
        Camera active
      </v-chip>
      <v-chip
        :color="connected ? 'success' : undefined"
        size="small"
        variant="tonal"
        class="mr-2"
        data-test="connection-status"
        :data-connected="connected ? 'true' : 'false'"
      >
        <v-icon start size="12">{{ connected ? "mdi-wifi" : "mdi-wifi-off" }}</v-icon>
        {{ connected ? "Connected" : "Disconnected" }}
      </v-chip>
      <v-btn icon="mdi-cog" variant="text" to="/admin" />
    </v-app-bar>

    <v-main>
      <v-container fluid class="fill-height pa-4">
        <v-row class="fill-height">
          <!-- Main widgets (left/center column) -->
          <v-col cols="12" md="6">
            <component
              :is="w.component"
              v-for="w in mainWidgets"
              :key="w.id"
              v-bind="getWidgetProps(w.id)"
              v-on="getWidgetEvents(w.id)"
            />
          </v-col>

          <!-- Sidebar widgets (right column) -->
          <v-col cols="12" md="6">
            <component
              :is="w.component"
              v-for="w in sidebarWidgets"
              :key="w.id"
              v-bind="getWidgetProps(w.id)"
              v-on="getWidgetEvents(w.id)"
            />
          </v-col>
        </v-row>
      </v-container>
    </v-main>

    <!-- Overlay widgets (dialogs, alerts) -->
    <component
      :is="w.component"
      v-for="w in overlayWidgets"
      :key="w.id"
      v-bind="getWidgetProps(w.id)"
      v-on="getWidgetEvents(w.id)"
    />

    <KioskGate
      :state="kiosk.state"
      @begin="beginKioskSession"
      @unlock-settings="kiosk.actions.unlockSettings"
      @save-settings="kiosk.actions.saveSettings"
      @load-rooms="kiosk.actions.loadRooms"
      @test-surface="kiosk.actions.testSurface"
    />
  </v-app>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from "vue";
import { useRoute } from "vue-router";
import { wsClient } from "../services/WebSocketClient.js";
import { getWidgets } from "../components/companion/WidgetRegistry.js";
import KioskGate from "../components/companion/KioskGate.vue";
import { useKioskMode } from "../composables/useKioskMode.js";
import { useNativeCompanionHardware } from "../composables/useNativeCompanionHardware.js";
import { useResidentGuidedSession } from "../composables/useResidentGuidedSession.js";
import { useTvNavigation } from "../composables/useTvNavigation.js";
import { api } from "../services/api.js";
import "../styles/companion-tv.css";

// Register built-in widgets
import "../components/companion/index.js";

// Reactive state shared across widgets
const recording = ref(false);
// Whether the microphone is really open (from the voice widget), as opposed to
// `recording`, the wish to listen.
const micCapture = ref({ live: false, error: null });
const audioState = ref("idle");
const transcript = ref([]);
const alertDialog = ref(false);
const alertMessage = ref("");
const alertType = ref("info");
const connected = ref(false);
const appRoot = ref(null);
const route = useRoute();
const hardware = useNativeCompanionHardware({
  ws: wsClient,
  isRecording: () => recording.value,
  isCapturing: () => micCapture.value.live,
  startCapture: () => startRecordingFromGesture(),
  stopCapture: stopRecording,
});
const kiosk = useKioskMode({ route, deviceState: () => hardware.actions.deviceState() });
const guided = useResidentGuidedSession({
  ws: wsClient,
  // This screen sees the routine the server is sending to its own surface.
  api: {
    getResidentGuidedState: () =>
      api.getResidentGuidedState(kiosk.state.settings.surfaceId || undefined),
  },
});
const tv = useTvNavigation({
  route,
  deviceIsTelevision: () => hardware.state.isTelevision,
  root: () => appRoot.value?.$el ?? null,
});

// Interactive prompt state
const interactivePromptVisible = ref(false);
const interactivePromptData = ref({
  execution_id: null,
  step_id: null,
  message: "",
  title: "Question for You",
  icon: "mdi-message-question",
  escalate_button_text: "I need help",
  dismiss_button_text: "I'm okay",
  countdown_seconds: 30,
  server_timestamp: new Date().toISOString(),
});

// Knowledge answer state
const knowledgeAnswerData = ref({
  queryText: "",
  answerText: "",
  sourceDocumentIds: [],
  // Per-answer marker so the widget reopens even when the same question is
  // asked again (identical queryText would otherwise not retrigger its watch).
  serverTimestamp: "",
});

let playbackContext = null;
let nextPlaybackTime = 0;
let activePlaybackSources = 0;

// Announcement buffer: accumulates all PCM chunks until stream_end,
// then plays the complete audio at once.  Current hardware cannot sustain
// real-time TTS inference, so partial playback causes audible gaps.
// TODO: reduce buffer (play incrementally) once faster inference hardware is available.
let announcementBuffer = [];
let announcementBufferBytes = 0;
let announcementSampleRate = 24000;

// Widget lists by position
const mainWidgets = computed(() => getWidgets("main"));
const sidebarWidgets = computed(() => getWidgets("sidebar"));
const overlayWidgets = computed(() => getWidgets("overlay"));

function normalizeAlertType(type) {
  if (type === "emergency_alert") return "emergency";
  if (type === "warning" || type === "reminder" || type === "emergency") {
    return type;
  }
  return "info";
}

// Provide props to widgets based on their ID
function getWidgetProps(widgetId) {
  switch (widgetId) {
    case "guided-task":
      return {
        session: guided.state.session,
        pendingAction: guided.state.pendingAction,
        celebrating: guided.state.celebrating,
      };
    case "voice":
      return { recording: recording.value, audioState: audioState.value };
    case "transcript":
      return { transcript: transcript.value };
    case "alert":
      return {
        visible: alertDialog.value,
        message: alertMessage.value,
        alertType: alertType.value,
      };
    case "interactive-prompt":
      return {
        visible: interactivePromptVisible.value,
        message: interactivePromptData.value.message,
        title: interactivePromptData.value.title,
        icon: interactivePromptData.value.icon,
        escalateButtonText: interactivePromptData.value.escalate_button_text,
        dismissButtonText: interactivePromptData.value.dismiss_button_text,
        countdownSeconds: interactivePromptData.value.countdown_seconds,
        serverTimestamp: interactivePromptData.value.server_timestamp,
      };
    case "knowledge-answer":
      return {
        queryText: knowledgeAnswerData.value.queryText,
        answerText: knowledgeAnswerData.value.answerText,
        sourceDocumentIds: knowledgeAnswerData.value.sourceDocumentIds,
        serverTimestamp: knowledgeAnswerData.value.serverTimestamp,
      };
    default:
      return {};
  }
}

// Provide event handlers to widgets based on their ID
function getWidgetEvents(widgetId) {
  switch (widgetId) {
    case "guided-task":
      return { action: guided.actions.submit };
    case "voice":
      return {
        "toggle-recording": toggleRecording,
        "audio-data": onAudioData,
        "state-change": onAudioStateChange,
        "capture-change": (capture) => {
          micCapture.value = capture;
        },
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
    case "interactive-prompt":
      return {
        response: onInteractiveResponse,
        timeout: onInteractiveTimeout,
      };
    default:
      return {};
  }
}

async function startRecordingFromGesture() {
  // Initialize AudioContext during the user gesture so it starts in running
  // state. Creating it lazily inside a WebSocket callback would leave it
  // suspended and audio would never play.
  const ctx = getPlaybackContext();
  if (ctx.state === "suspended") {
    await ctx.resume();
  }
  wsClient.connect();
  recording.value = true;
  audioState.value = "listening";
}

function stopRecording() {
  recording.value = false;
  audioState.value = "idle";
}

function toggleRecording() {
  if (recording.value) {
    stopRecording();
    return;
  }
  void startRecordingFromGesture();
}

function beginKioskSession() {
  void kiosk.actions.begin(startRecordingFromGesture);
}

/**
 * The Android shell plays audio without a tap, so its kiosk starts by itself
 * after a reboot or crash, idle until the server asks it to listen, instead of
 * waiting behind a tap screen she cannot be expected to use.
 */
async function beginNativeKiosk() {
  await kiosk.actions.begin(async () => {
    const ctx = getPlaybackContext();
    if (ctx.state === "suspended") await ctx.resume();
  });
}

function applySurfaceContext() {
  wsClient.setSurfaceContext({
    surfaceId: kiosk.state.settings.surfaceId,
    platform: hardware.state.platform,
  });
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

function onInteractiveResponse(action) {
  if (!interactivePromptData.value.execution_id || !interactivePromptData.value.step_id) {
    console.error("Cannot send interactive response: missing execution_id or step_id");
    return;
  }

  wsClient.sendInteractiveResponse(
    interactivePromptData.value.execution_id,
    interactivePromptData.value.step_id,
    action,
  );

  interactivePromptVisible.value = false;
}

function onInteractiveTimeout() {
  // Timeout is handled by backend, just close the dialog
  interactivePromptVisible.value = false;
}

function getPlaybackContext() {
  if (!playbackContext) {
    playbackContext = new (window.AudioContext || window.webkitAudioContext)();
  }
  return playbackContext;
}

function pcm16ToFloat32(buffer) {
  const input = new Int16Array(buffer);
  const output = new Float32Array(input.length);
  for (let i = 0; i < input.length; i++) {
    output[i] = input[i] / 0x8000;
  }
  return output;
}

function playAudioUrl(url) {
  const audio = new Audio(url);
  audioState.value = "system_speaking";
  audio.onended = () => {
    audioState.value = recording.value ? "listening" : "idle";
  };
  audio.onerror = () => {
    audioState.value = recording.value ? "listening" : "idle";
  };
  audio.play().catch((err) => console.error("Audio playback error:", err));
}

function playPcmChunk(buffer, sampleRate = 24000) {
  const audioCtx = getPlaybackContext();
  const samples = pcm16ToFloat32(buffer);
  if (!samples.length) return;

  if (audioCtx.state === "suspended") {
    void audioCtx.resume();
  }

  const audioBuffer = audioCtx.createBuffer(1, samples.length, sampleRate);
  audioBuffer.getChannelData(0).set(samples);

  const source = audioCtx.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(audioCtx.destination);

  const startAt = Math.max(audioCtx.currentTime, nextPlaybackTime);
  nextPlaybackTime = startAt + audioBuffer.duration;
  activePlaybackSources += 1;
  audioState.value = "system_speaking";

  source.onended = () => {
    activePlaybackSources = Math.max(0, activePlaybackSources - 1);
    if (activePlaybackSources === 0) {
      // Return to listening only when the user has the mic active;
      // otherwise fall back to idle so the status pill resets correctly.
      audioState.value = recording.value ? "listening" : "idle";
      nextPlaybackTime = Math.max(nextPlaybackTime, audioCtx.currentTime);
    }
  };

  source.start(startAt);
}

function flushAnnouncementBuffer() {
  if (!announcementBuffer.length) return;

  // Merge buffered chunks into a single ArrayBuffer for one decode pass
  const merged = new Uint8Array(announcementBufferBytes);
  let offset = 0;
  for (const chunk of announcementBuffer) {
    merged.set(new Uint8Array(chunk), offset);
    offset += chunk.byteLength;
  }
  announcementBuffer = [];
  announcementBufferBytes = 0;

  playPcmChunk(merged.buffer, announcementSampleRate);
}

watch(
  () => kiosk.state.settings.surfaceId,
  () => {
    applySurfaceContext();
    void guided.actions.hydrate();
  },
);
watch(
  () => tv.state.active,
  () => tv.actions.syncClass(),
);

onMounted(async () => {
  // The shell is detected first so the socket names its platform from the start.
  await hardware.actions.mount();
  tv.actions.mount();
  // Connect immediately so push notifications (alerts, reminders) are
  // delivered as soon as the page loads, regardless of whether the user
  // has tapped the mic button.  The backend holds the connection open
  // without starting a Gemini session until audio activity arrives.
  applySurfaceContext();
  wsClient.connect();
  guided.actions.mount();
  if (hardware.state.native && kiosk.state.gateVisible) {
    await beginNativeKiosk();
  }

  wsClient.on("onTranscript", (data) => {
    transcript.value.push({
      source: data.source,
      text: data.text,
      timestamp: new Date().toISOString(),
    });
  });

  wsClient.on("onCommand", (data) => {
    alertMessage.value = data.message || "";
    alertType.value = normalizeAlertType(data.type);
    alertDialog.value = true;
  });

  wsClient.on("onAudioBlob", (buffer) => {
    playPcmChunk(buffer);
  });

  wsClient.on("onAnnouncement", (data) => {
    if (data.subtype === "stream_start") {
      // Reset playback timeline so this announcement starts cleanly
      const ctx = getPlaybackContext();
      nextPlaybackTime = ctx.currentTime;
      activePlaybackSources = 0;
      announcementBuffer = [];
      announcementBufferBytes = 0;
      announcementSampleRate = data.sampleRate || 24000;
    } else if (data.subtype === "pcm_chunk" && data.data) {
      // Accumulate all chunks; playback starts on stream_end
      announcementBuffer.push(data.data);
      announcementBufferBytes += data.data.byteLength;
    } else if (data.subtype === "stream_end") {
      // Play the complete announcement as one contiguous buffer
      flushAnnouncementBuffer();
    } else if (data.subtype === "audio_url" && data.url) {
      playAudioUrl(data.url);
    }
  });

  wsClient.on("onConnect", () => {
    connected.value = true;
    kiosk.actions.onSocketConnect();
  });
  wsClient.on("onDisconnect", () => {
    connected.value = false;
    kiosk.actions.onSocketDisconnect();
  });

  wsClient.on("onInteractivePrompt", (data) => {
    interactivePromptData.value = {
      execution_id: data.execution_id,
      step_id: data.step_id,
      message: data.message || "",
      title: data.title || "Question for You",
      icon: data.icon || "mdi-message-question",
      escalate_button_text: data.escalate_button_text || "I need help",
      dismiss_button_text: data.dismiss_button_text || "I'm okay",
      countdown_seconds: data.countdown_seconds || 30,
      server_timestamp: data.server_timestamp || new Date().toISOString(),
    };
    interactivePromptVisible.value = true;
  });

  wsClient.on("onEnableMicrophone", () => {
    // Auto-enable mic so the user can respond to a voice prompt from
    // Gemini Live without manually tapping the microphone button.
    if (!recording.value) {
      void kiosk.actions.handleEnableMicrophone(startRecordingFromGesture);
    }
  });

  wsClient.on("onInteractiveResponse", (_data) => {
    // Close any open interactive prompt when response is received from another channel
    if (interactivePromptVisible.value) {
      interactivePromptVisible.value = false;
    }
  });

  wsClient.on("onKnowledgeAnswer", (data) => {
    knowledgeAnswerData.value = {
      queryText: data.query_text || "",
      answerText: data.answer_text || "",
      sourceDocumentIds: data.source_document_ids || [],
      serverTimestamp: data.server_timestamp || new Date().toISOString(),
    };
  });
});

onUnmounted(() => {
  hardware.actions.unmount();
  tv.actions.unmount();
  guided.actions.unmount();
  wsClient.disconnect();
  if (playbackContext) {
    void playbackContext.close();
    playbackContext = null;
  }
});
</script>

<style scoped>
/*
 * Senior companion surface — warm DS paper. The global ccWarm theme applies
 * here too (it is the default Vuetify theme), so widgets inherit the warm
 * tokens. We only need the page background; the global warm.glass-card rule
 * styles the cards (no scoped dark override).
 */
.companion-app {
  background: var(--cc-bg);
}
</style>
