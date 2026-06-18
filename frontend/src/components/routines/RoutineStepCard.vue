<template>
  <v-card class="glass-card mb-3" :class="{ 'step-card--dragging': isDragging }">
    <div class="d-flex align-center px-4 pt-3 pb-1">
      <span class="text-subtitle-2 font-weight-semibold" style="color: var(--cc-text-3)">
        Step {{ step.ord + 1 }}
      </span>
      <v-spacer />
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

    <v-card-text class="pt-0">
      <!-- Prompt template -->
      <v-textarea
        :model-value="step.prompt_template"
        label="Prompt"
        rows="2"
        density="comfortable"
        placeholder="e.g. Please fill the kettle with water from the tap."
        :hint="'Use {{ variable }} for personalization.'"
        persistent-hint
        @update:model-value="update('prompt_template', $event)"
      />

      <!-- Completion gate -->
      <CompletionGateEditor
        :model-value="step.completion_gate"
        :room-id="roomId"
        class="mt-2"
        @update:model-value="update('completion_gate', $event)"
      />

      <!-- Zone + Camera pickers -->
      <v-row class="mt-0">
        <v-col cols="6">
          <ZonePicker
            :model-value="step.zone_id"
            :room-id="roomId"
            label="Zone"
            @update:model-value="update('zone_id', $event)"
          />
        </v-col>
        <v-col cols="6">
          <CameraPicker
            :model-value="step.camera_ids"
            label="Cameras"
            @update:model-value="update('camera_ids', $event)"
          />
        </v-col>
      </v-row>

      <!-- Skip condition (JSON) -->
      <v-textarea
        :model-value="skipConditionText"
        label="Skip condition (JSON, optional)"
        rows="2"
        density="compact"
        hide-details
        class="mt-2 font-monospace"
        placeholder='{"kind": "already_done"}'
        @update:model-value="updateSkipCondition($event)"
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
                  :model-value="step.min_duration_s ?? ''"
                  label="Min duration (s)"
                  type="number"
                  density="compact"
                  hide-details
                  :placeholder="'inherit'"
                  @update:model-value="update('min_duration_s', $event ? parseInt($event) : null)"
                />
              </v-col>
              <v-col cols="4">
                <v-text-field
                  :model-value="step.step_timeout_s_override ?? ''"
                  label="Timeout (s)"
                  type="number"
                  density="compact"
                  hide-details
                  :placeholder="inheritedTimeout ? String(inheritedTimeout) : 'inherit'"
                  @update:model-value="update('step_timeout_s_override', $event ? parseInt($event) : null)"
                />
              </v-col>
              <v-col cols="4">
                <v-text-field
                  :model-value="step.max_step_attempts_override ?? ''"
                  label="Max attempts"
                  type="number"
                  density="compact"
                  hide-details
                  :placeholder="inheritedMaxAttempts ? String(inheritedMaxAttempts) : 'inherit'"
                  @update:model-value="update('max_step_attempts_override', $event ? parseInt($event) : null)"
                />
              </v-col>
            </v-row>
            <v-checkbox
              :model-value="step.is_safety_critical"
              label="Safety critical step"
              density="compact"
              hide-details
              color="error"
              class="mt-1"
              @update:model-value="update('is_safety_critical', $event)"
            />
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>
    </v-card-text>
  </v-card>
</template>

<script setup>
import { computed } from "vue";
import CompletionGateEditor from "./CompletionGateEditor.vue";
import ZonePicker from "./ZonePicker.vue";
import CameraPicker from "./CameraPicker.vue";

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

const skipConditionText = computed(() => {
  if (!props.step.skip_condition) return "";
  try {
    return JSON.stringify(props.step.skip_condition, null, 2);
  } catch {
    return "";
  }
});

function update(field, value) {
  emit("update", { ...props.step, [field]: value });
}

function updateSkipCondition(text) {
  if (!text.trim()) {
    update("skip_condition", null);
    return;
  }
  try {
    update("skip_condition", JSON.parse(text));
  } catch {
    // keep previous value until valid JSON is entered
  }
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
