<template>
  <v-dialog
    :model-value="visible"
    max-width="60vw"
    persistent
    no-click-animation
  >
    <div class="interactive-prompt-card">
      <!-- Icon -->
      <div class="prompt-icon-wrap">
        <v-icon :size="96" color="#93c5fd">mdi-message-question</v-icon>
      </div>

      <!-- Title -->
      <h2 class="prompt-title">Question for You</h2>

      <!-- Message -->
      <p class="prompt-message">{{ message }}</p>

      <!-- Countdown Timer -->
      <div class="countdown-display">
        <v-icon size="28" class="mr-1">mdi-timer-outline</v-icon>
        <span>{{ countdownText }}</span>
      </div>

      <!-- Actions -->
      <div class="prompt-actions">
        <button
          class="action-btn action-btn--dismiss"
          :disabled="buttonsDisabled"
          @click="handleDismiss"
        >
          {{ dismissButtonText }}
        </button>
        <button
          class="action-btn action-btn--escalate"
          :disabled="buttonsDisabled"
          @click="handleEscalate"
        >
          {{ escalateButtonText }}
        </button>
      </div>
    </div>
  </v-dialog>
</template>

<script setup>
import { ref, computed, watch, onUnmounted } from "vue";

const props = defineProps({
  visible: { type: Boolean, default: false },
  message: { type: String, default: "" },
  escalateButtonText: { type: String, default: "I need help" },
  dismissButtonText: { type: String, default: "I'm okay" },
  countdownSeconds: { type: Number, default: 30 },
  serverTimestamp: { type: String, required: true },
});

const emit = defineEmits(["response", "timeout"]);

const buttonsDisabled = ref(false);
const remainingSeconds = ref(props.countdownSeconds);
let animationFrameId = null;
let timeoutDeadline = null;

// Calculate timeout deadline using server timestamp to account for clock skew
function calculateDeadline() {
  const serverTime = new Date(props.serverTimestamp).getTime();
  const clientTime = Date.now();
  const skew = serverTime - clientTime;
  
  // Deadline = server time + countdown seconds
  timeoutDeadline = serverTime + (props.countdownSeconds * 1000);
  
  // Adjust for client clock
  return timeoutDeadline - skew;
}

// Format countdown as human-readable text
const countdownText = computed(() => {
  const seconds = Math.max(0, remainingSeconds.value);
  if (seconds >= 60) {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}m ${secs}s`;
  }
  return `${seconds}s`;
});

// Update countdown every second
function updateCountdown() {
  if (!timeoutDeadline) return;
  
  const now = Date.now();
  const remaining = Math.ceil((timeoutDeadline - now) / 1000);
  
  remainingSeconds.value = Math.max(0, remaining);
  
  if (remaining <= 0) {
    emit("timeout");
    stopCountdown();
    return;
  }
  
  animationFrameId = requestAnimationFrame(updateCountdown);
}

function startCountdown() {
  stopCountdown();
  calculateDeadline();
  updateCountdown();
}

function stopCountdown() {
  if (animationFrameId) {
    cancelAnimationFrame(animationFrameId);
    animationFrameId = null;
  }
}

function handleDismiss() {
  buttonsDisabled.value = true;
  stopCountdown();
  emit("response", "dismiss");
}

function handleEscalate() {
  buttonsDisabled.value = true;
  stopCountdown();
  emit("response", "escalate");
}

// Watch for visibility changes to start/stop countdown
watch(() => props.visible, (newVal) => {
  if (newVal) {
    buttonsDisabled.value = false;
    remainingSeconds.value = props.countdownSeconds;
    startCountdown();
  } else {
    stopCountdown();
  }
}, { immediate: true });

onUnmounted(() => {
  stopCountdown();
});
</script>

<style scoped>
/* ── Card ───────────────────────────────────────────────────────────────── */
.interactive-prompt-card {
  border-radius: 32px;
  padding: 60px 48px 48px;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 24px;
  background: rgba(10, 25, 50, 0.96);
  border: 2px solid rgba(99, 102, 241, 0.45);
  box-shadow: 0 0 60px rgba(99, 102, 241, 0.18);
  backdrop-filter: blur(24px);
  min-height: 50vh;
  justify-content: center;
}

/* ── Icon ───────────────────────────────────────────────────────────────── */
.prompt-icon-wrap {
  width: 140px;
  height: 140px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 8px;
  background: rgba(99, 102, 241, 0.15);
}

/* ── Title ──────────────────────────────────────────────────────────────── */
.prompt-title {
  font-size: 2.5rem;
  font-weight: 700;
  line-height: 1.2;
  margin: 0;
  color: #93c5fd;
}

/* ── Message ────────────────────────────────────────────────────────────── */
.prompt-message {
  font-size: 1.5rem;
  line-height: 1.6;
  color: rgba(255, 255, 255, 0.88);
  margin: 0;
  max-width: 90%;
}

/* ── Countdown ──────────────────────────────────────────────────────────── */
.countdown-display {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 12px 24px;
  border-radius: 16px;
  background: rgba(99, 102, 241, 0.12);
  color: #93c5fd;
  font-size: 1.3rem;
  font-weight: 600;
  margin-top: 8px;
}

/* ── Actions ────────────────────────────────────────────────────────────── */
.prompt-actions {
  display: flex;
  gap: 20px;
  width: 100%;
  max-width: 600px;
  margin-top: 16px;
  justify-content: space-between;
}

.action-btn {
  flex: 1;
  height: 70px;
  border: none;
  border-radius: 18px;
  font-size: 1.3rem;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s, transform 0.15s;
  letter-spacing: 0.01em;
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-btn:not(:disabled):active {
  transform: scale(0.97);
}

.action-btn--dismiss {
  background: rgba(255, 255, 255, 0.12);
  color: rgba(255, 255, 255, 0.90);
  border: 1px solid rgba(255, 255, 255, 0.18);
}

.action-btn--dismiss:not(:disabled):hover {
  background: rgba(255, 255, 255, 0.18);
}

.action-btn--escalate {
  background: linear-gradient(135deg, #ef4444, #dc2626);
  color: #fff;
  box-shadow: 0 4px 20px rgba(239, 68, 68, 0.45);
}

.action-btn--escalate:not(:disabled):hover {
  opacity: 0.9;
}
</style>
