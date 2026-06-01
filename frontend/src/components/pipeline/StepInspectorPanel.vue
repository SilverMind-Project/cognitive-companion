<template>
  <v-card variant="flat" class="cc-step-inspector" data-testid="step-inspector-panel">
    <template v-if="step">
      <v-card-title class="text-subtitle-1 d-flex align-center">
        <v-icon :icon="step.icon || 'mdi-cog'" class="mr-2" />
        <span class="text-truncate">{{ step.label }}</span>
        <v-spacer />
        <v-chip :color="stepStatusColor(step.status)" size="x-small" variant="tonal">
          {{ step.status }}
        </v-chip>
      </v-card-title>

      <v-tabs v-model="detailTab" density="compact">
        <v-tab value="inputs">Inputs</v-tab>
        <v-tab value="outputs">Outputs</v-tab>
        <v-tab v-if="step.logs?.length" value="logs">Logs</v-tab>
        <v-tab value="raw">Raw</v-tab>
      </v-tabs>

      <v-card-text>
        <v-window v-model="detailTab">
          <v-window-item value="inputs">
            <pre v-if="step.resolved_config" class="json-block">{{ jsonPretty(step.resolved_config) }}</pre>
            <p v-else class="text-medium-emphasis text-caption">No resolved config recorded.</p>
          </v-window-item>
          <v-window-item value="outputs">
            <pre v-if="step.outputs" class="json-block">{{ jsonPretty(step.outputs) }}</pre>
            <p v-else class="text-medium-emphasis text-caption">No output data.</p>
          </v-window-item>
          <v-window-item v-if="step.logs?.length" value="logs">
            <div
              v-for="(line, i) in step.logs"
              :key="i"
              class="log-line text-caption font-monospace"
            >
              {{ line }}
            </div>
          </v-window-item>
          <v-window-item value="raw">
            <pre class="json-block">{{ jsonPretty(step) }}</pre>
          </v-window-item>
        </v-window>
      </v-card-text>
    </template>

    <v-card-text v-else class="text-medium-emphasis text-center pa-8">
      Select a step to inspect its inputs, outputs, and logs.
    </v-card-text>
  </v-card>
</template>

<script setup>
import { ref, watch } from "vue";

const props = defineProps({
  step: { type: Object, default: null },
});

const detailTab = ref("outputs");

watch(
  () => props.step?.step_id || props.step?.label,
  () => {
    detailTab.value = "outputs";
  },
);

function stepStatusColor(status) {
  switch (status) {
    case "success":
    case "succeeded":
      return "success";
    case "failed":
      return "error";
    case "skipped":
      return "warning";
    case "in_progress":
    case "running":
      return "primary";
    case "cancelled":
      return "grey";
    default:
      return "grey";
  }
}

function jsonPretty(obj) {
  try {
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(obj);
  }
}
</script>

<style scoped>
.cc-step-inspector {
  min-height: 100%;
}

.json-block {
  max-height: 420px;
  overflow-y: auto;
  padding: 8px;
  border: 1px solid var(--cc-divider);
  border-radius: var(--cc-radius-sm);
  background: var(--cc-surface-2);
  color: var(--cc-text-1);
  font-family: monospace;
  font-size: 0.8rem;
  white-space: pre-wrap;
  word-break: break-word;
}

.log-line {
  padding: 3px 0;
  border-bottom: 1px solid var(--cc-divider);
}
</style>
