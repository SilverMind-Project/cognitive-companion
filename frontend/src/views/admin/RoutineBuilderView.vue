<template>
  <div>
    <!-- Header -->
    <div class="d-flex align-center flex-wrap ga-3 mb-4">
      <v-btn
        variant="text"
        prepend-icon="mdi-arrow-left"
        size="small"
        :to="{ name: 'admin-routines' }"
      >
        Routines
      </v-btn>
      <v-divider vertical class="mx-1" />
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">
          {{ state.routine?.name ?? "Loading..." }}
        </h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Routine for {{ state.routine?.person_id ?? "" }}
        </div>
      </div>
      <v-spacer />
      <v-chip
        v-if="state.routine"
        :color="state.routine.is_enabled ? 'success' : undefined"
        size="small"
        variant="tonal"
      >
        {{ state.routine.is_enabled ? "Enabled" : "Disabled" }}
      </v-chip>
      <v-btn
        variant="tonal"
        color="primary"
        prepend-icon="mdi-chart-bar"
        :to="{ name: 'admin-routine-metrics', params: { id } }"
      >
        Metrics
      </v-btn>
      <v-btn
        variant="flat"
        color="secondary"
        prepend-icon="mdi-play-outline"
        :loading="state.testRunning"
        :disabled="state.steps.length === 0"
        @click="runTest"
      >
        Test Run
      </v-btn>
      <v-btn
        color="primary"
        variant="flat"
        prepend-icon="mdi-content-save-outline"
        :loading="state.saving"
        @click="actions.saveSteps()"
      >
        Save Steps
      </v-btn>
    </div>

    <v-alert v-if="state.error" type="error" density="compact" class="mb-4" closable>
      {{ state.error }}
    </v-alert>

    <v-row>
      <!-- Left: routine-level settings -->
      <v-col cols="12" md="4">
        <v-card class="glass-card">
          <v-card-title class="text-subtitle-1">Routine Settings</v-card-title>
          <v-card-text v-if="state.routine">
            <v-text-field
              v-model="routineEdit.name"
              label="Name"
              density="comfortable"
            />
            <v-select
              v-model="routineRoomId"
              :items="rooms"
              item-title="name"
              item-value="id"
              label="Room context (for zone pickers)"
              density="compact"
              clearable
              hide-details
              class="mb-3"
            />
            <v-switch
              v-model="routineEdit.is_enabled"
              label="Enabled"
              density="compact"
              hide-details
              class="mb-3"
            />

            <v-expansion-panels variant="accordion" flat>
              <v-expansion-panel>
                <v-expansion-panel-title class="text-caption text-medium-emphasis pa-0">
                  Language &amp; Voice overrides
                </v-expansion-panel-title>
                <v-expansion-panel-text class="pa-0">
                  <v-text-field
                    v-model="routineEdit.language_override"
                    label="Language"
                    density="compact"
                    hide-details
                    :placeholder="'inherit (ta-IN)'"
                    class="mb-2"
                  />
                  <v-text-field
                    v-model="routineEdit.voice_override"
                    label="Voice"
                    density="compact"
                    hide-details
                    :placeholder="'inherit'"
                    class="mb-2"
                  />
                  <v-textarea
                    v-model="routineEdit.system_instruction_override"
                    label="System instruction override"
                    rows="2"
                    density="compact"
                    hide-details
                    :placeholder="'inherit global instruction'"
                  />
                </v-expansion-panel-text>
              </v-expansion-panel>
              <v-expansion-panel>
                <v-expansion-panel-title class="text-caption text-medium-emphasis pa-0">
                  Policy overrides
                </v-expansion-panel-title>
                <v-expansion-panel-text class="pa-0">
                  <v-row class="mt-0">
                    <v-col cols="6">
                      <v-text-field
                        v-model.number="routineEdit.step_timeout_s_override"
                        label="Step timeout (s)"
                        type="number"
                        density="compact"
                        hide-details
                        placeholder="300"
                      />
                    </v-col>
                    <v-col cols="6">
                      <v-text-field
                        v-model.number="routineEdit.max_step_attempts_override"
                        label="Max attempts"
                        type="number"
                        density="compact"
                        hide-details
                        placeholder="3"
                      />
                    </v-col>
                    <v-col cols="6">
                      <v-text-field
                        v-model.number="routineEdit.resume_grace_s_override"
                        label="Resume grace (s)"
                        type="number"
                        density="compact"
                        hide-details
                        placeholder="600"
                      />
                    </v-col>
                    <v-col cols="6">
                      <v-select
                        v-model="routineEdit.rephrase_via_override"
                        :items="['agent', 'llm']"
                        label="Rephrase via"
                        density="compact"
                        hide-details
                        clearable
                        placeholder="agent"
                      />
                    </v-col>
                  </v-row>
                </v-expansion-panel-text>
              </v-expansion-panel>
            </v-expansion-panels>

            <v-btn
              class="mt-4"
              variant="tonal"
              color="primary"
              block
              :loading="state.saving"
              @click="saveRoutineSettings"
            >
              Save Settings
            </v-btn>
          </v-card-text>
          <v-card-text v-else>
            <v-skeleton-loader type="article" />
          </v-card-text>
        </v-card>
      </v-col>

      <!-- Right: step list -->
      <v-col cols="12" md="8">
        <div v-if="state.loading" class="pa-4 text-center">
          <v-progress-circular indeterminate color="primary" />
        </div>
        <template v-else>
          <RoutineStepCard
            v-for="(step, idx) in state.steps"
            :key="step.id ?? 'new-' + idx"
            :step="step"
            :is-first="idx === 0"
            :is-last="idx === state.steps.length - 1"
            :room-id="routineRoomId"
            :inherited-timeout="state.routine?.step_timeout_s_override ?? null"
            :inherited-max-attempts="state.routine?.max_step_attempts_override ?? null"
            @update="actions.updateStep(idx, $event)"
            @remove="removeStep(idx)"
            @move-up="actions.moveStep(idx, idx - 1)"
            @move-down="actions.moveStep(idx, idx + 1)"
          />

          <v-btn
            variant="tonal"
            color="primary"
            prepend-icon="mdi-plus"
            block
            class="mt-2"
            @click="actions.addStep()"
          >
            Add Step
          </v-btn>

          <div
            v-if="state.steps.length === 0"
            class="pa-6 text-center text-medium-emphasis"
          >
            No steps yet. Click "Add Step" to begin.
          </div>
        </template>
      </v-col>
    </v-row>

    <!-- Confirm delete step dialog -->
    <v-dialog v-model="confirmDialog" max-width="400" persistent>
      <v-card rounded="xl">
        <v-card-title>Remove step?</v-card-title>
        <v-card-text>{{ confirmText }}</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="onCancel">Cancel</v-btn>
          <v-btn color="error" variant="flat" @click="onConfirm">Remove</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, watch, onMounted } from "vue";
import { useRoutineBuilder } from "@/composables/useRoutineBuilder.js";
import { useConfirm } from "@/composables/useConfirm.js";
import { api } from "@/services/api.js";
import RoutineStepCard from "@/components/routines/RoutineStepCard.vue";

const props = defineProps({
  id: { type: String, required: true },
});

const { state, actions } = useRoutineBuilder();
const { confirmDialog, confirmText, require: confirmRequire, onConfirm, onCancel } = useConfirm();

const rooms = ref([]);

async function fetchRooms() {
  try {
    const res = await api.getRooms();
    rooms.value = res.items ?? res;
  } catch {
    rooms.value = [];
  }
}

const routineEdit = reactive({
  name: "",
  is_enabled: true,
  language_override: null,
  voice_override: null,
  system_instruction_override: null,
  step_timeout_s_override: null,
  max_step_attempts_override: null,
  resume_grace_s_override: null,
  rephrase_via_override: null,
});

// A routine doesn't store room_id directly; zone picker will be disabled if no room
const routineRoomId = ref(null);

watch(
  () => state.routine,
  (r) => {
    if (!r) return;
    Object.assign(routineEdit, {
      name: r.name,
      is_enabled: r.is_enabled,
      language_override: r.language_override ?? null,
      voice_override: r.voice_override ?? null,
      system_instruction_override: r.system_instruction_override ?? null,
      step_timeout_s_override: r.step_timeout_s_override ?? null,
      max_step_attempts_override: r.max_step_attempts_override ?? null,
      resume_grace_s_override: r.resume_grace_s_override ?? null,
      rephrase_via_override: r.rephrase_via_override ?? null,
    });
  },
);

async function saveRoutineSettings() {
  await actions.saveRoutine({ ...routineEdit });
}

async function removeStep(idx) {
  const ok = await confirmRequire(`Remove step ${idx + 1}? This will re-number all following steps.`);
  if (!ok) return;
  actions.removeStep(idx);
}

async function runTest() {
  const session = await actions.testRun();
  if (session) {
    // noop - notify already shown by composable
  }
}

onMounted(() => {
  actions.load(props.id);
  fetchRooms();
});
</script>
