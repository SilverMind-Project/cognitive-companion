<template>
  <section
    v-if="visible"
    class="guided-task glass-card"
    aria-label="Your routine"
    data-test="guided-task-widget"
  >
    <template v-if="celebrating">
      <div class="guided-celebrate" role="status" data-test="guided-celebrate">
        <v-icon size="56" color="success" aria-hidden="true">mdi-party-popper</v-icon>
        <p class="guided-prompt-text">Well done! You finished {{ session.routine_name }}.</p>
      </div>
    </template>

    <template v-else>
      <header class="guided-header">
        <h2 class="guided-title">{{ session.routine_name }}</h2>
        <span class="guided-progress-pill" data-test="guided-progress">{{ progressLabel }}</span>
      </header>
      <v-progress-linear
        :model-value="progressPercent"
        color="primary"
        height="8"
        rounded
        aria-hidden="true"
        class="mb-4"
      />

      <p class="guided-prompt-text" aria-live="polite" data-test="guided-prompt">
        {{ session.prompt_text }}
      </p>

      <div v-if="helpOnTheWay" class="guided-help-banner" role="status" data-test="guided-help">
        <v-icon size="28" aria-hidden="true">mdi-hand-heart-outline</v-icon>
        <span>Help is on the way. A family member or caregiver has been told.</span>
      </div>

      <div class="guided-actions">
        <v-btn
          v-if="canFinishStep"
          color="success"
          variant="flat"
          size="x-large"
          prepend-icon="mdi-check-circle-outline"
          class="guided-btn"
          :loading="pendingAction === 'done'"
          :disabled="busy"
          data-test="guided-done"
          @click="emit('action', 'done')"
        >
          I'm done
        </v-btn>
        <v-btn
          color="primary"
          variant="tonal"
          size="x-large"
          prepend-icon="mdi-volume-high"
          class="guided-btn"
          :loading="pendingAction === 'repeat'"
          :disabled="busy"
          data-test="guided-repeat"
          @click="emit('action', 'repeat')"
        >
          Say it again
        </v-btn>
        <v-btn
          color="warning"
          variant="tonal"
          size="x-large"
          prepend-icon="mdi-hand-heart-outline"
          class="guided-btn"
          :loading="pendingAction === 'help'"
          :disabled="busy"
          data-test="guided-help-button"
          @click="emit('action', 'help')"
        >
          I need help
        </v-btn>
      </div>
    </template>
  </section>
</template>

<script setup>
/**
 * The resident's step-by-step routine card: the current step in large type that
 * stays on screen after the voice has finished, with touch buttons that do what
 * saying it aloud does. Presentational: state and taps live in
 * `useResidentGuidedSession`. It shows nothing technical (no ids, gates, or
 * status codes).
 */
import { computed } from "vue";
import { STEP_IN_PROGRESS } from "@/composables/useResidentGuidedSession.js";

const props = defineProps({
  /** A `guided_session_state` payload, or null when no routine is running. */
  session: { type: Object, default: null },
  /** The tap awaiting its answer, or null. */
  pendingAction: { type: String, default: null },
  celebrating: { type: Boolean, default: false },
});

const emit = defineEmits(["action"]);

const visible = computed(
  () => props.session !== null && (props.celebrating || STEP_IN_PROGRESS.has(props.session.status)),
);
const busy = computed(() => props.pendingAction !== null);
const helpOnTheWay = computed(() =>
  ["escalated", "caregiver_takeover"].includes(props.session?.status),
);
// While a caregiver has taken over, they move her through the steps.
const canFinishStep = computed(() => props.session?.status !== "caregiver_takeover");
const stepNumber = computed(() => (props.session?.current_step_ord ?? 0) + 1);
const progressLabel = computed(() => `Step ${stepNumber.value} of ${props.session.total_steps}`);
const progressPercent = computed(() => {
  const total = props.session?.total_steps || 1;
  return Math.min(100, (stepNumber.value / total) * 100);
});
</script>

<style scoped>
.guided-task {
  padding: 24px;
  margin-bottom: 16px;
  border-radius: var(--cc-radius-lg);
}

.guided-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.guided-title {
  font-size: clamp(1.25rem, 2vw, 1.6rem);
  font-weight: 600;
  color: var(--cc-text-2);
}

.guided-progress-pill {
  padding: 6px 14px;
  border-radius: var(--cc-radius-pill);
  background: var(--cc-brand-soft);
  color: var(--cc-text-1);
  font-size: 1.1rem;
  font-weight: 600;
  white-space: nowrap;
}

.guided-prompt-text {
  font-size: clamp(1.5rem, 2.5vw, 2rem);
  line-height: 1.45;
  font-weight: 500;
  color: var(--cc-text-1);
  margin-bottom: 20px;
}

.guided-help-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  margin-bottom: 20px;
  border-radius: var(--cc-radius-md);
  background: var(--cc-warning-softer);
  color: var(--cc-text-1);
  font-size: 1.25rem;
}

/* One full-width button per row: the same order and place every time, and no
   lone button wrapping onto its own row. */
.guided-actions {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
}

.guided-btn {
  min-height: 64px;
  font-size: 1.25rem;
  text-transform: none;
  letter-spacing: normal;
}

.guided-celebrate {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  text-align: center;
}
</style>
