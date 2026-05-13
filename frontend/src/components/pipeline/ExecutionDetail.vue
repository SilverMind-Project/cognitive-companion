<template>
  <v-row>
    <!-- Left: step timeline -->
    <v-col cols="12" md="5" lg="4">
      <v-card variant="flat">
        <v-card-title class="text-subtitle-1 d-flex align-center">
          <v-icon :icon="statusIcon" :color="statusColor" class="mr-2" />
          {{ execution.rule_name }}
          <v-spacer />
          <v-chip v-if="execution.status" :color="statusColor" size="small" variant="tonal">
            {{ execution.status }}
          </v-chip>
        </v-card-title>
        <v-card-subtitle v-if="execution.trigger_summary">
          {{ execution.trigger_summary }}
        </v-card-subtitle>

        <v-card-text>
          <v-timeline density="compact" side="end" truncate-line="both">
            <v-timeline-item
              v-for="(step, idx) in execution.timeline"
              :key="idx"
              :dot-color="stepStatusColor(step.status)"
              :icon="step.icon || 'mdi-cog'"
              size="x-small"
              :class="{ 'step-row': true, 'step-selected': selectedIndex === idx }"
              @click="selectedIndex = idx"
            >
              <div class="step-label">{{ step.label }}</div>
              <div class="text-caption text-medium-emphasis">
                {{ step.step_type }}
                <template v-if="step.elapsed_seconds != null">
                  &middot; {{ step.elapsed_seconds.toFixed(1) }}s
                </template>
              </div>
              <v-chip
                :color="stepStatusColor(step.status)"
                size="x-small"
                variant="tonal"
                class="mt-1"
              >
                {{ step.status }}
              </v-chip>
            </v-timeline-item>
          </v-timeline>
        </v-card-text>
      </v-card>
    </v-col>

    <!-- Right: step detail tabs -->
    <v-col cols="12" md="7" lg="8">
      <v-card v-if="selectedStep" variant="flat">
        <v-card-title class="text-subtitle-1 d-flex align-center">
          <v-icon :icon="selectedStep.icon || 'mdi-cog'" class="mr-2" />
          {{ selectedStep.label }}
          <v-spacer />
          <v-btn
            v-if="live && execution.can_cancel"
            icon="mdi-stop-circle"
            variant="text"
            color="error"
            size="small"
            @click="$emit('cancel')"
          />
          <v-btn
            v-if="execution.can_rerun"
            icon="mdi-replay"
            variant="text"
            size="small"
            @click="$emit('rerun')"
          />
        </v-card-title>
        <v-tabs v-model="detailTab" density="compact">
          <v-tab value="inputs">Inputs</v-tab>
          <v-tab value="outputs">Outputs</v-tab>
          <v-tab v-if="selectedStep.logs?.length" value="logs">Logs</v-tab>
          <v-tab value="raw">Raw</v-tab>
        </v-tabs>
        <v-card-text>
          <v-window v-model="detailTab">
            <v-window-item value="inputs">
              <pre v-if="selectedStep.resolved_config" class="json-block">{{ jsonPretty(selectedStep.resolved_config) }}</pre>
              <p v-else class="text-medium-emphasis text-caption">No resolved config recorded.</p>
            </v-window-item>
            <v-window-item value="outputs">
              <pre v-if="selectedStep.outputs" class="json-block">{{ jsonPretty(selectedStep.outputs) }}</pre>
              <p v-else class="text-medium-emphasis text-caption">No output data.</p>
            </v-window-item>
            <v-window-item v-if="selectedStep.logs?.length" value="logs">
              <div v-for="(line, i) in selectedStep.logs" :key="i" class="log-line text-caption font-monospace">
                {{ line }}
              </div>
            </v-window-item>
            <v-window-item value="raw">
              <pre class="json-block">{{ jsonPretty(selectedStep) }}</pre>
            </v-window-item>
          </v-window>
        </v-card-text>
      </v-card>

      <!-- Execution-level info (no step selected) -->
      <v-card v-else variant="flat">
        <v-card-text>
          <div class="text-body-2">
            <div v-if="execution.started_at">Started: {{ formatDateTime(execution.started_at) }}</div>
            <div v-if="execution.completed_at">Completed: {{ formatDateTime(execution.completed_at) }}</div>
            <div v-if="execution.error" class="text-error mt-2">{{ execution.error }}</div>
          </div>
        </v-card-text>
      </v-card>
    </v-col>
  </v-row>
</template>

<script setup>
import { ref, computed } from "vue";
import { formatDateTime } from "../../services/timezone.js";

const props = defineProps({
  execution: { type: Object, required: true },
  live: { type: Boolean, default: false },
});

defineEmits(["cancel", "rerun"]);

const selectedIndex = ref(0);
const detailTab = ref("outputs");

const selectedStep = computed(() => {
  const tl = props.execution.timeline || [];
  if (tl.length === 0) return null;
  return tl[selectedIndex.value] || null;
});

const statusColor = computed(() => stepStatusColor(props.execution.status));

function stepStatusColor(status) {
  switch (status) {
    case "success": return "success";
    case "failed": return "error";
    case "skipped": return "warning";
    case "in_progress": return "primary";
    case "cancelled": return "grey";
    default: return "grey";
  }
}

const statusIcon = computed(() => {
  switch (props.execution.status) {
    case "running": return "mdi-play-circle";
    case "waiting": return "mdi-clock-outline";
    case "completed": return "mdi-check-circle";
    case "failed": return "mdi-alert-circle";
    case "cancelled": return "mdi-cancel";
    default: return "mdi-help-circle";
  }
});

function jsonPretty(obj) {
  try {
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(obj);
  }
}
</script>

<style scoped>
.json-block {
  font-family: monospace;
  font-size: 0.8rem;
  white-space: pre-wrap;
  word-break: break-all;
  background: rgba(var(--v-theme-on-surface), 0.04);
  padding: 8px;
  border-radius: 4px;
  max-height: 400px;
  overflow-y: auto;
}

.step-label {
  font-weight: 500;
  font-size: 0.875rem;
}

.log-line {
  padding: 2px 0;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.06);
}

.step-row {
  cursor: pointer;
}

.step-selected {
  background: rgba(var(--v-theme-primary), 0.08);
  border-radius: 4px;
}
</style>
