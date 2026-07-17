<template>
  <div class="voice-card" :class="`voice-card--${audioState}`">
    <!-- Status pill -->
    <div class="status-pill" :class="`pill--${audioState}`">
      <span class="pill-dot" />
      {{ statusText }}
    </div>

    <!-- Waveform -->
    <div class="waveform-region">
      <AudioVisualizer
        :audio-state="audioState"
        :recording="recording"
        @audio-data="$emit('audio-data', $event)"
        @state-change="$emit('state-change', $event)"
      />
    </div>

    <!-- Mic button -->
    <div class="mic-region">
      <button
        class="mic-btn"
        :class="recording ? 'mic-btn--active' : 'mic-btn--idle'"
        :aria-label="recording ? 'Stop listening' : 'Start talking'"
        @click="$emit('toggle-recording')"
      >
        <v-icon size="40" color="#FBF8F3">
          {{ recording ? "mdi-stop" : "mdi-microphone" }}
        </v-icon>
      </button>
      <p class="mic-hint">{{ recording ? "Tap to stop" : "Tap to talk" }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";
import AudioVisualizer from "../AudioVisualizer.vue";

const props = defineProps({
  recording: { type: Boolean, default: false },
  audioState: { type: String, default: "idle" },
});

defineEmits(["audio-data", "state-change", "toggle-recording"]);

const STATUS_MAP = {
  idle: "Ready",
  listening: "Listening...",
  speaking: "You're speaking",
  system_speaking: "System is responding",
};

const statusText = computed(() => STATUS_MAP[props.audioState] ?? "Ready");
</script>

<style scoped>
/* ── Card shell — warm DS paper ─────────────────────────────────────────── */
.voice-card {
  background: var(--cc-surface);
  border: 1px solid var(--cc-divider);
  border-radius: var(--cc-radius-xl);
  box-shadow: var(--cc-shadow-sm);
  padding: 24px 20px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  transition:
    border-color var(--cc-dur-base) var(--cc-ease-standard),
    box-shadow var(--cc-dur-base) var(--cc-ease-standard);
  width: 100%;
  box-sizing: border-box;
}

.voice-card--listening {
  border-color: var(--good-line);
}
.voice-card--speaking {
  border-color: var(--notice-line);
}
.voice-card--system_speaking {
  border-color: var(--line-brand);
}

/* ── Status pill — DS semantic pairs ────────────────────────────────────── */
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  align-self: flex-start;
  padding: 7px 16px 7px 12px;
  border-radius: var(--cc-radius-pill);
  font-size: 1rem;
  font-weight: 700;
  letter-spacing: -0.005em;
  background: var(--cc-surface-2);
  border: 1px solid var(--cc-divider);
  color: var(--cc-text-2);
  transition:
    background var(--cc-dur-base) var(--cc-ease-standard),
    border-color var(--cc-dur-base) var(--cc-ease-standard),
    color var(--cc-dur-base) var(--cc-ease-standard);
}

.pill-dot {
  width: 10px;
  height: 10px;
  border-radius: var(--cc-radius-pill);
  background: var(--stone-400);
  flex: none;
  box-shadow: 0 0 0 4px var(--cc-surface-2);
}

/* idle → quiet pair (default above); active states map to DS pairs */
.pill--listening {
  background: var(--good-bg);
  border-color: var(--good-line);
  color: var(--good-fg);
}
.pill--speaking {
  background: var(--notice-bg);
  border-color: var(--notice-line);
  color: var(--notice-fg);
}
.pill--system_speaking {
  background: var(--sage-50);
  border-color: var(--sage-200);
  color: var(--sage-600);
}

.pill--listening .pill-dot {
  background: var(--green-care);
  box-shadow: 0 0 0 4px var(--good-bg);
}
.pill--speaking .pill-dot {
  background: var(--gold-notice);
  box-shadow: 0 0 0 4px var(--notice-bg);
}
.pill--system_speaking .pill-dot {
  background: var(--sage-500);
  box-shadow: 0 0 0 4px var(--sage-50);
}

.pill--listening .pill-dot,
.pill--speaking .pill-dot,
.pill--system_speaking .pill-dot {
  animation: cc-pill-blink 1.6s var(--cc-ease-standard) infinite;
}

/* ── Waveform ───────────────────────────────────────────────────────────── */
.waveform-region {
  width: 100%;
}

/* ── Mic button — sage idle, brick recording, calm breathing ring ───────── */
.mic-region {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding-top: 4px;
}

.mic-btn {
  width: 96px;
  height: 96px;
  border-radius: var(--cc-radius-pill);
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition:
    background var(--cc-dur-base) var(--cc-ease-standard),
    transform var(--cc-dur-base) var(--cc-ease-standard),
    box-shadow var(--cc-dur-base) var(--cc-ease-standard);
  outline: none;
  position: relative;
}

.mic-btn--idle {
  background: var(--cc-brand);
  box-shadow: var(--cc-shadow-md);
}

.mic-btn--idle:hover {
  transform: scale(1.04);
  box-shadow: var(--cc-shadow-lg);
}

.mic-btn--active {
  background: var(--cc-error);
  box-shadow:
    0 0 0 8px var(--alert-bg),
    var(--cc-shadow-md);
  animation: cc-mic-breathe 2.4s var(--cc-ease-standard) infinite;
}

.mic-hint {
  font-size: 19px;
  font-weight: 500;
  color: var(--cc-text-2);
  margin: 0;
}

/* ── Keyframes ──────────────────────────────────────────────────────────── */
@keyframes cc-pill-blink {
  0%,
  100% {
    opacity: 0.85;
  }
  50% {
    opacity: 1;
  }
}

/* Calm breathing ring, 8 → 14px. No fast flashing. */
@keyframes cc-mic-breathe {
  0%,
  100% {
    box-shadow:
      0 0 0 8px var(--alert-bg),
      var(--cc-shadow-md);
  }
  50% {
    box-shadow:
      0 0 0 14px var(--alert-bg),
      var(--cc-shadow-md);
  }
}

@media (prefers-reduced-motion: reduce) {
  .mic-btn--active {
    animation: none;
  }
  .pill-dot {
    animation: none !important;
  }
}
</style>
