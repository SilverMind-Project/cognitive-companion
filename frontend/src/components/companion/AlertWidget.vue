<template>
  <v-dialog
    :model-value="visible"
    max-width="60vw"
    persistent
    no-click-animation
  >
    <div class="alert-card" :class="`alert-card--${alertType}`">
      <!-- Icon -->
      <div class="alert-icon-wrap">
        <v-icon :size="52" :color="iconColor">{{ alertIcon }}</v-icon>
      </div>

      <!-- Title -->
      <h2 class="alert-title">{{ alertTitle }}</h2>

      <!-- Message -->
      <p class="alert-message">{{ message }}</p>

      <!-- Actions -->
      <div class="alert-actions" :class="alertType === 'emergency' ? 'alert-actions--two' : 'alert-actions--one'">
        <button class="action-btn action-btn--dismiss" @click="$emit('dismiss')">
          OK, got it
        </button>
        <button
          v-if="alertType === 'emergency'"
          class="action-btn action-btn--assist"
          @click="$emit('request-assistance')"
        >
          I need help
        </button>
      </div>
    </div>
  </v-dialog>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  visible:   { type: Boolean, default: false },
  message:   { type: String,  default: "" },
  alertType: { type: String,  default: "info" }, // emergency | warning | info | reminder
});

defineEmits(["dismiss", "request-assistance"]);

// DS CompanionPrompt mapping: emergency -> alert pair, warning -> notice pair,
// info -> info pair, reminder -> brand/sage. Icon colours read the semantic
// foreground tokens so the icon matches its tinted circle.
const ALERT_CONFIG = {
  emergency: { title: "Emergency alert",  icon: "mdi-heart-pulse",         iconColor: "var(--alert-fg)" },
  warning:   { title: "Important notice", icon: "mdi-information-outline",  iconColor: "var(--notice-fg)" },
  reminder:  { title: "Reminder",         icon: "mdi-bell-ring-outline",   iconColor: "var(--sage-600)" },
  info:      { title: "Message for you",  icon: "mdi-message-text-outline", iconColor: "var(--info-fg)" },
};

const config    = computed(() => ALERT_CONFIG[props.alertType] ?? ALERT_CONFIG.info);
const alertTitle  = computed(() => config.value.title);
const alertIcon   = computed(() => config.value.icon);
const iconColor   = computed(() => config.value.iconColor);
</script>

<style scoped>
/* ── Card — warm paper, semantic hairline border (DS CompanionPrompt) ────── */
.alert-card {
  /* per-type tint + line set by the modifier classes below */
  --tint: var(--sage-50);
  --line: var(--line-brand);
  background: var(--cc-bg-elevated);
  border: 1.5px solid var(--line);
  border-radius: var(--cc-radius-xl);
  box-shadow: var(--cc-shadow-lg);
  padding: 48px 44px 40px;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 20px;
  min-height: 50vh;
  justify-content: center;
}

.alert-card--emergency { --tint: var(--alert-bg);  --line: var(--alert-line); }
.alert-card--warning   { --tint: var(--notice-bg); --line: var(--notice-line); }
.alert-card--reminder  { --tint: var(--sage-50);   --line: var(--line-brand); }
.alert-card--info      { --tint: var(--info-bg);   --line: var(--info-line); }

/* ── Icon ───────────────────────────────────────────────────────────────── */
.alert-icon-wrap {
  width: 104px;
  height: 104px;
  border-radius: var(--cc-radius-pill);
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--tint);
}

/* ── Title ──────────────────────────────────────────────────────────────── */
.alert-title {
  font-family: var(--cc-font-display);
  font-weight: 500;
  font-size: 40px;
  line-height: 1.1;
  letter-spacing: -0.02em;
  color: var(--cc-text-1);
  margin: 0;
}

/* ── Message ────────────────────────────────────────────────────────────── */
.alert-message {
  font-size: 24px;
  line-height: 1.5;
  color: var(--cc-text-2);
  margin: 0;
  max-width: 52ch;
}

/* ── Actions ────────────────────────────────────────────────────────────── */
.alert-actions {
  display: flex;
  gap: 16px;
  width: 100%;
  max-width: 520px;
  margin-top: 8px;
}

.alert-actions--one  { justify-content: center; }
.alert-actions--two  { justify-content: space-between; }

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

.action-btn:active {
  transform: scale(0.98);
}

.action-btn--dismiss {
  background: var(--cc-surface);
  color: var(--text-brand);
  border: 1.5px solid var(--line-soft);
  max-width: 320px;
}

.action-btn--dismiss:hover {
  background: var(--cc-surface-2);
}

.action-btn--assist {
  background: var(--terra-400);
  color: #FFF8F3;
  border: 1.5px solid transparent;
  box-shadow: var(--cc-shadow-sm);
}

.action-btn--assist:hover {
  background: var(--terra-500);
}

@media (prefers-reduced-motion: reduce) {
  .action-btn { transition: none; }
}
</style>
