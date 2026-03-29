<template>
  <v-dialog
    :model-value="visible"
    :max-width="alertType === 'emergency' ? 560 : 500"
    persistent
    no-click-animation
  >
    <div class="alert-card" :class="`alert-card--${alertType}`">
      <!-- Icon -->
      <div class="alert-icon-wrap" :class="`icon-wrap--${alertType}`">
        <v-icon :size="64" :color="iconColor">{{ alertIcon }}</v-icon>
      </div>

      <!-- Title -->
      <h2 class="alert-title" :class="`title--${alertType}`">{{ alertTitle }}</h2>

      <!-- Message -->
      <p class="alert-message">{{ message }}</p>

      <!-- Actions -->
      <div class="alert-actions" :class="alertType === 'emergency' ? 'alert-actions--two' : 'alert-actions--one'">
        <button class="action-btn action-btn--dismiss" @click="$emit('dismiss')">
          OK, Got it
        </button>
        <button
          v-if="alertType === 'emergency'"
          class="action-btn action-btn--assist"
          @click="$emit('request-assistance')"
        >
          I Need Help
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

const ALERT_CONFIG = {
  emergency: { title: "Emergency Alert",      icon: "mdi-alert-circle",       iconColor: "#fca5a5" },
  warning:   { title: "Important Notice",     icon: "mdi-alert",              iconColor: "#fcd34d" },
  reminder:  { title: "Reminder",             icon: "mdi-bell-ring",          iconColor: "#c084fc" },
  info:      { title: "Message for You",      icon: "mdi-information-outline", iconColor: "#93c5fd" },
};

const config    = computed(() => ALERT_CONFIG[props.alertType] ?? ALERT_CONFIG.info);
const alertTitle  = computed(() => config.value.title);
const alertIcon   = computed(() => config.value.icon);
const iconColor   = computed(() => config.value.iconColor);
</script>

<style scoped>
/* ── Card ───────────────────────────────────────────────────────────────── */
.alert-card {
  border-radius: 28px;
  padding: 40px 36px 32px;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 16px;
  backdrop-filter: blur(24px);
}

.alert-card--emergency {
  background: rgba(60, 10, 10, 0.96);
  border: 2px solid rgba(239, 68, 68, 0.60);
  box-shadow: 0 0 80px rgba(239, 68, 68, 0.30);
}

.alert-card--warning {
  background: rgba(40, 30, 8, 0.96);
  border: 2px solid rgba(245, 158, 11, 0.50);
  box-shadow: 0 0 60px rgba(245, 158, 11, 0.20);
}

.alert-card--reminder {
  background: rgba(30, 15, 45, 0.96);
  border: 2px solid rgba(168, 85, 247, 0.45);
  box-shadow: 0 0 60px rgba(168, 85, 247, 0.18);
}

.alert-card--info {
  background: rgba(10, 25, 50, 0.96);
  border: 2px solid rgba(99, 102, 241, 0.45);
  box-shadow: 0 0 60px rgba(99, 102, 241, 0.18);
}

/* ── Icon ───────────────────────────────────────────────────────────────── */
.alert-icon-wrap {
  width: 100px;
  height: 100px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 4px;
}

.icon-wrap--emergency { background: rgba(239, 68,  68,  0.15); }
.icon-wrap--warning   { background: rgba(245, 158, 11,  0.15); }
.icon-wrap--reminder  { background: rgba(168, 85,  247, 0.15); }
.icon-wrap--info      { background: rgba(99,  102, 241, 0.15); }

/* ── Title ──────────────────────────────────────────────────────────────── */
.alert-title {
  font-size: 1.75rem;
  font-weight: 700;
  line-height: 1.2;
  margin: 0;
}

.title--emergency { color: #fca5a5; }
.title--warning   { color: #fcd34d; }
.title--reminder  { color: #c084fc; }
.title--info      { color: #93c5fd; }

/* ── Message ────────────────────────────────────────────────────────────── */
.alert-message {
  font-size: 1.25rem;
  line-height: 1.6;
  color: rgba(255, 255, 255, 0.88);
  margin: 0;
  max-width: 420px;
}

/* ── Actions ────────────────────────────────────────────────────────────── */
.alert-actions {
  display: flex;
  gap: 14px;
  width: 100%;
  margin-top: 8px;
}

.alert-actions--one  { justify-content: center; }
.alert-actions--two  { justify-content: space-between; }

.action-btn {
  flex: 1;
  height: 60px;
  border: none;
  border-radius: 16px;
  font-size: 1.15rem;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s, transform 0.15s;
  letter-spacing: 0.01em;
}

.action-btn:active {
  transform: scale(0.97);
}

.action-btn--dismiss {
  background: rgba(255, 255, 255, 0.12);
  color: rgba(255, 255, 255, 0.90);
  border: 1px solid rgba(255, 255, 255, 0.18);
  max-width: 260px;
}

.action-btn--dismiss:hover {
  background: rgba(255, 255, 255, 0.18);
}

.action-btn--assist {
  background: linear-gradient(135deg, #ef4444, #dc2626);
  color: #fff;
  box-shadow: 0 4px 20px rgba(239, 68, 68, 0.45);
}

.action-btn--assist:hover {
  opacity: 0.9;
}
</style>
