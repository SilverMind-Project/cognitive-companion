<template>
  <div>
    <v-timeline side="end" density="compact">
      <v-timeline-item
        v-for="(step, index) in steps"
        :key="step.id"
        :icon="stepIcon(step.step_type)"
        :dot-color="step.enabled ? 'primary' : 'grey'"
        size="small"
      >
        <StepCard
          :step="step"
          :draggable="true"
          @edit="openConfig(step)"
          @delete="removeStep(step.id)"
          @toggle="toggleStep(step)"
          @dragstart="onDragStart(index, $event)"
          @dragover.prevent
          @drop="onDrop(index)"
        />
      </v-timeline-item>
    </v-timeline>

    <div v-if="!steps.length" class="text-center text-grey py-8">
      <v-icon size="48" color="grey-lighten-1" class="mb-2">mdi-pipe-disconnected</v-icon>
      <div class="text-body-1">No pipeline steps yet</div>
      <div class="text-caption">Add your first step to get started</div>
    </div>

    <div class="text-center mt-4">
      <v-btn color="primary" variant="tonal" prepend-icon="mdi-plus" @click="paletteOpen = true">
        Add Step
      </v-btn>
    </div>

    <StepPalette v-model="paletteOpen" @select="addStep" />
    <StepConfigDialog v-model="configOpen" :step="editingStep" @save="saveStepConfig" />
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { api } from "../../services/api.js";
import StepCard from "./StepCard.vue";
import StepPalette from "./StepPalette.vue";
import StepConfigDialog from "./StepConfigDialog.vue";

const props = defineProps({
  ruleId: { type: Number, required: true },
});

const emit = defineEmits(["updated"]);

const steps = ref([]);
const paletteOpen = ref(false);
const configOpen = ref(false);
const editingStep = ref(null);
const dragIndex = ref(-1);

const STEP_ICONS = {
  person_identification: "mdi-face-recognition",
  vision_analysis: "mdi-eye",
  logic_reasoning: "mdi-head-cog",
  translation: "mdi-translate",
  notification: "mdi-bell",
  ha_action: "mdi-home-automation",
  activity_detection: "mdi-run",
  wait: "mdi-timer-sand",
  condition: "mdi-help-circle",
  verification: "mdi-check-decagram",
};

function stepIcon(type) {
  return STEP_ICONS[type] || "mdi-circle-outline";
}

async function loadSteps() {
  try {
    steps.value = await api.getRuleSteps(props.ruleId);
  } catch {
    steps.value = [];
  }
}

async function addStep(stepType) {
  try {
    await api.addRuleStep(props.ruleId, {
      step_type: stepType,
      order: steps.value.length,
      enabled: true,
      config_json: {},
    });
    await loadSteps();
    emit("updated");
  } catch (e) {
    console.error("Failed to add step:", e);
  }
}

async function removeStep(stepId) {
  try {
    await api.deleteRuleStep(props.ruleId, stepId);
    await loadSteps();
    emit("updated");
  } catch (e) {
    console.error("Failed to remove step:", e);
  }
}

async function toggleStep(step) {
  try {
    await api.updateRuleStep(props.ruleId, step.id, {
      ...step,
      enabled: !step.enabled,
    });
    await loadSteps();
    emit("updated");
  } catch (e) {
    console.error("Failed to toggle step:", e);
  }
}

function openConfig(step) {
  editingStep.value = { ...step };
  configOpen.value = true;
}

async function saveStepConfig(data) {
  if (!editingStep.value) return;
  try {
    await api.updateRuleStep(props.ruleId, editingStep.value.id, {
      ...editingStep.value,
      label: data.label,
      config_json: data.config_json,
    });
    editingStep.value = null;
    await loadSteps();
    emit("updated");
  } catch (e) {
    console.error("Failed to save step config:", e);
  }
}

function onDragStart(index, event) {
  dragIndex.value = index;
  event.dataTransfer.effectAllowed = "move";
}

async function onDrop(targetIndex) {
  const fromIndex = dragIndex.value;
  if (fromIndex < 0 || fromIndex === targetIndex) return;

  const moved = steps.value.splice(fromIndex, 1)[0];
  steps.value.splice(targetIndex, 0, moved);

  const orderedIds = steps.value.map((s) => s.id);
  try {
    await api.reorderRuleSteps(props.ruleId, orderedIds);
    await loadSteps();
    emit("updated");
  } catch (e) {
    console.error("Failed to reorder steps:", e);
    await loadSteps();
  } finally {
    dragIndex.value = -1;
  }
}

onMounted(loadSteps);
</script>
