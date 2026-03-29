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
        <v-icon size="32" color="white">
          {{ recording ? 'mdi-stop' : 'mdi-microphone' }}
        </v-icon>
      </button>
      <p class="mic-hint">{{ recording ? 'Tap to stop' : 'Tap to talk' }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";
import AudioVisualizer from "../AudioVisualizer.vue";

const props = defineProps({
  recording:  { type: Boolean, default: false },
  audioState: { type: String,  default: "idle" },
});

defineEmits(["audio-data", "state-change", "toggle-recording"]);

const STATUS_MAP = {
  idle:           "Ready",
  listening:      "Listening...",
  speaking:       "You're speaking",
  system_speaking:"System is responding",
};

const statusText = computed(() => STATUS_MAP[props.audioState] ?? "Ready");
</script>

<style scoped>
/* ── Card shell ─────────────────────────────────────────────────────────── */
.voice-card {
  background: rgba(22, 20, 38, 0.72);
  backdrop-filter: blur(24px);
  border-radius: 24px;
  border: 1px solid rgba(255, 255, 255, 0.07);
  padding: 24px 20px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  transition: border-color 0.4s ease, box-shadow 0.4s ease;
  width: 100%;
  box-sizing: border-box;
}

.voice-card--listening {
  border-color: rgba(99, 102, 241, 0.30);
  box-shadow: 0 0 48px rgba(99, 102, 241, 0.12);
}

.voice-card--speaking {
  border-color: rgba(245, 158, 11, 0.30);
  box-shadow: 0 0 48px rgba(245, 158, 11, 0.12);
}

.voice-card--system_speaking {
  border-color: rgba(139, 92, 246, 0.35);
  box-shadow: 0 0 56px rgba(139, 92, 246, 0.16);
}

/* ── Status pill ────────────────────────────────────────────────────────── */
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  align-self: flex-start;
  padding: 5px 14px 5px 10px;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 500;
  letter-spacing: 0.02em;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.10);
  color: rgba(255, 255, 255, 0.65);
  transition: all 0.3s ease;
}

.pill-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.7;
}

.pill--idle            { color: rgba(255,255,255,0.45); }
.pill--listening       { color: #818cf8; border-color: rgba(99,102,241,0.30); background: rgba(99,102,241,0.10); }
.pill--speaking        { color: #fbbf24; border-color: rgba(245,158,11,0.30); background: rgba(245,158,11,0.10); }
.pill--system_speaking { color: #c084fc; border-color: rgba(139,92,246,0.30); background: rgba(139,92,246,0.10); }

.pill--listening .pill-dot,
.pill--speaking .pill-dot,
.pill--system_speaking .pill-dot {
  animation: blink 1.4s ease-in-out infinite;
}

/* ── Waveform ───────────────────────────────────────────────────────────── */
.waveform-region {
  width: 100%;
}

/* ── Mic button ─────────────────────────────────────────────────────────── */
.mic-region {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding-top: 4px;
}

.mic-btn {
  width: 72px;
  height: 72px;
  border-radius: 50%;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.2s ease, box-shadow 0.3s ease;
  outline: none;
  position: relative;
}

.mic-btn--idle {
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  box-shadow: 0 4px 20px rgba(99, 102, 241, 0.40);
}

.mic-btn--idle:hover {
  transform: scale(1.06);
  box-shadow: 0 6px 28px rgba(99, 102, 241, 0.55);
}

.mic-btn--active {
  background: linear-gradient(135deg, #ef4444, #dc2626);
  box-shadow: 0 4px 20px rgba(239, 68, 68, 0.45);
  animation: pulse-ring 1.5s ease-in-out infinite;
}

.mic-hint {
  font-size: 0.78rem;
  color: rgba(255, 255, 255, 0.35);
  margin: 0;
  letter-spacing: 0.03em;
}

/* ── Keyframes ──────────────────────────────────────────────────────────── */
@keyframes blink {
  0%, 100% { opacity: 0.7; }
  50%       { opacity: 1; }
}

@keyframes pulse-ring {
  0%   { box-shadow: 0 0 0 0   rgba(239, 68, 68, 0.50); }
  70%  { box-shadow: 0 0 0 14px rgba(239, 68, 68, 0);   }
  100% { box-shadow: 0 0 0 0   rgba(239, 68, 68, 0);    }
}
</style>
