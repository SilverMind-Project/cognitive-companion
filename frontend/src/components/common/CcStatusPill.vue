<script setup>
/**
 * CcStatusPill — the design system's signature wellbeing indicator.
 * A calm pill that pairs a colored dot with a reading. Larger and softer than a
 * status v-chip; use it for the headline wellbeing state of a person or room.
 *
 *   <CcStatusPill status="steady" detail="Calm night, up at 7:10am" />
 *   <CcStatusPill status="notice" label="Worth a look" detail="Quieter in the kitchen" />
 *
 * Statuses: steady | notice | quiet | alert. Lead with the calm reading; only
 * escalate the status when something genuinely warrants attention.
 */
const props = defineProps({
  status: { type: String, default: "steady" }, // steady | notice | quiet | alert
  label: { type: String, default: "" },
  detail: { type: String, default: "" },
});

const WORDS = {
  steady: "Steady",
  notice: "Worth a look",
  quiet: "Quiet",
  alert: "Needs awareness",
};

const word = () => props.label || WORDS[props.status] || WORDS.steady;
</script>

<template>
  <span class="cc-status-pill" :class="`cc-status-pill--${status}`" :data-detail="!!detail">
    <span class="cc-status-pill__dot" aria-hidden="true" />
    <span class="cc-status-pill__body">
      <span class="cc-status-pill__label">{{ word() }}</span>
      <span v-if="detail" class="cc-status-pill__detail">{{ detail }}</span>
    </span>
  </span>
</template>

<style scoped>
.cc-status-pill {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 7px 14px 7px 11px;
  border-radius: var(--cc-radius-pill);
  border: 1px solid transparent;
}
.cc-status-pill[data-detail="true"] {
  padding: 8px 16px 8px 12px;
}

.cc-status-pill__dot {
  width: 10px;
  height: 10px;
  border-radius: var(--cc-radius-pill);
  flex: none;
}

.cc-status-pill__body {
  display: flex;
  flex-direction: column;
  line-height: 1.2;
}
.cc-status-pill__label {
  font-family: var(--cc-font);
  font-weight: 700;
  font-size: 0.875rem;
}
.cc-status-pill__detail {
  font-size: 0.78rem;
  opacity: 0.82;
}

/* Tones — calm DS pairs (background + border + foreground + dot). */
.cc-status-pill--steady {
  background: var(--good-bg);
  border-color: var(--good-line);
  color: var(--good-fg);
}
.cc-status-pill--steady .cc-status-pill__dot { background: var(--green-care); box-shadow: 0 0 0 4px var(--good-bg); }

.cc-status-pill--notice {
  background: var(--notice-bg);
  border-color: var(--notice-line);
  color: var(--notice-fg);
}
.cc-status-pill--notice .cc-status-pill__dot { background: var(--gold-notice); box-shadow: 0 0 0 4px var(--notice-bg); }

.cc-status-pill--alert {
  background: var(--alert-bg);
  border-color: var(--alert-line);
  color: var(--alert-fg);
}
.cc-status-pill--alert .cc-status-pill__dot { background: var(--brick-alert); box-shadow: 0 0 0 4px var(--alert-bg); }

.cc-status-pill--quiet {
  background: var(--cc-surface-2);
  border-color: var(--cc-divider);
  color: var(--cc-text-2);
}
.cc-status-pill--quiet .cc-status-pill__dot { background: var(--stone-400); box-shadow: 0 0 0 4px var(--cc-surface-2); }
</style>
