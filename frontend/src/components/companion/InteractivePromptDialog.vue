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
        <v-icon :size="52" color="var(--info-fg)">{{ icon }}</v-icon>
      </div>

      <!-- Title -->
      <h2 class="prompt-title">{{ title }}</h2>

      <!-- Message -->
      <p class="prompt-message">{{ message }}</p>

      <!-- Countdown Timer -->
      <div class="countdown-display">
        <v-icon size="22" class="mr-1">mdi-timer-outline</v-icon>
        <span>Closes on its own in {{ countdownText }}</span>
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
  title: { type: String, default: "Question for You" },
  icon: { type: String, default: "mdi-message-question" },
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
/* ── Card — warm paper, info-pair hairline (DS CompanionPrompt, question) ── */
.interactive-prompt-card {
  border-radius: var(--cc-radius-xl);
  padding: 48px 44px 40px;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 20px;
  background: var(--cc-bg-elevated);
  border: 1.5px solid var(--info-line);
  box-shadow: var(--cc-shadow-lg);
  min-height: 50vh;
  justify-content: center;
}

/* ── Icon ───────────────────────────────────────────────────────────────── */
.prompt-icon-wrap {
  width: 104px;
  height: 104px;
  border-radius: var(--cc-radius-pill);
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--info-bg);
}

/* ── Title ──────────────────────────────────────────────────────────────── */
.prompt-title {
  font-family: var(--cc-font-display);
  font-weight: 500;
  font-size: 40px;
  line-height: 1.1;
  letter-spacing: -0.02em;
  margin: 0;
  color: var(--cc-text-1);
}

/* ── Message ────────────────────────────────────────────────────────────── */
.prompt-message {
  font-size: 24px;
  line-height: 1.5;
  color: var(--cc-text-2);
  margin: 0;
  max-width: 52ch;
}

/* ── Countdown ──────────────────────────────────────────────────────────── */
.countdown-display {
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--cc-font-mono);
  color: var(--cc-text-3);
  font-size: 15px;
  font-weight: 500;
}

/* ── Actions ────────────────────────────────────────────────────────────── */
.prompt-actions {
  display: flex;
  gap: 16px;
  width: 100%;
  max-width: 520px;
  margin-top: 8px;
  justify-content: space-between;
}

.action-btn {
  flex: 1;
  min-height: 72px;
  border-radius: var(--cc-radius-md);
  font-family: var(--cc-font);
  font-size: 22px;
  font-weight: 600;
  cursor: pointer;
  transition: background var(--cc-dur-fast) var(--cc-ease-standard),
              transform var(--cc-dur-fast) var(--cc-ease-standard);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-btn:not(:disabled):active {
  transform: scale(0.98);
}

.action-btn--dismiss {
  background: var(--cc-surface);
  color: var(--text-brand);
  border: 1.5px solid var(--line-soft);
}

.action-btn--dismiss:not(:disabled):hover {
  background: var(--cc-surface-2);
}

.action-btn--escalate {
  background: var(--terra-400);
  color: #FFF8F3;
  border: 1.5px solid transparent;
  box-shadow: var(--cc-shadow-sm);
}

.action-btn--escalate:not(:disabled):hover {
  background: var(--terra-500);
}

@media (prefers-reduced-motion: reduce) {
  .action-btn { transition: none; }
}
</style>
