<template>
  <v-dialog
    :model-value="modelValue"
    max-width="860"
    :fullscreen="$vuetify.display.smAndDown"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <v-card class="cc-glass step-palette-card d-flex flex-column">
      <DialogHeader
        icon="mdi-puzzle-plus"
        label="Add Pipeline Step"
        :title="activeGroup?.name ?? 'Steps'"
        @close="$emit('update:modelValue', false)"
      />

      <div v-if="loading" class="d-flex align-center justify-center flex-grow-1 py-12">
        <v-progress-circular indeterminate color="primary" />
      </div>

      <div v-else class="step-palette-body d-flex flex-grow-1 overflow-hidden">
        <!-- Left vertical tabs, one per category -->
        <v-tabs
          v-model="activeCategory"
          direction="vertical"
          color="primary"
          class="step-palette-tabs flex-shrink-0"
        >
          <v-tab
            v-for="group in groups"
            :key="group.category"
            :value="group.category"
            class="justify-start"
            :prepend-icon="CATEGORY_ICONS[group.category]"
          >
            {{ group.name }}
          </v-tab>
        </v-tabs>

        <v-divider vertical />

        <!-- Step grid for the active category -->
        <div class="step-palette-content flex-grow-1 pa-5 overflow-y-auto">
          <v-window v-model="activeCategory">
            <v-window-item
              v-for="group in groups"
              :key="group.category"
              :value="group.category"
            >
              <div class="step-grid">
                <div v-for="st in group.types" :key="st.type">
                  <v-card
                    class="pa-4 text-center cursor-pointer step-type-card d-flex flex-column align-center justify-center"
                    rounded="lg"
                    hover
                    :class="st.deprecated ? 'step-type-card--deprecated' : ''"
                    @click="select(st.type)"
                  >
                    <v-icon
                      size="32"
                      :color="st.deprecated ? undefined : 'primary'"
                      class="mb-2"
                    >{{ st.icon }}</v-icon>
                    <div
                      class="text-body-2 font-weight-medium"
                      :class="st.deprecated ? 'text-decoration-line-through text-medium-emphasis' : ''"
                    >{{ st.label }}</div>
                    <v-chip
                      v-if="st.deprecated"
                      size="x-small"
                      color="warning"
                      variant="plain"
                      class="mt-1"
                    >deprecated</v-chip>
                  </v-card>
                </div>
              </div>
            </v-window-item>
          </v-window>
        </div>
      </div>

      <v-divider />
      <v-card-actions class="px-6 py-3">
        <v-icon size="small" color="medium-emphasis" class="mr-1">mdi-cursor-default-click-outline</v-icon>
        <span class="text-caption text-medium-emphasis">Click a step type to insert it into the pipeline</span>
        <v-spacer />
        <v-btn variant="text" @click="$emit('update:modelValue', false)">Cancel</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { api } from "../../services/api.js";
import DialogHeader from "../common/DialogHeader.vue";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  // "rule": full palette excluding gate-only steps (e.g. gate_verdict).
  // "gate": only gate-safe steps, including gate-only steps (gate_verdict).
  mode: { type: String, default: "rule" },
});

const emit = defineEmits(["update:modelValue", "select"]);

const loading = ref(false);
const stepTypes = ref([]);
const activeCategory = ref(null);

const CATEGORY_ORDER = ["perception", "reasoning", "state", "action", "flow"];
const CATEGORY_LABELS = {
  perception: "Perception",
  reasoning: "Reasoning",
  state: "State",
  action: "Action",
  flow: "Flow",
};
const CATEGORY_ICONS = {
  perception: "mdi-eye-outline",
  reasoning: "mdi-brain",
  state: "mdi-database-outline",
  action: "mdi-lightning-bolt-outline",
  flow: "mdi-source-branch",
};

// Metadata-driven palette filter (single source of truth: the gate_safe /
// gate_only flags VG2 added to StepMetadata). Never hardcode a step list.
function isAllowedInMode(st) {
  if (props.mode === "gate") {
    // Gate canvas: only side-effect-free gate-safe steps, and include the
    // gate-only sink (gate_verdict).
    return Boolean(st.gate_safe);
  }
  // Rule canvas: everything except gate-only steps.
  return !st.gate_only;
}

const groups = computed(() => {
  const byCategory = {};
  for (const st of stepTypes.value) {
    if (!isAllowedInMode(st)) continue;
    const cat = st.category || "action";
    if (!byCategory[cat]) byCategory[cat] = [];
    byCategory[cat].push({
      type: st.type_name,
      label: st.display_name,
      icon: st.icon,
      deprecated: st.deprecated || false,
    });
  }
  return CATEGORY_ORDER
    .filter((cat) => byCategory[cat])
    .map((cat) => ({
      category: cat,
      name: CATEGORY_LABELS[cat] || cat,
      types: byCategory[cat],
    }));
});

const activeGroup = computed(() => groups.value.find((g) => g.category === activeCategory.value));

onMounted(async () => {
  loading.value = true;
  try {
    stepTypes.value = await api.getStepTypes();
  } catch {
    stepTypes.value = [
      { type_name: "person_identification", display_name: "Person ID", category: "perception", icon: "mdi-face-recognition", deprecated: false },
      { type_name: "scene_analysis", display_name: "Scene Analysis", category: "perception", icon: "mdi-image-search", deprecated: false },
      { type_name: "object_trend_analysis", display_name: "Room Trend Query", category: "perception", icon: "mdi-chart-line", deprecated: false },
      { type_name: "semantic_memory_query", display_name: "Semantic Memory Query", category: "perception", icon: "mdi-database-search-outline", deprecated: false },
      { type_name: "presence_query", display_name: "Presence Query", category: "perception", icon: "mdi-map-marker-radius", deprecated: false },
      { type_name: "home_state", display_name: "Home State", category: "perception", icon: "mdi-home-variant", deprecated: false },
      { type_name: "llm_call", display_name: "LLM Call", category: "reasoning", icon: "mdi-brain", deprecated: false },
      { type_name: "condition", display_name: "Condition", category: "reasoning", icon: "mdi-help-circle", deprecated: false },
      { type_name: "activity_detection", display_name: "Record Activity", category: "state", icon: "mdi-database-plus", deprecated: false },
      { type_name: "verification", display_name: "Verify Activity", category: "state", icon: "mdi-check-decagram", deprecated: false },
      { type_name: "semantic_memory_write", display_name: "Write to Memory", category: "state", icon: "mdi-database-plus-outline", deprecated: false },
      { type_name: "activity_session_start", display_name: "Start Activity Session", category: "action", icon: "mdi-play", deprecated: false },
      { type_name: "activity_session_end", display_name: "End Activity Session", category: "action", icon: "mdi-stop", deprecated: false },
      { type_name: "notification", display_name: "Notification", category: "action", icon: "mdi-bell", deprecated: false },
      { type_name: "ha_action", display_name: "HA Action", category: "action", icon: "mdi-home-automation", deprecated: false },
      { type_name: "daily_report", display_name: "Daily Report", category: "action", icon: "mdi-file-chart", deprecated: false },
      { type_name: "wait", display_name: "Wait", category: "flow", icon: "mdi-timer-sand", deprecated: false },
    ];
  } finally {
    loading.value = false;
    if (groups.value.length) activeCategory.value = groups.value[0].category;
  }
});

function select(type) {
  emit("select", type);
  emit("update:modelValue", false);
}
</script>

<style scoped>
.step-palette-card {
  height: 70vh;
  max-height: 680px;
  border-radius: 24px;
  overflow: hidden;
}

.step-palette-body {
  min-height: 0;
}

.step-palette-tabs {
  width: 200px;
  background-color: var(--cc-bg-elevated);
  padding-top: 12px;
}

.step-palette-tabs :deep(.v-tab) {
  justify-content: flex-start !important;
  padding-inline: 20px !important;
  border-radius: 0;
  font-weight: 500;
  height: 44px;
}

.step-palette-content {
  min-width: 0;
}

.step-palette-content :deep(.v-window),
.step-palette-content :deep(.v-window__container) {
  overflow: visible !important;
}

.step-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px;
}

.step-type-card {
  height: 100%;
  min-height: 96px;
  transition: transform 0.2s cubic-bezier(0.2, 0, 0, 1), box-shadow 0.2s cubic-bezier(0.2, 0, 0, 1), border-color 0.2s !important;
  cursor: pointer;
}

.step-type-card:hover {
  transform: scale(1.03) translateY(-2px);
  border-color: rgb(var(--v-theme-primary)) !important;
}

.step-type-card--deprecated {
  opacity: 0.55;
}
</style>
