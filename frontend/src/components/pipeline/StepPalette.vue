<template>
  <v-dialog :model-value="modelValue" max-width="600" @update:model-value="$emit('update:modelValue', $event)">
    <v-card>
      <v-card-title class="d-flex align-center">
        <v-icon class="mr-2">mdi-puzzle-plus</v-icon>
        Add Pipeline Step
      </v-card-title>

      <v-card-text>
        <div v-if="loading" class="text-center py-4">
          <v-progress-circular indeterminate color="primary" />
        </div>
        <div v-else v-for="group in groups" :key="group.name" class="mb-4">
          <div class="text-overline text-grey mb-2">{{ group.name }}</div>
          <v-row dense>
            <v-col v-for="st in group.types" :key="st.type" cols="6" sm="4">
              <v-card
                variant="outlined"
                class="pa-3 text-center cursor-pointer step-palette-card"
                rounded="lg"
                hover
                :class="st.deprecated ? 'text-grey' : ''"
                @click="select(st.type)"
              >
                <v-icon size="28" :class="st.deprecated ? 'text-grey' : 'text-primary'" class="mb-1">{{ st.icon }}</v-icon>
                <div class="text-body-2 font-weight-medium" :class="st.deprecated ? 'text-decoration-line-through' : ''">{{ st.label }}</div>
                <v-chip v-if="st.deprecated" size="x-small" color="warning" variant="plain">deprecated</v-chip>
              </v-card>
            </v-col>
          </v-row>
        </div>
      </v-card-text>

      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="$emit('update:modelValue', false)">Cancel</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { api } from "../../services/api.js";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
});

const emit = defineEmits(["update:modelValue", "select"]);

const loading = ref(false);
const stepTypes = ref([]);

// Category display order
const CATEGORY_ORDER = ["perception", "reasoning", "state", "action", "flow"];
const CATEGORY_LABELS = {
  perception: "Perception",
  reasoning: "Reasoning",
  state: "State",
  action: "Action",
  flow: "Flow",
};

const groups = computed(() => {
  const byCategory = {};
  for (const st of stepTypes.value) {
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
      name: CATEGORY_LABELS[cat] || cat,
      types: byCategory[cat],
    }));
});

onMounted(async () => {
  loading.value = true;
  try {
    stepTypes.value = await api.getStepTypes();
  } catch {
    // Fallback to hardcoded types if API unavailable
    stepTypes.value = [
      { type_name: "person_identification", display_name: "Person ID", category: "perception", icon: "mdi-face-recognition", deprecated: false },
      { type_name: "scene_analysis", display_name: "Scene Analysis", category: "perception", icon: "mdi-image-search", deprecated: false },
      { type_name: "object_trend_analysis", display_name: "Object Trend Analysis", category: "perception", icon: "mdi-chart-line", deprecated: false },
      { type_name: "llm_call", display_name: "LLM Call", category: "reasoning", icon: "mdi-brain", deprecated: false },
      { type_name: "condition", display_name: "Condition", category: "reasoning", icon: "mdi-help-circle", deprecated: false },
      { type_name: "activity_detection", display_name: "Record Activity", category: "state", icon: "mdi-database-plus", deprecated: false },
      { type_name: "verification", display_name: "Verify Activity", category: "state", icon: "mdi-check-decagram", deprecated: false },
      { type_name: "activity_session_start", display_name: "Start Activity Session", category: "action", icon: "mdi-play", deprecated: false },
      { type_name: "activity_session_end", display_name: "End Activity Session", category: "action", icon: "mdi-stop", deprecated: false },
      { type_name: "notification", display_name: "Notification", category: "action", icon: "mdi-bell", deprecated: false },
      { type_name: "ha_action", display_name: "HA Action", category: "action", icon: "mdi-home-automation", deprecated: false },
      { type_name: "daily_report", display_name: "Daily Report", category: "action", icon: "mdi-file-chart", deprecated: false },
      { type_name: "wait", display_name: "Wait", category: "flow", icon: "mdi-timer-sand", deprecated: false },
    ];
  } finally {
    loading.value = false;
  }
});

function select(type) {
  emit("select", type);
  emit("update:modelValue", false);
}
</script>

<style scoped>
.step-palette-card {
  transition: border-color 0.15s, box-shadow 0.15s;
}
.step-palette-card:hover {
  border-color: rgb(var(--v-theme-primary));
}
.cursor-pointer {
  cursor: pointer;
}
</style>
