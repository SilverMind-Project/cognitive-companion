<template>
  <div>
    <!-- Header -->
    <div class="d-flex align-center flex-wrap ga-3 mb-4">
      <v-btn
        variant="text"
        prepend-icon="mdi-arrow-left"
        size="small"
        :to="{ name: 'admin-guided-sessions' }"
      >
        Sessions
      </v-btn>
      <v-divider vertical class="mx-1" />
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">
          Session #{{ id }}
        </h2>
        <div v-if="state.session" class="text-body-2 text-medium-emphasis mt-1">
          {{ state.session.person_id }} &middot; Routine #{{ state.session.routine_id }}
        </div>
      </div>
      <v-spacer />
      <v-chip
        v-if="state.session"
        :color="statusColor(state.session.status)"
        size="small"
        variant="tonal"
      >
        {{ state.session.status }}
      </v-chip>
      <v-chip size="small" :color="wsColor" variant="outlined">
        WS: {{ state.wsStatus }}
      </v-chip>
    </div>

    <!-- Escalation banner -->
    <v-alert
      v-if="state.escalationBanner"
      type="warning"
      variant="tonal"
      class="mb-4"
      density="compact"
    >
      <strong>Escalation:</strong> {{ state.escalationBanner.reason }}
      <v-btn
        v-if="canTakeover"
        variant="flat"
        color="warning"
        size="small"
        class="ml-3"
        :loading="state.saving"
        @click="actions.takeover()"
      >
        Take Over
      </v-btn>
    </v-alert>

    <v-row v-if="state.loading">
      <v-col class="text-center pa-12">
        <v-progress-circular indeterminate color="primary" />
      </v-col>
    </v-row>

    <v-row v-else>
      <!-- Left: live session state -->
      <v-col cols="12" md="4">
        <v-card class="glass-card mb-4">
          <v-card-title class="text-subtitle-1">Current Step</v-card-title>
          <v-card-text v-if="state.currentStep">
            <div class="text-caption text-medium-emphasis mb-1">
              Step {{ state.currentStep.ord + 1 }}
            </div>
            <div class="text-body-2 mb-3">{{ state.currentStep.prompt_text }}</div>
            <v-chip
              v-if="state.currentStep.is_safety_critical"
              color="error"
              size="small"
              variant="tonal"
            >
              Safety critical
            </v-chip>
          </v-card-text>
          <v-card-text v-else class="text-medium-emphasis">
            No active step
          </v-card-text>
        </v-card>

        <!-- Caregiver controls (status-gated) -->
        <v-card class="glass-card">
          <v-card-title class="text-subtitle-1">Controls</v-card-title>
          <v-card-text>
            <div v-if="!isInTakeover" class="d-flex flex-column ga-2">
              <v-btn
                v-if="canTakeover"
                color="primary"
                variant="tonal"
                prepend-icon="mdi-account-switch"
                :loading="state.saving"
                @click="actions.takeover()"
              >
                Take Over Session
              </v-btn>
              <div v-else class="text-caption text-medium-emphasis">
                Controls available when session is escalated or in takeover.
              </div>
            </div>

            <div v-else class="d-flex flex-column ga-2">
              <!-- Say -->
              <v-text-field
                v-model="sayText"
                label="Send message"
                density="compact"
                hide-details
                placeholder="Speak on caregiver's behalf"
                append-inner-icon="mdi-send"
                @click:append-inner="sendSay"
                @keyup.enter="sendSay"
              />

              <!-- Advance -->
              <v-btn
                variant="tonal"
                prepend-icon="mdi-arrow-right-circle"
                :loading="state.saving"
                @click="actions.advance()"
              >
                Advance Step
              </v-btn>

              <!-- Complete / Release -->
              <v-row class="ma-0">
                <v-col cols="6" class="pa-0 pr-1">
                  <v-btn
                    block
                    variant="flat"
                    color="success"
                    prepend-icon="mdi-check"
                    :loading="state.saving"
                    @click="actions.complete()"
                  >
                    Complete
                  </v-btn>
                </v-col>
                <v-col cols="6" class="pa-0 pl-1">
                  <v-btn
                    block
                    variant="tonal"
                    prepend-icon="mdi-undo"
                    :loading="state.saving"
                    @click="actions.release()"
                  >
                    Release
                  </v-btn>
                </v-col>
              </v-row>
            </div>
          </v-card-text>
        </v-card>
      </v-col>

      <!-- Right: attributed transcript + event log -->
      <v-col cols="12" md="8">
        <!-- Transcript -->
        <v-card class="glass-card mb-4">
          <v-card-title class="text-subtitle-1">Transcript</v-card-title>
          <v-card-text class="pa-0">
            <div
              v-if="state.transcript.length === 0"
              class="pa-4 text-center text-medium-emphasis"
            >
              No transcript yet
            </div>
            <div
              v-for="(turn, i) in state.transcript"
              :key="i"
              class="turn-row pa-3"
              :class="`turn-row--${turn.actor}`"
            >
              <div class="d-flex align-center mb-1">
                <v-chip
                  size="x-small"
                  :color="actorColor(turn.actor)"
                  variant="tonal"
                  class="mr-2"
                >
                  {{ actorLabel(turn.actor) }}
                </v-chip>
                <span
                  v-if="turn.timestamp"
                  class="text-caption text-medium-emphasis font-mono"
                >
                  {{ formatTimeOnly(turn.timestamp) }}
                </span>
              </div>
              <div class="text-body-2">{{ turn.content }}</div>
            </div>
          </v-card-text>
        </v-card>

        <!-- Event log -->
        <v-card class="glass-card">
          <v-card-title class="text-subtitle-1">Events</v-card-title>
          <v-card-text class="pa-0">
            <div
              v-if="state.events.length === 0"
              class="pa-4 text-center text-medium-emphasis"
            >
              No events yet
            </div>
            <v-list density="compact">
              <v-list-item
                v-for="ev in state.events"
                :key="ev.id"
                class="event-row"
              >
                <template #prepend>
                  <v-chip size="x-small" variant="tonal" class="mr-2">
                    {{ ev.kind }}
                  </v-chip>
                </template>
                <v-list-item-title class="text-caption">
                  Step {{ ev.step_ord != null ? ev.step_ord + 1 : "?" }}
                  <span v-if="ev.actor" class="text-medium-emphasis"> &middot; {{ ev.actor }}</span>
                </v-list-item-title>
                <template #append>
                  <span class="text-caption text-medium-emphasis font-mono">
                    {{ formatTimeOnly(ev.at) }}
                  </span>
                </template>
              </v-list-item>
            </v-list>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<script setup>
import { ref, computed } from "vue";
import { useGuidedSessionConsole } from "@/composables/useGuidedSessionConsole.js";
import { formatTimeOnly } from "@/services/timezone.js";

const props = defineProps({
  id: { type: String, required: true },
});

const { state, actions } = useGuidedSessionConsole(props.id);

const sayText = ref("");

const canTakeover = computed(() =>
  state.session &&
  ["escalated", "caregiver_takeover"].includes(state.session.status),
);

const isInTakeover = computed(
  () => state.session?.status === "caregiver_takeover",
);

const wsColor = computed(() => {
  const map = { open: "success", connecting: "info", closed: undefined, error: "error" };
  return map[state.wsStatus];
});

function statusColor(status) {
  const map = {
    active: "success", waiting: "info", escalated: "warning",
    caregiver_takeover: "warning", completed: "success",
    abandoned: undefined, failed: "error", summoning: "info", pending: undefined,
  };
  return map[status];
}

function actorColor(actor) {
  const map = { user: "primary", assistant: "info", caregiver: "warning", orchestrator: undefined };
  return map[actor] ?? undefined;
}

function actorLabel(actor) {
  const map = { user: "Person", assistant: "AI", caregiver: "Caregiver", orchestrator: "System" };
  return map[actor] ?? actor;
}

async function sendSay() {
  if (!sayText.value.trim()) return;
  await actions.say(sayText.value);
  sayText.value = "";
}
</script>

<style scoped>
.turn-row {
  border-bottom: 1px solid var(--cc-divider);
}

.turn-row:last-child {
  border-bottom: none;
}

.turn-row--caregiver {
  background: rgba(201, 138, 46, 0.06);
}

.font-mono {
  font-family: var(--cc-font-mono);
}
</style>
