<template>
  <div>
    <v-timeline side="end" density="compact" class="cc-pipeline-timeline">
      <v-timeline-item
        v-for="(step, index) in steps"
        :key="step.id"
        :icon="stepIcon(step.step_type)"
        :dot-color="step.enabled ? stepDotColor(step.step_type) : 'grey'"
        size="small"
        fill-dot
      >
        <div
          class="cc-step-drop-zone"
          :class="{
            'cc-step-dragging': dragSourceIndex === index,
          }"
          @dragover="onDragOver($event, index)"
          @drop="onDrop($event)"
          @dragend="onDragEnd"
        >
          <StepCard
            :step="step"
            :index="index"
            :total="steps.length"
            @edit="openConfig(step)"
            @delete="removeStep(step.id)"
            @toggle="toggleStep(step)"
            @moveup="moveStep(index, index - 1)"
            @movedown="moveStep(index, index + 1)"
            @dragstart="onDragStart($event)"
          />
        </div>
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
    <StepConfigDialog v-model="configOpen" :step="editingStep" :all-steps="steps" @save="saveStepConfig" />
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
const dragSourceIndex = ref(null);
let dragOriginalOrder = null;

const STEP_META = {
  person_identification:  { icon: "mdi-face-recognition",          color: "indigo" },
  scene_analysis:         { icon: "mdi-image-search",               color: "teal" },
  image_crop:             { icon: "mdi-crop",                       color: "teal" },
  object_trend_analysis:  { icon: "mdi-chart-line",                 color: "teal" },
  semantic_memory_query:  { icon: "mdi-database-search-outline",    color: "teal" },
  semantic_memory_write:  { icon: "mdi-database-plus-outline",      color: "indigo" },
  llm_call:               { icon: "mdi-brain",                      color: "purple" },
  condition:              { icon: "mdi-help-circle-outline",        color: "blue-grey" },
  verification:           { icon: "mdi-check-decagram",             color: "green" },
  activity_detection:     { icon: "mdi-database-plus",              color: "indigo" },
  activity_session_start: { icon: "mdi-play-circle-outline",        color: "green" },
  activity_session_end:   { icon: "mdi-stop-circle-outline",        color: "red" },
  notification:           { icon: "mdi-bell-outline",               color: "orange" },
  ha_action:              { icon: "mdi-home-automation",            color: "blue" },
  daily_report:           { icon: "mdi-file-chart-outline",         color: "indigo" },
  interactive_prompt:     { icon: "mdi-forum-outline",              color: "cyan" },
  wait:                   { icon: "mdi-timer-sand",                 color: "amber" },
};

function stepIcon(type) {
  return STEP_META[type]?.icon || "mdi-circle-outline";
}

function stepDotColor(type) {
  return STEP_META[type]?.color || "primary";
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

function reorderLocal(fromIndex, toIndex) {
  if (toIndex < 0 || toIndex >= steps.value.length || fromIndex === toIndex) return;
  const reordered = [...steps.value];
  const [moved] = reordered.splice(fromIndex, 1);
  reordered.splice(toIndex, 0, moved);
  steps.value = reordered;
}

async function persistOrder() {
  try {
    await api.reorderRuleSteps(props.ruleId, steps.value.map((s) => s.id));
    emit("updated");
  } catch (e) {
    console.error("Failed to reorder steps:", e);
    await loadSteps();
  }
}

async function moveStep(fromIndex, toIndex) {
  if (toIndex < 0 || toIndex >= steps.value.length) return;
  reorderLocal(fromIndex, toIndex);
  await persistOrder();
}

function onDragStart(index) {
  dragSourceIndex.value = index;
  dragOriginalOrder = [...steps.value];
}

function onDragOver(event, index) {
  event.preventDefault();
  if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
  const src = dragSourceIndex.value;
  if (src === null || src === index) return;
  dragSourceIndex.value = index;
  requestAnimationFrame(() => reorderLocal(src, index));
}

function onDrop(event) {
  event.preventDefault();
  dragSourceIndex.value = null;
  dragOriginalOrder = null;
  persistOrder();
}

function onDragEnd() {
  if (dragSourceIndex.value !== null && dragOriginalOrder) {
    steps.value = dragOriginalOrder;
  }
  dragSourceIndex.value = null;
  dragOriginalOrder = null;
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

onMounted(loadSteps);
</script>

<style scoped>
.cc-pipeline-timeline {
  --v-timeline-item-padding: 8px;
}
.cc-pipeline-timeline :deep(.v-timeline-item__body) {
  padding-bottom: 12px;
  width: 100%;
  min-width: 0;
}
.cc-step-drop-zone {
  border-radius: var(--cc-radius-lg);
  outline: none;
}
.cc-step-dragging {
  opacity: 0.4;
}
</style>
