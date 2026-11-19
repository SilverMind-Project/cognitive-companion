<template>
  <div>
    <div class="d-flex align-center flex-wrap ga-3 mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Identity setup</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Recognizing people is a chain: enroll everyone, capture and label faces, deploy the
          calibration, turn on calibrated faces, then let them teach body appearance. This page
          shows which link is broken today and what to do next.
        </div>
      </div>
      <v-spacer />
      <v-btn
        size="small"
        variant="text"
        prepend-icon="mdi-refresh"
        :loading="state.loading"
        data-test="refresh"
        @click="actions.load"
      >
        Refresh
      </v-btn>
    </div>

    <v-alert
      v-if="state.forbidden"
      type="warning"
      variant="tonal"
      class="mb-4"
      data-test="forbidden"
    >
      Identity setup needs the identity readiness permission.
    </v-alert>

    <v-alert v-if="state.error" type="error" variant="tonal" class="mb-4" data-test="load-error">
      {{ state.error }}
      <template #append>
        <v-btn size="small" variant="text" @click="actions.load">Retry</v-btn>
      </template>
    </v-alert>

    <div v-if="state.loading && !state.readiness" class="d-flex justify-center pa-8">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <template v-else-if="state.readiness && !state.forbidden">
      <v-alert
        v-if="blocking"
        type="info"
        variant="tonal"
        class="mb-4"
        data-test="blocking-summary"
      >
        Start with <strong>{{ STEP_PRESENTATION[blocking].title }}</strong>: it is blocked, and the
        steps after it cannot make progress until it is done.
      </v-alert>

      <section v-for="group in groups" :key="group.title" class="mb-6">
        <div class="text-subtitle-1 font-weight-bold mb-2">{{ group.title }}</div>
        <v-card class="glass-card">
          <v-list lines="three" class="py-0">
            <template v-for="(step, i) in group.steps" :key="step.key">
              <v-divider v-if="i > 0" />
              <v-list-item :data-test="`step-${step.key}`" class="py-3">
                <template #prepend>
                  <div class="chain-number text-medium-emphasis mr-3">
                    {{ chainLabel(step.key) }}
                  </div>
                </template>
                <v-list-item-title class="d-flex align-center flex-wrap ga-2">
                  <span class="font-weight-medium">{{ STEP_PRESENTATION[step.key].title }}</span>
                  <v-chip
                    size="small"
                    variant="tonal"
                    :color="STATE_PRESENTATION[step.state].color"
                    :data-test="`state-${step.key}`"
                  >
                    {{ STATE_PRESENTATION[step.state].label }}
                  </v-chip>
                  <v-chip
                    v-if="step.key === blocking"
                    size="small"
                    variant="outlined"
                    data-test="start-here"
                  >
                    Start here
                  </v-chip>
                </v-list-item-title>
                <div class="text-body-2 mt-1">{{ step.detail }}</div>
                <div v-if="step.next_action !== 'none'" class="text-body-2 mt-2">
                  <v-btn
                    v-if="ACTION_PRESENTATION[step.next_action].to"
                    size="small"
                    variant="tonal"
                    :to="ACTION_PRESENTATION[step.next_action].to"
                    :data-test="`action-${step.key}`"
                  >
                    {{ ACTION_PRESENTATION[step.next_action].text }}
                  </v-btn>
                  <span v-else class="text-medium-emphasis" :data-test="`action-${step.key}`">
                    Next: {{ ACTION_PRESENTATION[step.next_action].text }}.
                  </span>
                </div>
              </v-list-item>
            </template>
          </v-list>
        </v-card>
      </section>

      <section v-if="state.readiness.review_queues.length" class="mb-6" data-test="review-queues">
        <div class="text-subtitle-1 font-weight-bold mb-2">Review queues</div>
        <v-card class="glass-card">
          <v-list lines="two" class="py-0">
            <template v-for="(queue, i) in state.readiness.review_queues" :key="queue.surface">
              <v-divider v-if="i > 0" />
              <v-list-item :data-test="`queue-${queue.surface}`" class="py-3">
                <v-list-item-title class="d-flex align-center flex-wrap ga-2">
                  <span class="font-weight-medium">{{
                    REVIEW_QUEUE_PRESENTATION[queue.surface].title
                  }}</span>
                  <v-chip
                    size="small"
                    variant="tonal"
                    :color="queue.waiting ? 'warning' : undefined"
                    :data-test="`waiting-${queue.surface}`"
                  >
                    {{ waitingLabel(queue.waiting) }}
                  </v-chip>
                </v-list-item-title>
                <div class="text-body-2 mt-1">
                  {{ REVIEW_QUEUE_PRESENTATION[queue.surface].subject }}
                </div>
                <template #append>
                  <v-btn
                    size="small"
                    variant="text"
                    :to="REVIEW_QUEUE_PRESENTATION[queue.surface].to"
                    :data-test="`open-${queue.surface}`"
                  >
                    Open
                  </v-btn>
                </template>
              </v-list-item>
            </template>
          </v-list>
        </v-card>
      </section>

      <div class="text-caption text-medium-emphasis">
        Checked {{ formatDateTime(state.readiness.checked_at) }}. Face calibration labels face crops
        so a face score becomes a trustworthy probability; the ReID Review Queue reviews
        body-appearance samples, which are proposed only after calibrated faces are live.
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useIdentityReadiness } from "@/composables/useIdentityReadiness";
import {
  ACTION_PRESENTATION,
  PREREQUISITE_KEYS,
  STATE_PRESENTATION,
  STEP_PRESENTATION,
  type ReadinessStepKey,
} from "@/constants/identityReadiness";
import { REVIEW_QUEUE_PRESENTATION } from "@/constants/identityReview";
import { formatDateTime } from "@/services/timezone.js";

const { state, actions } = useIdentityReadiness();

const blocking = computed(() => state.readiness?.blocking_step ?? null);

const groups = computed(() => {
  const steps = state.readiness?.steps ?? [];
  return [
    {
      title: "Before you start",
      steps: steps.filter((s) => PREREQUISITE_KEYS.includes(s.key)),
    },
    {
      title: "The identity chain",
      steps: steps.filter((s) => !PREREQUISITE_KEYS.includes(s.key)),
    },
  ].filter((g) => g.steps.length);
});

function chainLabel(key: ReadinessStepKey): string {
  const links = STEP_PRESENTATION[key].chain;
  if (!links.length) return "";
  return links.length === 1 ? String(links[0]) : `${links[0]}-${links[links.length - 1]}`;
}

// A queue whose owner could not be read has no count; it is never shown as empty.
function waitingLabel(waiting: number | null): string {
  if (waiting === null) return "Count unavailable";
  return waiting === 0 ? "Nothing waiting" : `${waiting} waiting`;
}

onMounted(() => void actions.load());
</script>

<style scoped>
.chain-number {
  min-width: 2.5rem;
  font-variant-numeric: tabular-nums;
}
</style>
