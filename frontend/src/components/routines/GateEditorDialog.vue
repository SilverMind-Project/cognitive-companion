<template>
  <AppDialog
    :model-value="modelValue"
    size="xl"
    icon="mdi-eye-outline"
    label="Vision Confirm"
    title="Edit Vision Logic"
    confirm-label="Done"
    @update:model-value="$emit('update:modelValue', $event)"
    @confirm="confirm"
  >
    <div v-if="!ruleId" class="pa-6 text-center text-medium-emphasis">
      <v-icon size="40" class="mb-2">mdi-sitemap-outline</v-icon>
      <div>Choose a preset first to create the gate graph, then edit it here.</div>
    </div>

    <template v-else>
      <PipelineCanvas :rule-id="ruleId" mode="gate" />

      <v-divider class="my-2" />

      <!-- Preview / test-run (VG08): run the cascade once and show the verdict. -->
      <div class="pa-4">
        <div class="d-flex align-center mb-3">
          <v-icon size="small" class="mr-2">mdi-play-circle-outline</v-icon>
          <span class="text-subtitle-2">Preview this gate</span>
        </div>
        <div class="d-flex flex-wrap align-center ga-3 mb-3">
          <v-text-field
            v-model="previewPersonId"
            label="Person (optional)"
            density="compact"
            hide-details
            style="max-width: 220px"
          />
          <v-select
            v-model="previewProfile"
            :items="profileItems"
            label="Profile"
            density="compact"
            hide-details
            style="max-width: 160px"
          />
          <v-btn
            color="primary"
            variant="flat"
            :loading="previewLoading"
            prepend-icon="mdi-play"
            @click="runPreview"
          >
            Run preview
          </v-btn>
        </div>

        <v-alert
          v-if="verdict"
          :type="verdict.complete ? 'success' : 'info'"
          variant="tonal"
          density="compact"
        >
          <div class="font-weight-medium">
            {{ verdict.complete ? "Complete" : "Not complete" }}
            ({{ Math.round(verdict.confidence * 100) }}% confidence)
          </div>
          <div class="text-body-2">{{ verdict.reason }}</div>
          <div class="text-caption text-medium-emphasis mt-1">
            {{ verdict.cost?.model_calls ?? 0 }} model call(s),
            {{ verdict.cost?.frames ?? 0 }} frame(s), {{ verdict.cost?.latency_ms ?? 0 }} ms,
            profile: {{ verdict.profile }}
          </div>
        </v-alert>
      </div>
    </template>
  </AppDialog>
</template>

<script setup>
import { computed, ref } from "vue";
import AppDialog from "@/components/common/AppDialog.vue";
import PipelineCanvas from "@/components/pipeline/PipelineCanvas.vue";
import { api } from "@/services/api.js";
import { useNotify } from "@/composables/useNotify.js";

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  gate: { type: Object, default: () => ({}) },
});

const emit = defineEmits(["update:modelValue", "save", "close"]);
const { notify } = useNotify();

const ruleId = computed(() => props.gate?.vision?.gate_graph_rule_id ?? null);

const profileItems = [
  { title: "Confirm (heavy)", value: "confirm" },
  { title: "Watch (cheap)", value: "watch" },
];
const previewPersonId = ref("");
const previewProfile = ref("confirm");
const previewLoading = ref(false);
const verdict = ref(null);

async function runPreview() {
  if (!ruleId.value) return;
  previewLoading.value = true;
  try {
    verdict.value = await api.testRunGateGraph(ruleId.value, {
      person_id: previewPersonId.value || null,
      profile: previewProfile.value,
    });
  } catch (error) {
    notify.error(`Preview failed: ${error.message || error}`);
  } finally {
    previewLoading.value = false;
  }
}

function confirm() {
  emit("save", props.gate);
  emit("update:modelValue", false);
}
</script>
