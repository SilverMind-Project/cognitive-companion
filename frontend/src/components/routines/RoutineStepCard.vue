<template>
  <v-card class="glass-card mb-3" :class="{ 'step-card--dragging': isDragging }">
    <div class="d-flex align-center px-4 pt-3 pb-1">
      <span class="text-subtitle-2 font-weight-semibold" style="color: var(--cc-text-3)">
        Step {{ step.ord + 1 }}
      </span>
      <v-spacer />
      <v-btn icon="mdi-pencil-outline" variant="text" size="small" @click="openEditDialog" />
      <v-btn
        icon="mdi-arrow-up"
        variant="text"
        size="small"
        :disabled="isFirst"
        @click="$emit('move-up')"
      />
      <v-btn
        icon="mdi-arrow-down"
        variant="text"
        size="small"
        :disabled="isLast"
        @click="$emit('move-down')"
      />
      <v-btn
        icon="mdi-delete-outline"
        variant="text"
        size="small"
        color="error"
        @click="$emit('remove')"
      />
    </div>

    <v-card-text class="pt-0 pb-3">
      <div class="text-body-1 font-weight-medium mb-2" style="color: var(--cc-text-1)">
        {{ step.prompt_template || "(No prompt defined)" }}
      </div>

      <div class="d-flex flex-wrap ga-2 text-caption">
        <!-- Completion Gate summary -->
        <span v-if="step.completion_gate" class="cc-badge cc-badge--brand">
          <span class="cc-badge__dot"></span>
          Gates: {{ step.completion_gate.kinds.join(", ") }}
        </span>

        <!-- Room/Zone context -->
        <span v-if="step.zone_id" class="cc-badge cc-badge--info">
          <span class="cc-badge__dot"></span>
          Zone: {{ step.zone_id }}
        </span>

        <!-- Cameras context -->
        <span v-if="step.camera_ids && step.camera_ids.length" class="cc-badge cc-badge--info">
          <span class="cc-badge__dot"></span>
          Cameras: {{ step.camera_ids.join(", ") }}
        </span>

        <!-- Timeout override -->
        <span v-if="step.step_timeout_s_override" class="cc-badge cc-badge--notice">
          <span class="cc-badge__dot"></span>
          Timeout: {{ step.step_timeout_s_override }}s
        </span>

        <!-- Safety Critical badge -->
        <span v-if="step.is_safety_critical" class="cc-badge cc-badge--alert">
          <span class="cc-badge__dot"></span>
          Safety Critical
        </span>
      </div>

      <div class="mt-3">
        <v-btn
          variant="outlined"
          color="primary"
          size="small"
          prepend-icon="mdi-pencil-outline"
          @click="openEditDialog"
        >
          Edit Step
        </v-btn>
      </div>
    </v-card-text>

    <!-- AppDialog Modal for Step Details Editing -->
    <AppDialog
      v-model="editDialogOpen"
      size="lg"
      icon="mdi-pencil-outline"
      :label="`Step ${step.ord + 1}`"
      title="Edit Step Details"
      confirm-label="Apply"
      @confirm="saveEdit"
      @cancel="closeEdit"
    >
      <div class="pa-4">
        <!-- Prompt template -->
        <v-textarea
          v-model="localStep.prompt_template"
          label="Prompt"
          rows="2"
          density="comfortable"
          placeholder="e.g. Please fill the kettle with water from the tap."
          :hint="'Use {{ variable }} for personalization.'"
          persistent-hint
          class="mb-3"
        />

        <!-- Completion gate -->
        <CompletionGateEditor
          v-slot
          v-model="localStep.completion_gate"
          :room-id="roomId"
          class="mt-2"
        />

        <!-- Zone + Camera pickers -->
        <v-row class="mt-0">
          <v-col cols="6">
            <ZonePicker v-model="localStep.zone_id" :room-id="roomId" label="Zone" />
          </v-col>
          <v-col cols="6">
            <CameraPicker
              v-model="localStep.camera_ids"
              label="Cameras for vision + selection"
              hint="Used for the vision check and camera selection. Leave empty to auto-select from where she is."
            />
          </v-col>
        </v-row>

        <!-- Skip condition (JSON) -->
        <v-textarea
          v-model="localSkipConditionText"
          label="Skip condition (JSON, optional)"
          rows="2"
          density="compact"
          hide-details
          class="mt-2 font-monospace"
          placeholder='{"kind": "already_done"}'
        />

        <!-- Override fields -->
        <v-expansion-panels variant="accordion" class="mt-3" flat>
          <v-expansion-panel>
            <v-expansion-panel-title class="text-caption text-medium-emphasis pa-0">
              Per-step overrides
            </v-expansion-panel-title>
            <v-expansion-panel-text class="pa-0">
              <v-row class="mt-1">
                <v-col cols="4">
                  <v-text-field
                    v-model.number="localStep.min_duration_s"
                    label="Min duration (s)"
                    type="number"
                    density="compact"
                    hide-details
                    :placeholder="'inherit'"
                  />
                </v-col>
                <v-col cols="4">
                  <v-text-field
                    v-model.number="localStep.step_timeout_s_override"
                    label="Timeout (s)"
                    type="number"
                    density="compact"
                    hide-details
                    :placeholder="inheritedTimeout ? String(inheritedTimeout) : 'inherit'"
                  />
                </v-col>
                <v-col cols="4">
                  <v-text-field
                    v-model.number="localStep.max_step_attempts_override"
                    label="Max attempts"
                    type="number"
                    density="compact"
                    hide-details
                    :placeholder="inheritedMaxAttempts ? String(inheritedMaxAttempts) : 'inherit'"
                  />
                </v-col>
              </v-row>
              <v-checkbox
                v-model="localStep.is_safety_critical"
                label="Safety critical step"
                density="compact"
                hide-details
                color="error"
                class="mt-1"
              />
            </v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>
      </div>
    </AppDialog>
  </v-card>
</template>

<script setup>
import { ref, watch } from "vue";
import AppDialog from "@/components/common/AppDialog.vue";
import CompletionGateEditor from "./CompletionGateEditor.vue";
import ZonePicker from "./ZonePicker.vue";
import CameraPicker from "./CameraPicker.vue";
import { useNotify } from "@/composables/useNotify.js";

const props = defineProps({
  step: { type: Object, required: true },
  isFirst: { type: Boolean, default: false },
  isLast: { type: Boolean, default: false },
  isDragging: { type: Boolean, default: false },
  roomId: { type: Number, default: null },
  inheritedTimeout: { type: Number, default: null },
  inheritedMaxAttempts: { type: Number, default: null },
});

const emit = defineEmits(["update", "remove", "move-up", "move-down"]);

const { notify } = useNotify();

const editDialogOpen = ref(false);
const localStep = ref(JSON.parse(JSON.stringify(props.step)));
const localSkipConditionText = ref("");

// Sync localStep when props.step changes
watch(
  () => props.step,
  (newStep) => {
    localStep.value = JSON.parse(JSON.stringify(newStep));
  },
  { deep: true },
);

function openEditDialog() {
  localStep.value = JSON.parse(JSON.stringify(props.step));
  localSkipConditionText.value = localStep.value.skip_condition
    ? JSON.stringify(localStep.value.skip_condition, null, 2)
    : "";
  editDialogOpen.value = true;
}

function closeEdit() {
  editDialogOpen.value = false;
}

function saveEdit() {
  // Parse skip condition
  const skipText = localSkipConditionText.value.trim();
  if (!skipText) {
    localStep.value.skip_condition = null;
  } else {
    try {
      localStep.value.skip_condition = JSON.parse(skipText);
    } catch {
      notify.error("Invalid JSON in skip condition. Please correct it.");
      return;
    }
  }

  // Clean empty numbers
  if (localStep.value.min_duration_s === "") {
    localStep.value.min_duration_s = null;
  }
  if (localStep.value.step_timeout_s_override === "") {
    localStep.value.step_timeout_s_override = null;
  }
  if (localStep.value.max_step_attempts_override === "") {
    localStep.value.max_step_attempts_override = null;
  }

  emit("update", { ...localStep.value });
  editDialogOpen.value = false;
}
</script>

<style scoped>
.step-card--dragging {
  opacity: 0.7;
  box-shadow: var(--cc-shadow-md);
}

.font-monospace {
  font-family: var(--cc-font-mono);
}
</style>
