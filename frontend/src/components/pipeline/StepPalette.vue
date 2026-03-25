<template>
  <v-dialog :model-value="modelValue" max-width="600" @update:model-value="$emit('update:modelValue', $event)">
    <v-card rounded="xl">
      <v-card-title class="d-flex align-center">
        <v-icon class="mr-2">mdi-puzzle-plus</v-icon>
        Add Pipeline Step
      </v-card-title>

      <v-card-text>
        <div v-for="group in groups" :key="group.name" class="mb-4">
          <div class="text-overline text-grey mb-2">{{ group.name }}</div>
          <v-row dense>
            <v-col v-for="st in group.types" :key="st.type" cols="6" sm="4">
              <v-card
                variant="outlined"
                class="pa-3 text-center cursor-pointer step-palette-card"
                rounded="lg"
                hover
                @click="select(st.type)"
              >
                <v-icon size="28" color="primary" class="mb-1">{{ st.icon }}</v-icon>
                <div class="text-body-2 font-weight-medium">{{ st.label }}</div>
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
const props = defineProps({
  modelValue: { type: Boolean, default: false },
});

const emit = defineEmits(["update:modelValue", "select"]);

const groups = [
  {
    name: "Perception",
    types: [
      { type: "person_identification", label: "Person ID", icon: "mdi-face-recognition" },
      { type: "vision_analysis", label: "Vision Analysis", icon: "mdi-eye" },
    ],
  },
  {
    name: "Reasoning",
    types: [
      { type: "logic_reasoning", label: "Logic Reasoning", icon: "mdi-head-cog" },
      { type: "condition", label: "Condition", icon: "mdi-help-circle" },
    ],
  },
  {
    name: "State",
    types: [
      { type: "activity_detection", label: "Record Activity", icon: "mdi-database-plus" },
      { type: "verification", label: "Verify Activity", icon: "mdi-check-decagram" },
    ],
  },
  {
    name: "Action",
    types: [
      { type: "notification", label: "Notification", icon: "mdi-bell" },
      { type: "ha_action", label: "HA Action", icon: "mdi-home-automation" },
      { type: "translation", label: "Translation", icon: "mdi-translate" },
    ],
  },
  {
    name: "Flow",
    types: [
      { type: "wait", label: "Wait", icon: "mdi-timer-sand" },
    ],
  },
];

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
