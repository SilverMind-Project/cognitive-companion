<template>
  <v-card
    :variant="step.enabled ? 'elevated' : 'outlined'"
    :class="{ 'opacity-50': !step.enabled }"
    density="compact"
    :draggable="draggable"
    @dragstart="$emit('dragstart', $event)"
    @dragover.prevent
    @drop="$emit('drop')"
  >
    <v-card-text class="d-flex align-center py-2">
      <div class="flex-grow-1">
        <div class="text-subtitle-2 font-weight-bold">{{ humanize(step.step_type) }}</div>
        <div v-if="step.label" class="text-caption text-grey">{{ step.label }}</div>
        <div class="text-caption text-grey-darken-1">{{ configSummary }}</div>
      </div>
      <v-btn icon="mdi-pencil" size="x-small" variant="text" @click.stop="$emit('edit')" />
      <v-btn
        :icon="step.enabled ? 'mdi-eye' : 'mdi-eye-off'"
        size="x-small"
        variant="text"
        @click.stop="$emit('toggle')"
      />
      <v-btn icon="mdi-delete" size="x-small" variant="text" color="error" @click.stop="$emit('delete')" />
    </v-card-text>
  </v-card>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  step: { type: Object, required: true },
  draggable: { type: Boolean, default: false },
});

defineEmits(["edit", "delete", "toggle", "dragstart", "drop"]);

function humanize(type) {
  if (!type) return "";
  return type
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

const configSummary = computed(() => {
  const cfg = props.step.config_json;
  if (!cfg || typeof cfg !== "object") return "";

  const parts = [];

  if (cfg.prompt) {
    const trimmed = cfg.prompt.length > 50 ? cfg.prompt.slice(0, 50) + "..." : cfg.prompt;
    parts.push(`prompt: ${trimmed}`);
  }
  if (cfg.minutes != null) {
    parts.push(`minutes: ${cfg.minutes}`);
  }
  if (cfg.target_language) {
    parts.push(`lang: ${cfg.target_language}`);
  }
  if (cfg.domain) {
    parts.push(`${cfg.domain}.${cfg.service || "*"}`);
  }
  if (cfg.entity_id) {
    parts.push(cfg.entity_id);
  }
  if (cfg.alert_level) {
    parts.push(`level: ${cfg.alert_level}`);
  }
  if (cfg.expression) {
    const trimmed = cfg.expression.length > 50 ? cfg.expression.slice(0, 50) + "..." : cfg.expression;
    parts.push(trimmed);
  }
  if (cfg.min_confidence != null) {
    parts.push(`confidence >= ${cfg.min_confidence}`);
  }
  if (cfg.target_persons && cfg.target_persons.length) {
    parts.push(`persons: ${cfg.target_persons.join(", ")}`);
  }
  if (cfg.activities_of_interest && cfg.activities_of_interest.length) {
    parts.push(`activities: ${cfg.activities_of_interest.join(", ")}`);
  }
  // activity_detection (setter) summary
  if (cfg.source_key) {
    parts.push(`source: ${cfg.source_key} → ${cfg.activities_path || "activities"}`);
  }
  // verification conditions summary
  if (cfg.conditions && cfg.conditions.length) {
    parts.push(`${cfg.conditions.length} condition${cfg.conditions.length > 1 ? "s" : ""} (${cfg.match_mode || "all"})`);
  }
  if (cfg.re_notify_if_failed) {
    parts.push(`re-notify: ${cfg.re_notify_delay_minutes || 5}min`);
  }
  // logic_reasoning response format
  if (cfg.response_format && cfg.response_format !== "default") {
    parts.push(`format: ${cfg.response_format}`);
  }

  return parts.join(" | ") || "No configuration";
});
</script>
