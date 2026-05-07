<template>
  <v-card
    :variant="step.enabled ? 'elevated' : 'outlined'"
    :class="{ 'opacity-50': !step.enabled }"
    rounded="lg"
  >
    <v-card-text class="pa-4">
      <!-- Header row -->
      <div class="d-flex align-center gap-3">
        <v-chip size="x-small" variant="tonal" color="primary" class="flex-shrink-0 font-weight-bold step-num-chip">
          {{ index + 1 }}
        </v-chip>

        <div class="flex-grow-1 min-width-0 ml-2">
          <div class="d-flex align-center gap-1 flex-wrap">
            <span class="text-subtitle-2 font-weight-bold">{{ stepDisplayName }}</span>
            <v-tooltip v-if="templateTokens.length" location="top">
              <template #activator="{ props: tipProps }">
                <v-chip
                  v-bind="tipProps"
                  size="x-small"
                  variant="tonal"
                  color="info"
                  class="cc-token-chip"
                >
                  <v-icon start size="10">mdi-code-braces</v-icon>
                  {{ templateTokens.length }}
                </v-chip>
              </template>
              <div class="text-caption font-weight-bold mb-1">Templated values:</div>
              <div v-for="t in templateTokens" :key="t" class="text-caption cc-mono">{{ t }}</div>
            </v-tooltip>
          </div>
          <div v-if="step.label" class="text-caption text-medium-emphasis">{{ step.label }}</div>
        </div>

        <!-- Reorder + actions -->
        <div class="d-flex align-center flex-shrink-0">
          <v-icon
            class="cc-drag-handle flex-shrink-0 mr-1"
            size="16"
            color="grey"
            draggable="true"
            @dragstart="onDragStart"
          >mdi-drag-vertical</v-icon>
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
          <v-divider vertical class="mx-2" />
          <v-btn icon="mdi-pencil" size="x-small" variant="text" @click.stop="$emit('edit')" />
          <v-btn
            :icon="step.enabled ? 'mdi-eye' : 'mdi-eye-off'"
            size="x-small"
            variant="text"
            @click.stop="$emit('toggle')"
          />
          <v-btn icon="mdi-delete" size="x-small" variant="text" color="error" @click.stop="$emit('delete')" />
        </div>
      </div>

      <!-- Detail chips row -->
      <div v-if="detailChips.length" class="d-flex flex-wrap mt-3">
        <template v-for="chip in detailChips" :key="chip.key">
          <v-tooltip v-if="chip.tooltip" location="top" :max-width="320">
            <template #activator="{ props: tipProps }">
              <v-chip
                v-bind="tipProps"
                size="small"
                :color="chip.color || undefined"
                :variant="chip.color ? 'tonal' : 'outlined'"
                :prepend-icon="chip.icon"
                class="cc-detail-chip"
              >
                {{ chip.label }}
              </v-chip>
            </template>
            <span class="cc-mono text-caption">{{ chip.tooltip }}</span>
          </v-tooltip>
          <v-chip
            v-else
            size="small"
            :color="chip.color || undefined"
            :variant="chip.color ? 'tonal' : 'outlined'"
            :prepend-icon="chip.icon"
            class="cc-detail-chip"
          >
            {{ chip.label }}
          </v-chip>
        </template>
      </div>

      <!-- Prompt / expression / template preview -->
      <div v-if="textPreview" class="mt-3 cc-preview-text text-caption text-medium-emphasis">
        {{ textPreview }}
      </div>
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

const emit = defineEmits(["edit", "delete", "toggle", "moveup", "movedown", "dragstart"]);

function onDragStart(event) {
  event.dataTransfer.effectAllowed = "move";
  event.dataTransfer.setData("text/plain", props.index);
  emit("dragstart", props.index);
}

// ── Display names ────────────────────────────────────────────────────────────

const STEP_LABELS = {
  activity_detection: "Record Activity",
  activity_session_start: "Start Activity Session",
  activity_session_end: "End Activity Session",
  condition: "Condition",
  daily_report: "Daily Report",
  ha_action: "HA Action",
  interactive_prompt: "Interactive Prompt",
  llm_call: "LLM Call",
  notification: "Notification",
  object_trend_analysis: "Object Trend Analysis",
  person_identification: "Person Identification",
  scene_analysis: "Scene Analysis",
  semantic_memory_query: "Memory Query",
  semantic_memory_write: "Memory Write",
  tracking_query: "Tracking Query",
  verification: "Verify Activity",
  wait: "Wait",
};

function humanize(type) {
  if (!type) return "";
  if (STEP_LABELS[type]) return STEP_LABELS[type];
  return type
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

const stepDisplayName = computed(() => humanize(props.step.step_type));

// ── Template tokens ───────────────────────────────────────────────────────────

const templateTokens = computed(() => {
  const cfg = props.step.config_json;
  if (!cfg || typeof cfg !== "object") return [];
  const strings = [];
  function collect(obj) {
    if (typeof obj === "string") { strings.push(obj); return; }
    if (obj && typeof obj === "object") Object.values(obj).forEach(collect);
  }
  collect(cfg);
  if (!strings.length) return [];
  const tokens = new Set();
  const re = /\{\{\s*([\w][\w.]*)\s*\}\}/g;
  for (const text of strings) {
    let m;
    while ((m = re.exec(text)) !== null) tokens.add(m[1]);
  }
  return Array.from(tokens);
});

// ── Detail chips ──────────────────────────────────────────────────────────────

const ALERT_COLORS = { emergency: "red", warning: "orange", info: "blue", reminder: "green" };

function truncate(s, n) {
  if (!s) return "";
  return s.length > n ? s.slice(0, n) + "…" : s;
}

const detailChips = computed(() => {
  const cfg = props.step.config_json;
  if (!cfg || typeof cfg !== "object") return [];
  const type = props.step.step_type;
  const chips = [];
  let key = 0;
  const chip = (label, icon, color, tooltip) => chips.push({ key: key++, label, icon, color: color || undefined, tooltip });

  if (type === "llm_call") {
    if (cfg.model_id) {
      const short = truncate(cfg.model_id, 28);
      chip(short, "mdi-chip", "purple", cfg.model_id !== short ? cfg.model_id : undefined);
    }
    const maxImgs = cfg.max_images ?? 5;
    const triggerImgs = cfg.trigger_images_count ?? 0;
    const additionalSensors = cfg.additional_sensor_ids?.length || 0;
    const additionalRooms = cfg.additional_room_names?.length || 0;
    if (maxImgs > 0) chip(`≤ ${maxImgs} images`, "mdi-image-multiple-outline", "teal");
    if (triggerImgs > 0) chip(`${triggerImgs} trigger frame${triggerImgs > 1 ? "s" : ""}`, "mdi-camera", "teal");
    if (additionalSensors > 0) chip(`+${additionalSensors} sensor${additionalSensors > 1 ? "s" : ""}`, "mdi-camera-plus-outline", "cyan");
    if (additionalRooms > 0) chip(cfg.additional_room_names.join(", "), "mdi-home-outline", "cyan");
    if (cfg.output_key && cfg.output_key !== "llm_response") chip(`→ ${cfg.output_key}`, "mdi-export-variant", "blue-grey");
    if (cfg.response_format && cfg.response_format !== "default") chip(cfg.response_format, "mdi-code-json", "blue-grey");
  }

  if (type === "scene_analysis") {
    const source = cfg.image_source || "trigger";
    chip(source, "mdi-image-outline", "teal");
    const maxImgs = cfg.max_images ?? 1;
    if (maxImgs > 1) chip(`≤ ${maxImgs} images`, "mdi-image-multiple-outline", "teal");
    if (cfg.run_detect !== false) chip("detect", "mdi-eye-outline", "green");
    if (cfg.run_describe !== false) chip("describe", "mdi-text-box-outline", "green");
    if (cfg.run_hazards !== false) chip("hazards", "mdi-alert-outline", "orange");
    if (cfg.run_embed) chip("embed", "mdi-vector-combine", "blue");
    const addSensors = cfg.additional_sensor_ids?.length || 0;
    const addRooms = cfg.additional_room_names?.length || 0;
    if (addSensors > 0) chip(`+${addSensors} sensor${addSensors > 1 ? "s" : ""}`, "mdi-camera-plus-outline", "cyan");
    if (addRooms > 0) chip(cfg.additional_room_names.join(", "), "mdi-home-outline", "cyan");
    if (cfg.output_key && cfg.output_key !== "scene_images") chip(`→ ${cfg.output_key}`, "mdi-export-variant", "blue-grey");
  }

  if (type === "notification") {
    const level = cfg.alert_level || "warning";
    chip(level, "mdi-bell-outline", ALERT_COLORS[level] || "orange");
    if (cfg.channels?.length) chip(cfg.channels.join(", "), "mdi-send-outline", undefined);
    const telegramSrc = cfg.telegram_image_source;
    if (telegramSrc && telegramSrc !== "trigger") chip(`telegram: ${telegramSrc}`, "mdi-send", "blue");
    if (cfg.trigger_cooloff === false) chip("no cooloff", "mdi-timer-off-outline", "warning");
  }

  if (type === "condition") {
    if (cfg.trigger_cooloff) chip("cooloff on match", "mdi-timer-outline", "blue-grey");
  }

  if (type === "person_identification") {
    if (cfg.target_persons?.length) {
      chip(cfg.target_persons.join(", "), "mdi-account-outline", "indigo");
    } else {
      chip("all persons", "mdi-account-group-outline", "indigo");
    }
    if (cfg.min_confidence != null) chip(`≥ ${Math.round(cfg.min_confidence * 100)}% conf`, "mdi-percent", "teal");
    if (cfg.include_annotated_image) chip("annotated image", "mdi-image-edit-outline", undefined);
    if (cfg.write_movements_to_memory) chip("writes to memory", "mdi-database-arrow-up-outline", "purple");
  }

  if (type === "ha_action") {
    const domain = cfg.domain || "";
    const service = cfg.service || "";
    if (domain || service) chip(`${domain}.${service}`, "mdi-home-automation", "blue");
    if (cfg.entity_id) chip(truncate(cfg.entity_id, 32), "mdi-identifier", undefined, cfg.entity_id.length > 32 ? cfg.entity_id : undefined);
  }

  if (type === "wait") {
    const mins = cfg.minutes ?? 5;
    chip(`${mins} min`, "mdi-timer-sand", "amber");
  }

  if (type === "verification") {
    if (cfg.conditions?.length) {
      const mode = cfg.match_mode || "all";
      chip(`${cfg.conditions.length} condition${cfg.conditions.length > 1 ? "s" : ""} (${mode})`, "mdi-check-all", undefined);
    }
    if (cfg.re_notify_if_failed) chip(`re-notify ${cfg.re_notify_delay_minutes || 5}min`, "mdi-bell-ring-outline", "orange");
  }

  if (type === "activity_detection") {
    if (cfg.activity_type) chip(cfg.activity_type, "mdi-run", "indigo");
    if (cfg.person_id) chip(cfg.person_id, "mdi-account-outline", undefined);
    if (cfg.room_name) chip(cfg.room_name, "mdi-home-outline", undefined);
    const conf = cfg.confidence ?? 0.8;
    chip(`${Math.round(conf * 100)}% conf`, "mdi-percent", "teal");
  }

  if (type === "activity_session_start" || type === "activity_session_end") {
    if (cfg.activity_type) chip(cfg.activity_type, "mdi-run", "indigo");
    if (cfg.source_key) chip(`source: ${cfg.source_key}`, "mdi-link-variant", "blue-grey");
  }

  if (type === "object_trend_analysis") {
    if (cfg.room_ids?.length) chip(cfg.room_ids.join(", "), "mdi-home-group", "indigo");
    else chip("all rooms", "mdi-home-group", "indigo");
    if (cfg.severity_threshold) chip(cfg.severity_threshold, "mdi-alert-circle-outline", undefined);
    if (cfg.output_key && cfg.output_key !== "room_trends") chip(`→ ${cfg.output_key}`, "mdi-export-variant", "blue-grey");
  }

  if (type === "semantic_memory_query") {
    if (cfg.output_key) chip(`→ ${cfg.output_key}`, "mdi-export-variant", "blue-grey");
    if (cfg.top_k) chip(`top ${cfg.top_k}`, "mdi-format-list-numbered", undefined);
  }

  if (type === "semantic_memory_write") {
    if (cfg.source_key) chip(`source: ${cfg.source_key}`, "mdi-link-variant", "blue-grey");
  }

  return chips;
});

// ── Text preview (prompt / expression / message template) ─────────────────────

const textPreview = computed(() => {
  const cfg = props.step.config_json;
  if (!cfg || typeof cfg !== "object") return "";
  const type = props.step.step_type;

  if (type === "llm_call" && cfg.prompt) return truncate(cfg.prompt, 120);
  if (type === "condition" && cfg.expression) return truncate(cfg.expression, 100);
  if (type === "notification" && (cfg.message_template || cfg.telegram_template)) {
    return truncate(cfg.message_template || cfg.telegram_template, 120);
  }
  if (type === "semantic_memory_query" && cfg.query) return truncate(cfg.query, 100);
  if (type === "semantic_memory_write" && cfg.content) return truncate(cfg.content, 100);
  return "";
});
</script>

<style scoped>
.cc-drag-handle {
  cursor: grab;
  opacity: 0.45;
  transition: opacity 0.15s;
}
.cc-drag-handle:hover {
  opacity: 0.85;
}
.cc-drag-handle:active {
  cursor: grabbing;
}
.cc-token-chip {
  font-family: "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace;
}
.cc-mono {
  font-family: "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace;
}
.cc-detail-chip {
  max-width: 260px;
  overflow: hidden;
  margin-right: 6px;
  margin-bottom: 5px;
}
.cc-detail-chip :deep(.v-chip__content) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cc-preview-text {
  border-left: 2px solid rgba(var(--v-theme-on-surface), 0.12);
  padding-left: 8px;
  font-style: italic;
  line-height: 1.4;
}
.step-num-chip {
  min-width: 24px;
  justify-content: center;
}
</style>
