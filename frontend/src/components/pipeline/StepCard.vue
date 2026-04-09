<template>
  <v-card
    :variant="step.enabled ? 'elevated' : 'outlined'"
    :class="{ 'opacity-50': !step.enabled }"
    density="compact"
  >
    <v-card-text class="d-flex align-center py-2 gap-1">
      <!-- Step number badge -->
      <v-chip size="x-small" variant="tonal" color="primary" class="me-2 flex-shrink-0">
        {{ index + 1 }}
      </v-chip>

      <!-- Step info -->
      <div class="flex-grow-1 min-width-0">
        <div class="d-flex align-center">
          <div class="text-subtitle-2 font-weight-bold">{{ humanize(step.step_type) }}</div>
          <v-tooltip v-if="templateTokens.length" location="top">
            <template #activator="{ props: tipProps }">
              <v-chip
                v-bind="tipProps"
                size="x-small"
                variant="tonal"
                color="info"
                class="ml-2 cc-token-chip"
              >
                <v-icon start size="10">mdi-code-braces</v-icon>
                {{ templateTokens.length }}
              </v-chip>
            </template>
            <div class="text-caption">Templated values:</div>
            <div v-for="t in templateTokens" :key="t" class="text-caption">{{ t }}</div>
          </v-tooltip>
        </div>
        <div v-if="step.label" class="text-caption text-grey">{{ step.label }}</div>
        <div class="text-caption text-grey-darken-1 text-truncate">{{ configSummary }}</div>
      </div>

      <!-- Reorder buttons -->
      <div class="d-flex flex-column" style="gap:0">
        <v-btn
          icon="mdi-chevron-up"
          size="x-small"
          variant="text"
          :disabled="index === 0"
          style="height:18px; min-width:28px"
          @click.stop="$emit('moveup')"
        />
        <v-btn
          icon="mdi-chevron-down"
          size="x-small"
          variant="text"
          :disabled="index === total - 1"
          style="height:18px; min-width:28px"
          @click.stop="$emit('movedown')"
        />
      </div>

      <v-divider vertical class="mx-1" />

      <!-- Action buttons -->
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
  index: { type: Number, required: true },
  total: { type: Number, required: true },
});

defineEmits(["edit", "delete", "toggle", "moveup", "movedown"]);

const STEP_LABELS = {
  activity_detection: "Record Activity",
  verification: "Verify Activity",
  person_identification: "Person Identification",
};

function humanize(type) {
  if (!type) return "";
  if (STEP_LABELS[type]) return STEP_LABELS[type];
  return type
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

const configSummary = computed(() => {
  const cfg = props.step.config_json;
  if (!cfg || typeof cfg !== "object") return "";

  const parts = [];

  if (cfg.model_id) parts.push(`model: ${cfg.model_id}`);
  if (cfg.output_key) parts.push(`→ ${cfg.output_key}`);
  if (cfg.prompt) {
    const trimmed = cfg.prompt.length > 60 ? cfg.prompt.slice(0, 60) + "..." : cfg.prompt;
    parts.push(trimmed);
  }
  if (cfg.minutes != null) parts.push(`wait: ${cfg.minutes}min`);
  if (cfg.target_language) parts.push(`lang: ${cfg.target_language}`);
  if (cfg.domain) parts.push(`${cfg.domain}.${cfg.service || "*"}`);
  if (cfg.entity_id) parts.push(cfg.entity_id);
  if (cfg.alert_level) parts.push(`level: ${cfg.alert_level}`);
  if (cfg.expression) {
    const trimmed = cfg.expression.length > 50 ? cfg.expression.slice(0, 50) + "..." : cfg.expression;
    parts.push(trimmed);
  }
  if (cfg.min_confidence != null) parts.push(`confidence >= ${cfg.min_confidence}`);
  if (cfg.target_persons?.length) parts.push(`persons: ${cfg.target_persons.join(", ")}`);
  if (cfg.activities_of_interest?.length) parts.push(`activities: ${cfg.activities_of_interest.join(", ")}`);
  if (cfg.source_key) parts.push(`source: ${cfg.source_key} → ${cfg.activities_path || "activities"}`);
  if (cfg.conditions?.length) {
    parts.push(`${cfg.conditions.length} condition${cfg.conditions.length > 1 ? "s" : ""} (${cfg.match_mode || "all"})`);
  }
  if (cfg.re_notify_if_failed) parts.push(`re-notify: ${cfg.re_notify_delay_minutes || 5}min`);
  if (cfg.response_format && cfg.response_format !== "default") parts.push(`format: ${cfg.response_format}`);

  return parts.join(" | ") || "No configuration";
});

// Detect template tokens used in this step's config.
// - Most steps use {{key}} (handled by backend/core/template.py).
// - Notification steps use {key} (Python .format()).
const templateTokens = computed(() => {
  const cfg = props.step.config_json;
  if (!cfg || typeof cfg !== "object") return [];
  const fields = [
    cfg.prompt,
    cfg.expression,
    cfg.system_prompt,
    cfg.message_template,
    cfg.title_template,
    cfg.url_template,
    cfg.body_template,
  ].filter((v) => typeof v === "string" && v.length);
  if (!fields.length) return [];
  const tokens = new Set();
  const isNotification = props.step.step_type === "notification";
  const re = isNotification
    ? /\{([\w][\w.]*)\}/g
    : /\{\{\s*([\w][\w.]*)\s*\}\}/g;
  for (const text of fields) {
    let m;
    while ((m = re.exec(text)) !== null) tokens.add(m[1]);
  }
  return Array.from(tokens);
});
</script>

<style scoped>
.cc-token-chip {
  font-family: "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace;
}
</style>
